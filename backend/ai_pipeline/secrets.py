"""Content-level secret redaction (second line of defence after the filename filter).

Matches are replaced with a placeholder; newlines are preserved so line numbers stay correct.
This is best-effort, not a guarantee that arbitrary secrets can be recognised.
Run a dedicated scanner such as gitleaks on repositories before uploading them.
"""
import re

_FIXED = [
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z ]+ )?PRIVATE KEY-----|\Z)"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b"),
    re.compile(r"\b[sr]k_(?:live|test)_[0-9a-zA-Z]{16,}\b"),
    re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
]
_GENERIC = re.compile(
    r"""(?ix)(?<![\w.\-])(?P<key_quote>['"]?)
        [\w.\-]*(?:api[_-]?key|secret|token|passwd|password|pwd|auth[_-]?key|private[_-]?key)[\w.\-]*
        (?P=key_quote)[ \t]*[:=][ \t]*
        (?:"(?P<double>[^"\r\n]*)"|'(?P<single>[^'\r\n]*)'
        |(?P<bare>\[REDACTED_SECRET\]|[^\s,;\#}\])'"]+))""")
# Any URI scheme, including postgresql+psycopg, redis, mongodb+srv and HTTPS.
# Remove all userinfo, not just the password; percent-encoded passwords remain covered.
_CREDENTIAL_URI = re.compile(r"""(?i)\b[a-z][a-z0-9+.\-]*://(?P<value>[^/@\s"'<>]*:[^/@\s"'<>]+)@""")
_AUTH_HEADER = re.compile(r"(?i)\b(?:Bearer|Basic)[ \t]+(?P<value>[A-Za-z0-9_~+./=\-]{8,})")
# Match whole placeholder values, never arbitrary substrings inside real credentials.
_PLACEHOLDER = re.compile(
    r"""(?ix)(?:your(?:[_-][\w-]+)+|(?:example|sample|dummy|placeholder|todo)(?:[_-][\w-]+)*
        |change[_-]?me|x{4,}|<[^>]+>|\$\{[^}]*\}?|%\([^)]+\)s
        |(?:process\.env|os\.environ|os\.getenv)(?:[.\[(].*)?
        |true|false|null|none|undefined)""")
REDACTED = "[REDACTED_SECRET]"


def _is_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER.fullmatch(value))


def redact_secrets(text: str) -> tuple[str, int]:
    """Returns (clean_text, number_of_redactions)."""
    count = 0

    def fixed(m):
        nonlocal count
        count += 1
        return REDACTED + "\n" * m.group(0).count("\n")

    def generic(m):
        nonlocal count
        group = next(g for g in ("double", "single", "bare") if m.group(g) is not None)
        value = m.group(group)
        # Explicit secret assignments do not need an entropy/length threshold:
        # a short, low-entropy password is still private.
        if not value or REDACTED in value or _is_placeholder(value):
            return m.group(0)
        count += 1
        start, end = m.start(group) - m.start(), m.end(group) - m.start()
        return m.group(0)[:start] + REDACTED + m.group(0)[end:]

    def credential(m):
        nonlocal count
        value = m.group("value")
        if REDACTED in value or _is_placeholder(value):
            return m.group(0)
        # URI credentials may consist entirely of explicit environment placeholders.
        if ":" in value and all(not part or _is_placeholder(part) for part in value.split(":", 1)):
            return m.group(0)
        count += 1
        start, end = m.start("value") - m.start(), m.end("value") - m.start()
        return m.group(0)[:start] + REDACTED + m.group(0)[end:]

    for rx in _FIXED:
        text = rx.sub(fixed, text)
    text = _CREDENTIAL_URI.sub(credential, text)
    text = _AUTH_HEADER.sub(credential, text)
    return _GENERIC.sub(generic, text), count
