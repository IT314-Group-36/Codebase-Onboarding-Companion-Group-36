"""Issue sync job: GitHub -> normalise -> one atomic swap.

A failed sync (rate limit, bad token, network) never wipes what an earlier sync stored: readers keep the old
issues and see the failure in the sync state. Saved OAuth credentials are resolved from the
repository owner at job execution; plaintext tokens are never stored in the issue cache or sync state.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_pipeline.github_issues import (
    GitHubError,
    IssuesDisabled,
    fetch_issues,
    normalize_issue,
    parse_owner_repo,
)
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Issue, IssueSync, Repository, User
from app.services.github import GitHubError as SavedCredentialError
from app.services.github import user_github_token

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=15)      # a job that never reported back must not block new syncs forever


async def mark_sync(session: AsyncSession, repo_id: int, *, status: str, message: str | None = None, **extra) -> None:
    """Create or update the repo's sync row (the caller commits)."""
    fields = {"status": status, "message": message, **extra}
    stmt = pg_insert(IssueSync).values(repo_id=repo_id, **fields)
    await session.execute(stmt.on_conflict_do_update(
        index_elements=[IssueSync.repo_id], set_={**fields, "updated_at": func.now()}))


def sync_in_progress(row: IssueSync | None, now: datetime | None = None) -> bool:
    if row is None or row.status not in ("queued", "syncing"):
        return False
    return (now or datetime.now(timezone.utc)) - row.updated_at < STALE_AFTER


def sync_view(row: IssueSync | None) -> dict:
    if row is None:
        return {"status": "never", "message": None, "fetched": 0, "synced_at": None}
    return {"status": row.status, "message": row.message, "fetched": row.fetched, "synced_at": row.synced_at}


async def _finish_failed(repo_id: int, message: str) -> None:
    async with SessionLocal() as s:
        await mark_sync(s, repo_id, status="failed", message=message)
        await s.commit()


async def _store(repo_id: int, rows: list[dict], message: str | None) -> None:
    """Replace the repo's issues atomically: readers see the old list until this commits."""
    async with SessionLocal() as s, s.begin():
        await s.execute(delete(Issue).where(Issue.repo_id == repo_id))
        if rows:
            await s.execute(insert(Issue), [{**r, "repo_id": repo_id} for r in rows])
        await mark_sync(s, repo_id, status="ok", message=message, fetched=len(rows), synced_at=func.now())


async def run_issue_sync(repo_id: int, access_token: str | None = None) -> None:
    cfg = get_settings()
    async with SessionLocal() as s:
        repo = await s.get(Repository, repo_id)
        if repo is None:
            return
        url = repo.url
        owner_id = repo.owner_id
        await mark_sync(s, repo_id, status="syncing", message=None)
        await s.commit()
    try:
        target = parse_owner_repo(url)
        if target is None:
            await _finish_failed(repo_id, "Issues can only be fetched for repositories hosted on github.com.")
            return
        token, using_saved = access_token, False
        if not token and owner_id is not None:
            async with SessionLocal() as s:
                owner = await s.get(User, owner_id)
            if owner is not None and owner.encrypted_access_token:
                # Decrypt only inside the job, not in the route or queue arguments.
                # An unreadable saved credential must fail, not switch identities.
                token = user_github_token(owner)
                if not token:
                    raise SavedCredentialError("Your saved GitHub sign-in is empty. Sign in with GitHub again.", "reauth")
                using_saved = True
        token = token or cfg.github_token or None
        try:
            raw = await asyncio.to_thread(
                fetch_issues, *target, token, cfg.issue_labels, api_url=cfg.github_api_url,
                max_pages=cfg.issue_max_pages, timeout=cfg.issue_timeout_seconds)
        except IssuesDisabled as e:                       # the old issues are gone for good: store the empty result
            await _store(repo_id, [], str(e).replace(token, "***") if token else str(e))
            return
        except GitHubError as e:                          # keep the previous issues, report why
            message = str(e)
            if using_saved:
                if e.kind == "reauth":
                    message = "GitHub rejected your saved sign-in. Sign in with GitHub again, then retry issue sync."
                elif e.kind in ("not_found", "forbidden"):
                    message = ("GitHub could not grant access to this repository's issues with your saved sign-in. "
                               "Check your repository permissions and organization OAuth app approval. "
                               "If your authorization has changed, sign in with GitHub again, then retry.")
                elif e.kind == "rate_limit":
                    message = "GitHub API rate limit reached for your account. Please try syncing again later."
            await _finish_failed(repo_id, message.replace(token, "***") if token else message)
            return
        rows = [normalize_issue(r) for r in raw]
        note = None if rows else "No open issues carry any of these labels: " + ", ".join(cfg.issue_labels) + "."
        await _store(repo_id, rows, note)
    except SavedCredentialError as e:
        await _finish_failed(repo_id, str(e))
    except Exception:  # noqa: BLE001
        # Unexpected upstream exceptions can contain Authorization credentials.
        log.error("issue sync for repo %s failed unexpectedly", repo_id)
        try:
            await _finish_failed(repo_id, "Unexpected error while syncing issues. Please try again.")
        except Exception:  # noqa: BLE001
            log.exception("could not record the sync failure for repo %s", repo_id)
