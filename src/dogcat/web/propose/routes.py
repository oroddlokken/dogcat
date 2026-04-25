"""Routes for the dogcat web proposal server."""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import unicodedata
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dogcat.web.propose import CSRF_COOKIE_MAX_AGE, CSRF_COOKIE_NAME

if TYPE_CHECKING:
    from starlette.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_TITLE_LEN = 500
MAX_DESC_LEN = 50_000
# Namespace whitelist: ASCII letters, digits, underscore, hyphen.
# Matches the format used by issue-id prefixes throughout the codebase
# and rejects spaces, control characters, and Unicode homoglyphs that
# would let a submitter spoof an existing namespace visually.
MAX_NAMESPACE_LEN = 64
NAMESPACE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _normalize_namespace(value: str) -> str:
    """NFKC-normalize and strip whitespace from a namespace string.

    Normalization folds visually-equivalent Unicode forms (e.g. fullwidth
    ASCII) so the regex check sees the canonical representation.
    """
    return unicodedata.normalize("NFKC", value).strip()


def _is_valid_namespace(value: str) -> bool:
    """Return True if ``value`` is a well-formed namespace identifier."""
    return (
        bool(value)
        and len(value) <= MAX_NAMESPACE_LEN
        and bool(NAMESPACE_PATTERN.fullmatch(value))
    )


def _persist_pinned_namespace(dogcats_dir: str, namespace: str) -> None:
    """Append ``namespace`` to ``pinned_namespaces`` in config.local.toml.

    Pinned namespaces are picked up by ``get_namespaces()`` on the next app
    boot, so namespaces minted via the form survive a server restart instead
    of being held only in process memory.
    """
    from dogcat.config import load_local_config, save_local_config

    config = load_local_config(dogcats_dir)
    pinned: list[str] = list(config.get("pinned_namespaces", []))
    if namespace in pinned:
        return
    pinned.append(namespace)
    config["pinned_namespaces"] = pinned
    save_local_config(dogcats_dir, config)


def _refresh_inbox_if_stale(inbox: object, inbox_path_state: dict[str, float]) -> None:
    """Reload the cached InboxStorage if the file changed since last reload.

    Stat is cheap; reload is also cheap until inbox grows large. Either way
    skipping the per-request reload when nothing changed is the win.
    """
    from dogcat.inbox import InboxStorage

    if not isinstance(inbox, InboxStorage):
        return
    try:
        mtime = inbox.path.stat().st_mtime
        size = inbox.path.stat().st_size
    except OSError:
        return
    cached = inbox_path_state.get("mtime")
    cached_size = inbox_path_state.get("size")
    if cached == mtime and cached_size == size:
        return
    try:
        inbox.reload()
    except (ValueError, RuntimeError, OSError):
        return
    inbox_path_state["mtime"] = mtime
    inbox_path_state["size"] = size


def _create_proposal_sync(
    request: Request, namespace: str, title: str, desc: str | None
) -> tuple[str, str]:
    """Blocking inbox write — returns (full_id, namespace) for the new proposal.

    Uses the persistent ``app.state.inbox`` when present, falling back to a
    fresh constructor only when the app was built without one (e.g. older
    create_app override or hand-built test app). Reload-on-mtime keeps the
    cached state fresh after CLI/other-process writes.
    """
    from dogcat.idgen import IDGenerator
    from dogcat.inbox import InboxStorage
    from dogcat.models import Proposal

    inbox: InboxStorage | None = getattr(request.app.state, "inbox", None)
    dogcats_dir: str = request.app.state.dogcats_dir
    if inbox is None:
        inbox = InboxStorage(dogcats_dir=dogcats_dir)
    else:
        state_dict: dict[str, float] = getattr(request.app.state, "_inbox_stat", {})
        _refresh_inbox_if_stale(inbox, state_dict)
        request.app.state._inbox_stat = state_dict

    id_gen = IDGenerator(
        existing_ids=inbox.get_proposal_ids(),
        prefix=f"{namespace}-inbox",
    )
    proposal_id = id_gen.generate_proposal_id(title, namespace=f"{namespace}-inbox")
    proposal = Proposal(
        id=proposal_id,
        title=title,
        namespace=namespace,
        description=desc,
        proposed_by="web",
    )
    inbox.create(proposal)
    return proposal.full_id, proposal.namespace


def _issue_csrf_token(response: Response, token: str) -> None:
    """Set the CSRF cookie on a response, refreshing its expiry."""
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=CSRF_COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
    )


