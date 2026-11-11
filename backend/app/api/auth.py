"""GitHub sign-in (OAuth web flow) and the session cookie.

browser -> GET /auth/github/login  -> github.com authorize page
        <- GET /auth/github/callback?code&state   (we verify `state`, trade the code for a token, store it
                                                    encrypted, set the signed session cookie, redirect to the frontend)
The frontend then calls GET /auth/me to learn who is signed in.
"""
import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_github_client
from app.core.config import get_settings
from app.core.security import SecurityConfigError, config_problem, create_session_token, encrypt_token
from app.db.session import get_session
from app.models import User
from app.schemas import MeOut
from app.services.github import GitHubClient, GitHubError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
STATE_COOKIE = "oauth_state"
STATE_TTL_SECONDS = 600
# Only these GitHub error codes are passed on to the frontend; anything else is shown as a generic error so a crafted
# callback link cannot put arbitrary text on our page.
PASS_THROUGH_ERRORS = {"access_denied"}


def login_enabled() -> bool:
    return get_settings().github_oauth_configured and config_problem() is None


def _to_frontend(error: str | None = None, message: str | None = None) -> RedirectResponse:
    url = get_settings().frontend_url.rstrip("/") + "/auth/callback"
    if error:
        url += "?" + urlencode({"error": error, "error_description": message or ""})
    return RedirectResponse(url, status_code=302)


def _fail(error: str, message: str) -> RedirectResponse:
    resp = _to_frontend(error, message)
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


@router.get("/config")
async def auth_config():
    return {"github_login_enabled": login_enabled()}


@router.get("/github/login")
async def github_login(github: GitHubClient = Depends(get_github_client)):
    if not login_enabled():
        return _to_frontend("not_configured", "GitHub sign-in is not set up on this server yet. Ask the project owner to configure it.")
    cfg = get_settings()
    state = secrets.token_urlsafe(32)
    resp = RedirectResponse(github.authorize_url(state), status_code=302)
    resp.set_cookie(STATE_COOKIE, state, max_age=STATE_TTL_SECONDS, httponly=True, secure=cfg.cookie_secure,
                    samesite="lax", path="/")
    return resp


async def _upsert_user(session: AsyncSession, gh: dict, token: str, scopes: str) -> User:
    for attempt in (1, 2):                                      # a double-click can race two first logins; retry once
        user = (await session.execute(select(User).where(User.github_id == gh["id"]))).scalar_one_or_none()
        if user is None:
            user = User(github_id=gh["id"], login=gh["login"])
            session.add(user)
        user.login = gh["login"]
        user.name, user.email, user.avatar_url = gh.get("name"), gh.get("email"), gh.get("avatar_url")
        user.encrypted_access_token = encrypt_token(token)
        user.token_scopes = scopes
        try:
            await session.commit()
            return user
        except IntegrityError:
            await session.rollback()
            if attempt == 2:
                raise
    raise RuntimeError("unreachable")


@router.get("/github/callback")
async def github_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
                          session: AsyncSession = Depends(get_session), github: GitHubClient = Depends(get_github_client)):
    expected = request.cookies.get(STATE_COOKIE)
    if error:                                                   # e.g. the user clicked "Cancel" on GitHub
        return _fail(error if error in PASS_THROUGH_ERRORS else "github_error", "GitHub sign-in was cancelled or failed.")
    if not expected or not state or not secrets.compare_digest(expected, state):
        return _fail("invalid_state", "The sign-in link expired or was not started here. Please try again.")
    if not code:
        return _fail("missing_code", "GitHub did not send a sign-in code. Please try again.")
    try:
        token, scopes = await github.exchange_code(code)
        gh = await github.get_user(token)
        user = await _upsert_user(session, gh, token, scopes)
    except GitHubError as e:
        return _fail("github_error", str(e))
    except SecurityConfigError:
        log.exception("login secrets are misconfigured")
        return _fail("server_misconfigured", "The server's sign-in settings are invalid. Ask the project owner.")
    cfg = get_settings()
    resp = _to_frontend()
    resp.delete_cookie(STATE_COOKIE, path="/")
    resp.set_cookie(cfg.session_cookie_name, create_session_token(user.id), max_age=cfg.session_ttl_seconds,
                    httponly=True, secure=cfg.cookie_secure, samesite="lax", path="/")
    return resp


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user)):
    return MeOut(id=user.id, github_id=user.github_id, login=user.login, name=user.name, email=user.email,
                 avatar_url=user.avatar_url, github_connected=bool(user.encrypted_access_token),
                 token_scopes=user.token_scopes)


@router.post("/logout")
async def logout():
    # SameSite=Lax cookies are not sent on cross-site POSTs, so another website cannot trigger this (or any other POST) for you.
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(get_settings().session_cookie_name, path="/")
    return resp
