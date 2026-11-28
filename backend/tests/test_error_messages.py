"""C2: users get fixed, friendly messages; SQL, paths and Git output stay in the server log under a reference id."""
import logging
import re

from fastapi import HTTPException
from sqlalchemy.exc import ProgrammingError

from ai_pipeline.clone_limits import CloneLimitError
from ai_pipeline.embeddings import EmbeddingError, EmbeddingQuotaError
from app.main import docs_urls
from app.services import indexing
from app.services.errors import BRANCH_NOT_FOUND, CLONE_FAILED, PublicError, public_error_message
from tests.test_private_repos import register_and_index

SQL_ERROR = ProgrammingError("INSERT INTO users (github_login, encrypted_access_token) VALUES (%(a)s, %(b)s)",
                             {"a": "octo", "b": "secret"}, Exception('relation "users" does not exist'))
GIT_ERROR = ("Could not clone the repo. Check its URL, branch and GitHub access.\n"
             "fatal: unable to access '/tmp/onboarding_work/job_7_ab12cd34/clone/.git/config': Permission denied")


def _assert_clean(message: str) -> None:
    for leak in ("INSERT", "users", "encrypted_access_token", "/tmp/", "onboarding_work", "fatal:", "Traceback", "File \""):
        assert leak not in message


def test_unexpected_exception_becomes_a_generic_message_with_a_reference():
    message = public_error_message(SQL_ERROR, "abc12345")
    assert "abc12345" in message and message.startswith("Unexpected error while indexing")
    _assert_clean(message)


def test_git_failure_becomes_a_fixed_message_without_git_output():
    assert public_error_message(RuntimeError(GIT_ERROR), "abc12345") == CLONE_FAILED
    branch = "Could not clone the repo.\nfatal: Remote branch nope not found in upstream origin"
    assert public_error_message(RuntimeError(branch), "abc12345") == BRANCH_NOT_FOUND


def test_messages_written_by_the_app_are_kept():
    assert public_error_message(CloneLimitError("Cloning timed out."), "x") == "Cloning timed out."
    assert public_error_message(PublicError("Sign in with GitHub again."), "x") == "Sign in with GitHub again."
    assert public_error_message(HTTPException(503, "storage planning budget is full"), "x") == "storage planning budget is full"


def test_known_pipeline_messages_are_kept():
    message = "No embeddable text files found in this repository."
    assert public_error_message(RuntimeError(message), "x") == message


def test_embedding_provider_details_are_hidden_but_the_quota_message_is_kept():
    detail = EmbeddingError("Cloudflare rejected the API token (403): {'errors': [{'message': 'account 1234'}]}")
    message = public_error_message(detail, "abc12345")
    assert "abc12345" in message and "Cloudflare" not in message and "1234" not in message
    quota = EmbeddingQuotaError("Cloudflare Workers AI daily free allowance is used up; it resets at 00:00 UTC.")
    assert public_error_message(quota, "abc12345") == str(quota)


def test_api_docs_are_off_unless_enabled():
    assert docs_urls(False) == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert docs_urls(True) == {}


async def test_database_failure_is_stored_safely_and_logged_in_full(db, make_user, git_repo, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise SQL_ERROR
    monkeypatch.setattr(indexing, "analyze_checkout", boom)
    _, headers = await make_user()
    with caplog.at_level(logging.ERROR, logger="app.services.indexing"):
        repo, _ = await register_and_index(headers, git_repo)
    assert repo.status == "failed"
    _assert_clean(repo.error)
    reference = re.search(r"reference ([0-9a-f]{8})", repo.error).group(1)
    assert reference in caplog.text and "Traceback" in caplog.text and "INSERT INTO users" in caplog.text


async def test_git_failure_is_stored_without_git_output(db, make_user, git_repo, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError(GIT_ERROR)
    monkeypatch.setattr(indexing, "clone_repo", fail)
    _, headers = await make_user()                              # no saved token: one attempt, then the final message
    repo, _ = await register_and_index(headers, git_repo)
    assert repo.status == "failed" and repo.error == CLONE_FAILED
    _assert_clean(repo.error)
