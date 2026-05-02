"""Browser-use integration for automated web security testing.
Requires: browser-use v0.12+ (pip install browser-use)
Graceful degradation when browser-use is not installed.
"""
import os
import sys
from pathlib import Path

_RAPTOR_DIR = os.environ["RAPTOR_DIR"]

try:
    from browser_use import Agent as BrowserAgent, Browser, BrowserConfig
    _BROWSER_USE_AVAILABLE = True
except ImportError:
    _BROWSER_USE_AVAILABLE = False


def is_available() -> bool:
    return _BROWSER_USE_AVAILABLE


# Security test prompts — each targets a specific vulnerability class
_XSS_PROBE_TEMPLATE = """\
You are a security researcher testing for XSS vulnerabilities on {target_url}.
Navigate to the target URL and identify all input fields, search boxes, and URL parameters.
For each input, attempt to inject: <script>alert('xss')</script> and note if it reflects unescaped.
Also try: "><img src=x onerror=alert(1)> and javascript:alert(1) in URL parameters.
Report: field name, injection payload, whether it reflected, and severity (reflected/stored/DOM).
Format findings as JSON list with keys: field, payload, reflected, severity, evidence.
"""

_CSRF_PROBE_TEMPLATE = """\
You are a security researcher testing for CSRF vulnerabilities on {target_url}.
Navigate to the target and identify state-changing forms (login, profile update, password change, etc.).
Check each form for: presence of CSRF token, SameSite cookie attribute, Origin/Referer validation.
Report: form action, method, has_csrf_token, samesite_cookie, findings as JSON list.
"""

_AUTH_BYPASS_PROBE_TEMPLATE = """\
You are a security researcher testing authentication on {target_url}.
Navigate to the target and attempt:
1. Direct URL access to /admin, /dashboard, /api/admin without authentication
2. IDOR: replace user IDs in URLs with sequential values (e.g., /user/1, /user/2)
3. JWT manipulation: check if tokens are validated on protected endpoints
4. Parameter tampering: add ?admin=true or ?role=admin to authenticated requests
Report findings as JSON list with keys: technique, url, bypassed (bool), evidence.
"""

_INJECTION_PROBE_TEMPLATE = """\
You are a security researcher testing for injection vulnerabilities on {target_url}.
Navigate to all search/filter inputs and attempt:
1. SQL: ' OR '1'='1 and 1; DROP TABLE users--
2. Command: ; ls -la and | whoami
3. SSTI: {{7*7}} and ${{7*7}}
Report: input_name, payload, response_hint (error message, timing, unexpected output), severity.
"""


def _make_agent(task: str, llm=None):
    """Create a browser-use Agent with the given task."""
    if not _BROWSER_USE_AVAILABLE:
        raise RuntimeError(
            "browser-use is not installed. "
            "Install with: pip install browser-use"
        )

    if llm is None:
        try:
            import anthropic
            from langchain_anthropic import ChatAnthropic
            llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
        except ImportError:
            raise RuntimeError(
                "langchain-anthropic not installed. "
                "Install with: pip install langchain-anthropic"
            )

    config = BrowserConfig(headless=True)
    browser = Browser(config=config)
    return BrowserAgent(task=task, llm=llm, browser=browser)


async def probe_xss(target_url: str, llm=None) -> dict:
    """Run XSS probe against target_url."""
    agent = _make_agent(_XSS_PROBE_TEMPLATE.format(target_url=target_url), llm)
    result = await agent.run()
    return {"probe": "xss", "target": target_url, "result": result}


async def probe_csrf(target_url: str, llm=None) -> dict:
    """Run CSRF probe against target_url."""
    agent = _make_agent(_CSRF_PROBE_TEMPLATE.format(target_url=target_url), llm)
    result = await agent.run()
    return {"probe": "csrf", "target": target_url, "result": result}


async def probe_auth_bypass(target_url: str, llm=None) -> dict:
    """Run authentication bypass probe against target_url."""
    agent = _make_agent(_AUTH_BYPASS_PROBE_TEMPLATE.format(target_url=target_url), llm)
    result = await agent.run()
    return {"probe": "auth_bypass", "target": target_url, "result": result}


async def probe_injection(target_url: str, llm=None) -> dict:
    """Run injection probe (SQLi/CMDi/SSTI) against target_url."""
    agent = _make_agent(_INJECTION_PROBE_TEMPLATE.format(target_url=target_url), llm)
    result = await agent.run()
    return {"probe": "injection", "target": target_url, "result": result}


async def run_full_scan(target_url: str, llm=None, probes: list[str] | None = None) -> list[dict]:
    """Run all (or selected) probes against target_url.

    Args:
        target_url: URL to test (must be authorized for testing).
        llm: Optional LangChain LLM instance.
        probes: List of probe names to run. Defaults to all probes.

    Returns:
        List of result dicts from each probe.
    """
    all_probes = {
        "xss": probe_xss,
        "csrf": probe_csrf,
        "auth_bypass": probe_auth_bypass,
        "injection": probe_injection,
    }
    selected = {k: v for k, v in all_probes.items() if not probes or k in probes}

    results = []
    for name, probe_fn in selected.items():
        try:
            result = await probe_fn(target_url, llm)
            results.append(result)
        except Exception as e:
            results.append({"probe": name, "target": target_url, "error": str(e)})
    return results
