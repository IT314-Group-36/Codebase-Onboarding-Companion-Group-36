"""Content-level secret redaction (second line of defence after the filename filter).

Matches are replaced with a placeholder; newlines are preserved so line numbers stay correct.
This is deliberately small and dependency-free. For production add gitleaks / detect-secrets.
"""
import math
import re

_FIXED = [
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z ]+ )?PRIVATE KEY-----|\Z)"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b"),
    re.compile(r"\b[sr]k_(?:live|test)_[0-9a-zA-Z]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
]
_GENERIC = re.compile(
    r"""(?ix)\b([\w.\-]*(?:api[_-]?key|secret|token|passwd|password|pwd|auth[_-]?key|private[_-]?key)[\w.\-]*)
        \s*[:=]\s*(['"])([^'"\s]{12,})\2""")
_PLACEHOLDER = re.compile(r"(your|example|sample|changeme|change_me|placeholder|xxxx|dummy|todo|<|\$\{|%\()", re.I)
REDACTED = "[REDACTED_SECRET]"


def _entropy(s: str) -> float:
    return -sum(s.count(c) / len(s) * math.log2(s.count(c) / len(s)) for c in set(s))


def redact_secrets(text: str) -> tuple[str, int]:
    """Returns (clean_text, number_of_redactions)."""
    count = 0

    def fixed(m):
        nonlocal count
        count += 1
        return REDACTED + "\n" * m.group(0).count("\n")

    def generic(m):
        nonlocal count
        value = m.group(3)
        if REDACTED in value or _PLACEHOLDER.search(value) or _entropy(value) < 3.0:
            return m.group(0)
        count += 1
        return m.group(0).replace(value, REDACTED)

    for rx in _FIXED:
        text = rx.sub(fixed, text)
    return _GENERIC.sub(generic, text), count
