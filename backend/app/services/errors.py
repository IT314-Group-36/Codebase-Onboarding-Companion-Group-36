"""Safe error messages.

Exceptions can contain SQL, file paths, library names and Git output. Those details help an attacker, so they are
written to the server log only, under a short reference id, and users get a fixed, friendly message instead.

Messages this application writes for the user are raised as `PublicError` (or `CloneLimitError`, whose texts are fixed too)
and are stored as they are. Everything else is mapped to a fixed message, or to a generic one with a reference id.
"""
import uuid

from fastapi import HTTPException

from ai_pipeline.clone_limits import CloneLimitError
from ai_pipeline.embeddings import EmbeddingError, EmbeddingQuotaError

CLONE_FAILED = ("Could not clone the repo. Check that the URL and branch are correct and, if the repository is private, "
                "that your GitHub account can access it.")
BRANCH_NOT_FOUND = "Could not clone the repo: that branch was not found. Check the branch name."
# Messages the pipeline writes itself (fixed text, no exception details): safe and useful to show as they are.
KNOWN_MESSAGES = frozenset({"No embeddable text files found in this repository."})


class PublicError(RuntimeError):
    """A message written by this application for the user: safe to store and to show as it is."""


def new_reference() -> str:
    """Short id that ties a user-visible message to the full traceback in the server log."""
    return uuid.uuid4().hex[:8]


def clone_error_message(raw: str) -> str:
    """Fixed message for a failed `git clone`. The raw Git output is never returned."""
    low = raw.lower()
    if "remote branch" in low and "not found" in low:
        return BRANCH_NOT_FOUND
    return CLONE_FAILED


def public_error_message(exc: BaseException, reference: str, task: str = "indexing") -> str:
    """The text that may be stored in `Repository.error` (and so returned by the API) for `exc`.

    The caller logs the full traceback together with `reference`.
    """
    if isinstance(exc, (PublicError, CloneLimitError)):
        return str(exc)[:1000]
    if isinstance(exc, HTTPException) and isinstance(exc.detail, str):      # e.g. the storage budget message
        return exc.detail[:1000]
    if isinstance(exc, EmbeddingQuotaError):                                 # fixed text: the daily allowance is used up
        return str(exc)[:1000]
    if isinstance(exc, EmbeddingError):                                      # provider response text stays in the log
        return (f"The embedding service failed (reference {reference}). Please try again later. "
                "If it keeps failing, tell the team this reference.")
    if isinstance(exc, RuntimeError) and str(exc) in KNOWN_MESSAGES:
        return str(exc)
    if isinstance(exc, RuntimeError) and str(exc).startswith("Could not clone"):
        return clone_error_message(str(exc))
    return (f"Unexpected error while {task} (reference {reference}). Please try again. "
            "If it keeps failing, tell the team this reference.")