def _form_context(
    request: Request,
    namespace: str,
    csrf_token: str,
    *,
    submitted: bool = False,
    error: str | None = None,
    proposal_title: str | None = None,
    proposal_id: str | None = None,
) -> dict[str, object]:
    """Build the template context dict for propose.html."""
    namespaces: list[str] = request.app.state.namespaces
    allow_creating_namespaces: bool = getattr(
        request.app.state, "allow_creating_namespaces", False
    )
    ctx: dict[str, object] = {
        "request": request,
        "namespace": namespace,
        "namespaces": namespaces,
        "allow_creating_namespaces": allow_creating_namespaces,
        "csrf_token": csrf_token,
        "submitted": submitted,
        "error": error,
    }
    if proposal_title is not None:
        ctx["proposal_title"] = proposal_title
    if proposal_id is not None:
        ctx["proposal_id"] = proposal_id
    return ctx


@router.get("/", response_class=HTMLResponse)
async def propose_form(request: Request) -> HTMLResponse:
    """Render the proposal submission form."""
    templates = request.app.state.templates
    namespace = request.app.state.namespace
    submitted = request.query_params.get("submitted") == "true"
    proposal_title = request.query_params.get("title")
    proposal_id = request.query_params.get("id")
    ns_param = request.query_params.get("namespace")
    if ns_param and ns_param in request.app.state.namespaces:
        namespace = ns_param

    csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or secrets.token_urlsafe(32)
    response = templates.TemplateResponse(
        request,
        "propose.html",
        _form_context(
            request,
            namespace,
            csrf_token,
            submitted=submitted,
            proposal_title=proposal_title,
            proposal_id=proposal_id,
        ),
    )
    _issue_csrf_token(response, csrf_token)
    return response


@router.post("/", response_model=None)
async def submit_proposal(
    request: Request,
    namespace: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    csrf_token: str = Form(""),
) -> HTMLResponse | RedirectResponse:
    """Handle proposal form submission via InboxStorage."""
    import hmac

    templates = request.app.state.templates

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    # Both must be present and equal — empty strings are rejected even if
    # equal so a client without a session cookie can't slip through.
    csrf_ok = (
        bool(cookie_token)
        and bool(csrf_token)
        and hmac.compare_digest(cookie_token, csrf_token)
    )
    if not csrf_ok:
        # Issue a fresh token so the rejected client gets a clean slate.
        new_token = secrets.token_urlsafe(32)
        rejected = templates.TemplateResponse(
            request,
            "propose.html",
            _form_context(
                request, namespace, new_token, error="Invalid form submission."
            ),
        )
        _issue_csrf_token(rejected, new_token)
        return rejected

    # On a successful CSRF check, keep the existing per-session token —
    # rotating per request breaks multi-tab use without strengthening the
    # protection (cookie already scopes the token to this browser session).
    session_token = cookie_token

    def _render_error(message: str) -> HTMLResponse:
        resp = templates.TemplateResponse(
            request,
            "propose.html",
            _form_context(request, namespace, session_token, error=message),
        )
        _issue_csrf_token(resp, session_token)
        return resp

    title = title.strip()
    desc: str | None = description.strip() or None

    if not title:
        return _render_error("Title is required.")

    if len(title) > MAX_TITLE_LEN:
        return _render_error(f"Title must be {MAX_TITLE_LEN} characters or fewer.")

    if desc and len(desc) > MAX_DESC_LEN:
        return _render_error(f"Description must be {MAX_DESC_LEN} characters or fewer.")

    namespace = _normalize_namespace(namespace)
    if not _is_valid_namespace(namespace):
        return _render_error(
            "Namespace must be 1-64 ASCII letters, digits, '-' or '_'."
        )

    valid_namespaces: list[str] = request.app.state.namespaces
    allow_creating: bool = getattr(
        request.app.state, "allow_creating_namespaces", False
    )
    is_new_namespace = namespace not in valid_namespaces
    if is_new_namespace:
        if not allow_creating:
            return _render_error(f"Invalid namespace: {namespace}")
        # Accept new namespace — add it to the known list for this session
        valid_namespaces.append(namespace)

    dogcats_dir: str = request.app.state.dogcats_dir
    try:
        full_id, _ = await asyncio.to_thread(
            _create_proposal_sync, request, namespace, title, desc
        )
        logger.info("Proposal created: %s", full_id)
        # Persist the namespace AFTER a successful proposal write — no point
        # pinning a namespace that failed to land any record.
        if is_new_namespace:
            await asyncio.to_thread(_persist_pinned_namespace, dogcats_dir, namespace)
    except (ValueError, RuntimeError, OSError):
        logger.exception("Failed to create proposal")
        return _render_error("Failed to submit proposal.")

    query = urlencode(
        {
            "submitted": "true",
            "id": full_id,
            "title": title,
            "namespace": namespace,
        }
    )
    redirect = RedirectResponse(url=f"/?{query}", status_code=303)
    _issue_csrf_token(redirect, session_token)
    return redirect
