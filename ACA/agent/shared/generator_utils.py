"""Helpers for extracting generator code from an LLM response."""

from __future__ import annotations

import codecs
import hashlib
import re
from typing import Any, Dict, Optional, Tuple


GENERATOR_OK = "GENERATOR_OK"
GENERATOR_EXTRACTION_ERROR = "GENERATOR_EXTRACTION_ERROR"

_FENCED_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _normalize_code_block(text: str) -> str:
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")


def _try_compile(code: str) -> bool:
    try:
        compile(code, "<generator>", "exec")
        return True
    except Exception:
        return False


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _looks_like_multiline_python(code: str) -> bool:
    """Heuristic: code contains real newlines AND typical Python keywords/patterns."""
    if "\n" not in code:
        return False
    indicators = ("def ", "import ", "print(", "return ", "if __name__", "class ", "=")
    return any(indicator in code for indicator in indicators)


def normalize_generator_code_transport_escapes(code: str) -> Tuple[str, Dict]:
    """Conservatively repair newline escape sequences introduced by JSON/tool-call transport.

    Strategy:
    1. If code compiles as-is, return unchanged (e.g. BaseG markdown output, or valid
       single-line code like ``print("1\\n2")``).
    2. If code fails to compile AND contains literal ``\\n``, try targeted newline
       dedoubling (up to 2 rounds).
    3. As last resort, try ``codecs.decode(..., "unicode_escape")`` but only accept
       the result if it compiles and looks like valid multi-line Python.

    Returns (normalized_code, metadata).
    """
    meta: Dict = {
        "normalization_applied": False,
        "normalization_rule": None,
        "normalization_rounds": 0,
        "original_compile_ok": False,
        "normalized_compile_ok": False,
        "original_hash": _stable_hash(code),
        "normalized_hash": _stable_hash(code),
    }

    if not code:
        return code, meta

    original_ok = _try_compile(code)
    meta["original_compile_ok"] = original_ok
    if original_ok:
        return code, meta

    # Code does not compile — check whether escape sequences are the culprit.
    if "\\n" not in code:
        return code, meta

    # ---- Phase 1: targeted newline dedouble ----
    normalized = code
    for round_id in (1, 2):
        if "\\n" not in normalized and "\\r\\n" not in normalized:
            break
        before = normalized
        normalized = normalized.replace("\\r\\n", "\n").replace("\\n", "\n")
        if normalized == before:
            break
        meta["normalization_rounds"] = round_id

    if normalized != code and _try_compile(normalized):
        meta["normalization_applied"] = True
        meta["normalization_rule"] = "newline_dedouble"
        meta["normalized_compile_ok"] = True
        meta["normalized_hash"] = _stable_hash(normalized)
        return normalized, meta

    # ---- Phase 2: unicode_escape fallback ----
    try:
        candidate = codecs.decode(code, "unicode_escape")
    except Exception:
        return code, meta

    if candidate != code and _try_compile(candidate) and _looks_like_multiline_python(candidate):
        meta["normalization_applied"] = True
        meta["normalization_rule"] = "unicode_escape_fallback"
        meta["normalized_compile_ok"] = True
        meta["normalized_hash"] = _stable_hash(candidate)
        return candidate, meta

    return code, meta


def _extract_from_tool_calls(msg: Any) -> Optional[str]:
    tool_calls = getattr(msg, "tool_calls", None) or []
    for tc in tool_calls:
        args = tc.get("args", {}) if isinstance(tc, dict) else {}
        for key in ("code", "python_code", "generator_code"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return _normalize_code_block(value)
    return None


def _extract_from_text(text: str) -> Optional[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return None

    matches = _FENCED_BLOCK_RE.findall(normalized)
    if matches:
        code = _normalize_code_block(matches[0])
        return code or None

    if normalized.startswith("```"):
        lines = normalized.split("\n")
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = _normalize_code_block("\n".join(lines))
        return stripped or None

    # Accept raw code if it looks executable enough for first-pass usage.
    if "\n" in normalized or normalized.startswith(("import ", "from ", "def ", "print(", "seed", "if __name__")):
        return _normalize_code_block(normalized)
    return None


def extract_generator_code(msg_or_text: Any) -> Tuple[str, Optional[str]]:
    """Extract Python generator code from tool-call payload or message text.

    The returned code is normalized through
    :func:`normalize_generator_code_transport_escapes` so that double-escaped
    newlines (``\\\\n``) introduced by JSON/tool-call transport are repaired
    before the code reaches the compile / execution sandbox.
    """
    code = _extract_from_tool_calls(msg_or_text)
    if code:
        normalized, _ = normalize_generator_code_transport_escapes(code)
        return GENERATOR_OK, normalized

    if hasattr(msg_or_text, "content"):
        text = getattr(msg_or_text, "content", "") or ""
    else:
        text = str(msg_or_text or "")

    code = _extract_from_text(text)
    if code:
        normalized, _ = normalize_generator_code_transport_escapes(code)
        return GENERATOR_OK, normalized
    return GENERATOR_EXTRACTION_ERROR, None
