"""
ASan/UBSan crash-oracle verification.

Clearwing's "crash-first" philosophy: treat AddressSanitizer and
UndefinedBehaviorSanitizer as ground truth.  A reproduced crash
upgrades a finding from suspicion → crash_reproduced, which gates
PoC generation in the validation pipeline.

Workflow:
  1. Detect available compiler (gcc/clang, or WSL on Windows).
  2. Compile the target file with -fsanitize=address,undefined.
  3. Run the binary with a generated or provided test input.
  4. Capture ASAN/UBSAN output; classify crash type.
  5. Return CrashEvidence with the raw output and signal.

Platform notes:
  - Linux/macOS: gcc or clang, native ASan/UBSan.
  - Windows: tries clang-cl first, then falls back to WSL (bash -c).
    If neither is available, compile_result.available = False.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.config import RaptorConfig
from core.logging import get_logger

logger = get_logger()

# ---------------------------------------------------------------------------
# ASAN / UBSAN output parsers
# ---------------------------------------------------------------------------

_ASAN_SUMMARY_RE = re.compile(
    r"SUMMARY:\s*(AddressSanitizer|LeakSanitizer):\s*(\S+)\s+"
    r"(?:on address 0x[0-9a-f]+)?\s*(?:at\s+(.+?))?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_UBSAN_RE = re.compile(
    r"(.*?):\s*runtime error:\s*(.+)$",
    re.MULTILINE,
)

_SIGNAL_RE = re.compile(r"signal\s+(\d+)", re.IGNORECASE)

# Map ASAN error types to CWE
_ASAN_CWE_MAP = {
    "heap-buffer-overflow":  "CWE-122",
    "stack-buffer-overflow": "CWE-121",
    "global-buffer-overflow":"CWE-122",
    "heap-use-after-free":   "CWE-416",
    "double-free":           "CWE-415",
    "use-after-poison":      "CWE-416",
    "null-dereference":      "CWE-476",
    "stack-overflow":        "CWE-121",
}

_UBSAN_CWE_MAP = {
    "integer overflow":    "CWE-190",
    "signed integer":      "CWE-190",
    "unsigned integer":    "CWE-190",
    "null pointer":        "CWE-476",
    "shift exponent":      "CWE-682",
    "out of bounds":       "CWE-125",
    "misaligned address":  "CWE-704",
}


@dataclass
class CrashEvidence:
    """Result of a sanitizer-verification run."""

    crashed: bool
    sanitizer: str          # "asan" | "ubsan" | "both" | "none"
    error_type: str         # e.g. "heap-buffer-overflow"
    cwe: str                # inferred CWE
    signal: str             # e.g. "SIGABRT"
    raw_output: str
    compile_cmd: str
    run_cmd: str
    compile_error: str = ""
    available: bool = True  # False when toolchain not present

    @property
    def evidence_level(self) -> str:
        if self.crashed:
            return "crash_reproduced"
        return "static_corroboration"


@dataclass
class _CompilerInfo:
    exe: str
    is_wsl: bool
    flags: list[str]


# ---------------------------------------------------------------------------
# Compiler detection
# ---------------------------------------------------------------------------

def _detect_compiler() -> Optional[_CompilerInfo]:
    """Find the best available compiler with sanitizer support."""
    system = platform.system()

    candidates = ["clang", "gcc", "cc"]
    if system == "Windows":
        candidates = ["clang", "clang-cl"] + candidates

    for exe in candidates:
        if shutil.which(exe):
            return _CompilerInfo(exe=exe, is_wsl=False, flags=[])

    # Windows fallback: try via WSL
    if system == "Windows" and shutil.which("wsl"):
        for wsl_cc in ["clang", "gcc", "cc"]:
            result = subprocess.run(
                ["wsl", "which", wsl_cc],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return _CompilerInfo(exe=wsl_cc, is_wsl=True, flags=[])

    return None


def _sanitizer_flags(exe: str) -> list[str]:
    """Return ASan+UBSan compile flags supported by the given compiler."""
    # clang-cl uses different flag syntax
    if "clang-cl" in exe:
        return ["/fsanitize=address"]
    return ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g", "-O1"]


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def _compile_with_sanitizers(
    source_file: str,
    output_binary: str,
    compiler_info: _CompilerInfo,
    extra_flags: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """Compile a single C/C++ source file with ASan+UBSan.

    Returns (success, error_output).
    """
    san_flags = _sanitizer_flags(compiler_info.exe)
    if extra_flags:
        san_flags = san_flags + extra_flags

    cmd = [compiler_info.exe] + san_flags + [source_file, "-o", output_binary]

    if compiler_info.is_wsl:
        # Translate Windows paths to WSL-style
        wsl_src = source_file.replace("\\", "/").replace("C:", "/mnt/c").replace("D:", "/mnt/d")
        wsl_out = output_binary.replace("\\", "/").replace("C:", "/mnt/c").replace("D:", "/mnt/d")
        cmd = ["wsl"] + [compiler_info.exe] + san_flags + [wsl_src, "-o", wsl_out]

    logger.debug(f"[sanitizer] compile: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=RaptorConfig.get_safe_env(),
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout)[:4096]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Crash-output parsers
# ---------------------------------------------------------------------------

def _parse_asan_output(output: str) -> tuple[str, str]:
    """Return (error_type, cwe) from ASAN output."""
    m = _ASAN_SUMMARY_RE.search(output)
    if m:
        error_type = m.group(2).lower()
        cwe = _ASAN_CWE_MAP.get(error_type, "CWE-119")
        return error_type, cwe
    return "unknown", "CWE-119"


def _parse_ubsan_output(output: str) -> tuple[str, str]:
    """Return (error_type, cwe) from UBSAN output."""
    m = _UBSAN_RE.search(output)
    if m:
        msg = m.group(2).lower()
        for kw, cwe in _UBSAN_CWE_MAP.items():
            if kw in msg:
                return msg[:80], cwe
        return msg[:80], "CWE-119"
    return "unknown", "CWE-119"


def _classify_output(output: str) -> tuple[str, str, str]:
    """Return (sanitizer_name, error_type, cwe)."""
    has_asan = "AddressSanitizer" in output or "ASan" in output
    has_ubsan = "runtime error:" in output and "AddressSanitizer" not in output

    if has_asan:
        et, cwe = _parse_asan_output(output)
        return "asan", et, cwe
    if has_ubsan:
        et, cwe = _parse_ubsan_output(output)
        return "ubsan", et, cwe
    if "signal" in output.lower():
        m = _SIGNAL_RE.search(output)
        sig = m.group(1) if m else "unknown"
        return "signal", f"signal_{sig}", "CWE-119"
    return "none", "none", ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SanitizerRunner:
    """Compile-and-run crash oracle using ASan/UBSan.

    Usage:
        runner = SanitizerRunner()
        if runner.available:
            evidence = runner.verify(
                source_file="/tmp/target.c",
                test_input=b"AAAA" * 100,
            )
            if evidence.crashed:
                print(f"Crash confirmed: {evidence.error_type}")
    """

    def __init__(self):
        self._compiler = _detect_compiler()

    @property
    def available(self) -> bool:
        return self._compiler is not None

    def verify(
        self,
        source_file: str,
        test_input: bytes = b"",
        extra_compile_flags: Optional[list[str]] = None,
        timeout_run: int = 10,
    ) -> CrashEvidence:
        """Compile with sanitizers and run with test_input.

        Args:
            source_file:          Path to C/C++ source file.
            test_input:           Bytes fed to the binary via stdin.
            extra_compile_flags:  Additional compiler flags (e.g. -I headers).
            timeout_run:          Seconds before killing the run.

        Returns:
            CrashEvidence summarising the result.
        """
        if not self._compiler:
            return CrashEvidence(
                crashed=False, sanitizer="none", error_type="toolchain_unavailable",
                cwe="", signal="", raw_output="",
                compile_cmd="", run_cmd="", available=False,
            )

        san_flags = _sanitizer_flags(self._compiler.exe)
        compile_cmd_str = (
            f"{self._compiler.exe} {' '.join(san_flags)} {source_file} -o <binary>"
        )

        with tempfile.TemporaryDirectory(prefix="raptor_san_") as tmpdir:
            binary = os.path.join(tmpdir, "target_san")

            ok, compile_err = _compile_with_sanitizers(
                source_file=source_file,
                output_binary=binary,
                compiler_info=self._compiler,
                extra_flags=extra_compile_flags,
            )
            if not ok:
                return CrashEvidence(
                    crashed=False, sanitizer="none", error_type="compile_error",
                    cwe="", signal="", raw_output="",
                    compile_cmd=compile_cmd_str, run_cmd="",
                    compile_error=compile_err, available=True,
                )

            # Run binary
            env = RaptorConfig.get_safe_env()
            env["ASAN_OPTIONS"] = "detect_leaks=0:abort_on_error=0:print_stats=0"
            env["UBSAN_OPTIONS"] = "print_stacktrace=1"

            run_cmd_parts: list[str]
            if self._compiler.is_wsl:
                wsl_binary = binary.replace("\\", "/").replace("C:", "/mnt/c").replace("D:", "/mnt/d")
                run_cmd_parts = ["wsl", wsl_binary]
            else:
                run_cmd_parts = [binary]

            run_cmd_str = " ".join(run_cmd_parts)

            try:
                result = subprocess.run(
                    run_cmd_parts,
                    input=test_input,
                    capture_output=True,
                    timeout=timeout_run,
                    env=env,
                )
                raw_output = (result.stderr + result.stdout).decode("utf-8", errors="replace")
                crashed = result.returncode not in (0, 1)
            except subprocess.TimeoutExpired:
                raw_output = "Process timed out"
                crashed = False
            except Exception as e:
                raw_output = str(e)
                crashed = False

            san_name, error_type, cwe = _classify_output(raw_output)

            # Extract signal from returncode
            signal_str = ""
            if crashed and result.returncode < 0:
                sig = abs(result.returncode)
                signal_str = {
                    6: "SIGABRT", 11: "SIGSEGV", 4: "SIGILL",
                    8: "SIGFPE",  7: "SIGBUS",
                }.get(sig, f"SIG{sig}")

            return CrashEvidence(
                crashed=crashed,
                sanitizer=san_name,
                error_type=error_type,
                cwe=cwe,
                signal=signal_str,
                raw_output=raw_output[:8192],
                compile_cmd=compile_cmd_str,
                run_cmd=run_cmd_str,
                available=True,
            )

    def verify_with_generated_input(
        self,
        source_file: str,
        function_name: str,
        extra_compile_flags: Optional[list[str]] = None,
    ) -> CrashEvidence:
        """Attempt crash with auto-generated boundary-case inputs.

        Tries several classic mutation patterns:
          - Large buffer (4096 × 'A')
          - Negative integer encoded as 4 bytes
          - Long format string
          - NUL-heavy buffer
        """
        patterns: list[bytes] = [
            b"A" * 4096,
            b"\xff\xff\xff\xff" + b"A" * 64,
            b"%n%n%n%n%n%n%n%n" * 16,
            b"\x00" * 4096,
            b"A" * 256 + b"\x00" + b"B" * 256,
        ]

        best: Optional[CrashEvidence] = None
        for pattern in patterns:
            ev = self.verify(
                source_file=source_file,
                test_input=pattern,
                extra_compile_flags=extra_compile_flags,
            )
            if ev.crashed:
                return ev
            if best is None or (ev.available and not ev.compile_error):
                best = ev

        return best or CrashEvidence(
            crashed=False, sanitizer="none", error_type="no_crash",
            cwe="", signal="", raw_output="",
            compile_cmd="", run_cmd="", available=self.available,
        )
