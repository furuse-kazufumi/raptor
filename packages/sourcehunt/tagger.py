"""
File security tagger.

Classifies source files with security-relevant tags to drive
specialist routing in the sourcehunt pipeline.

Tags (mirrors Clearwing's scheme):
  memory_unsafe  – C/C++ with raw memory operations
  parser         – decoding / parsing logic
  crypto         – cryptographic primitives or protocols
  auth_boundary  – authentication / authorisation decision points
  syscall_entry  – kernel / syscall interfaces
  fuzzable       – public entry points that accept external input
"""

import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.inventory.languages import detect_language

# ---------------------------------------------------------------------------
# Pattern tables
# ---------------------------------------------------------------------------

_MEMORY_UNSAFE_LANGS = {"c", "cpp"}

_MEMORY_UNSAFE_RE = re.compile(
    r"\b(malloc|calloc|realloc|free|memcpy|memmove|memset|memcmp|"
    r"strcpy|strcat|sprintf|vsprintf|gets|scanf|"
    r"strncpy|strncat|snprintf|alloca|__builtin_alloca|"
    r"new\s*\[|delete\s*\[)\s*\("
)

_PARSER_RE = re.compile(
    r"\b(parse_?[A-Za-z]|tokenize|tokenizer|lexer|lex_[A-Za-z]|"
    r"decoder|deserializ|from_json|from_xml|from_bytes|unpack|"
    r"read_field|grammar|scan_token|next_token|parse_message|"
    r"parse_header|parse_packet|parse_request)\b",
    re.IGNORECASE,
)

_CRYPTO_RE = re.compile(
    r"\b(cipher|chacha|salsa|AES|aes_|rsa_|dsa_|ecdsa|ecdh|"
    r"sha[0-9]+|sha_[0-9]|md5|hmac|blake2|poly1305|"
    r"encrypt|decrypt|EVP_|BN_|RAND_|BIGNUM|"
    r"ssl_|tls_|SSL_|TLS_|openssl|mbedtls|wolfssl|"
    r"pbkdf2|bcrypt|scrypt|argon2|kdf|derive_key|"
    r"nonce|iv_size|key_schedule|key_expansion)\b",
    re.IGNORECASE,
)

_AUTH_RE = re.compile(
    r"\b(authenticate|authoriz|login|logout|session_|"
    r"privilege|credential|jwt|oauth|bearer_|"
    r"access_control|permission|role_check|acl_|policy_|"
    r"is_admin|is_root|sudo_|check_auth|verify_token|"
    r"has_permission|require_admin|cap_|setuid|setgid)\b",
    re.IGNORECASE,
)

_SYSCALL_RE = re.compile(
    r"\b(syscall\s*\(|__syscall|__NR_[A-Z]|"
    r"copy_from_user|copy_to_user|put_user\s*\(|get_user\s*\(|"
    r"SYSCALL_DEFINE[0-9]|sys_call_table|"
    r"seccomp|ptrace\s*\(|mmap\s*\(|mprotect\s*\(|"
    r"execve\s*\(|ioctl\s*\(|prctl\s*\()\b"
)

# Matches exported/public function signatures across languages
_FUZZABLE_RE = re.compile(
    r"(?:"
    r"^pub\s+(?:unsafe\s+)?fn\s+\w+"                    # Rust pub fn
    r"|^extern\s+\"C\""                                  # Rust extern "C"
    r"|^(?:__attribute__\s*\(\s*\(\s*visibility)"        # C __attribute__((visibility))
    r"|^\s*(?:public|protected)\s+\w[\w<>\[\]]*\s+\w+\s*\("  # Java/C# public method
    r"|^(?:void|int|char\s*\*|bool|size_t|ssize_t|uint\w*|int\w*)\s+"
      r"\w+\s*\([^)]{0,120}\)\s*\{"                     # C public function definition
    r"|^def\s+[a-z]\w*\s*\(self"                        # Python public method
    r"|^module\.exports\s*="                             # Node.js exported
    r")",
    re.MULTILINE,
)


def tag_file(file_path: str, content: Optional[str] = None) -> set[str]:
    """Assign security tags to a single source file.

    Args:
        file_path: Absolute or relative path to the source file.
        content:   Pre-loaded file text (read from disk when None).

    Returns:
        Set of tag strings (may be empty for non-source or unreadable files).
    """
    path = Path(file_path)
    lang = detect_language(str(path))

    try:
        if content is None:
            content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()

    tags: set[str] = set()

    # memory_unsafe only for C/C++
    if lang in _MEMORY_UNSAFE_LANGS and _MEMORY_UNSAFE_RE.search(content):
        tags.add("memory_unsafe")

    if _PARSER_RE.search(content):
        tags.add("parser")

    if _CRYPTO_RE.search(content):
        tags.add("crypto")

    if _AUTH_RE.search(content):
        tags.add("auth_boundary")

    if _SYSCALL_RE.search(content):
        tags.add("syscall_entry")

    if _FUZZABLE_RE.search(content):
        tags.add("fuzzable")

    return tags


def tag_files_batch(
    file_paths: list[str],
    max_workers: int = 8,
) -> dict[str, set[str]]:
    """Tag multiple files in parallel.

    Returns:
        {file_path: set_of_tags} for every path in file_paths.
    """
    results: dict[str, set[str]] = {}

    def _tag_one(fp: str) -> tuple[str, set[str]]:
        return fp, tag_file(fp)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for fp, tags in ex.map(_tag_one, file_paths):
            results[fp] = tags

    return results
