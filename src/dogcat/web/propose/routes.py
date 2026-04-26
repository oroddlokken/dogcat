"""Routes for the dogcat web proposal server."""

from __future__ import annotations

import asyncio
import logging
import re as _re
import secrets
import unicodedata
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dogcat.constants import (
    MAX_DESC_LEN,
    MAX_NAMESPACE_LEN,
    MAX_TITLE_LEN,
    NAMESPACE_PATTERN,
    is_valid_namespace,
)
from dogcat.web.propose import (
    CSRF_COOKIE_MAX_AGE,
    CSRF_COOKIE_NAME,
    CSRF_NONCE_TTL_SECONDS,
    MAX_PINNED_NAMESPACES,
)

if TYPE_CHECKING:
    from starlette.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter()

# MAX_TITLE_LEN, MAX_DESC_LEN, MAX_NAMESPACE_LEN, NAMESPACE_PATTERN are
# imported from dogcat.constants — promoted there so CLI / IDGenerator
# can share the same namespace whitelist (rejects spaces, control chars,
# Unicode homoglyphs that would let a submitter spoof an existing
# namespace visually).
__all__ = (
    "MAX_DESC_LEN",
    "MAX_NAMESPACE_LEN",
    "MAX_TITLE_LEN",
    "NAMESPACE_PATTERN",
    "router",
)


def _normalize_namespace(value: str) -> str:
    """NFKC-normalize and strip whitespace from a namespace string.

    Normalization folds visually-equivalent Unicode forms (e.g. fullwidth
    ASCII) so the regex check sees the canonical representation.
    """
    return unicodedata.normalize("NFKC", value).strip()


def _is_valid_namespace(value: str) -> bool:
    """Return True if ``value`` is a well-formed namespace identifier."""
    return is_valid_namespace(value)


def _persist_pinned_namespace(dogcats_dir: str, namespace: str) -> None:
    """Append ``namespace`` to ``pinned_namespaces`` in config.local.toml.

    Pinned namespaces are picked up by ``get_namespaces()`` on the next app
    boot, so namespaces minted via the form survive a server restart instead
    of being held only in process memory.

    Caps the list at :data:`MAX_PINNED_NAMESPACES` so a replay attack on
    the create-namespace form cannot grow it unbounded. (dogcat-2icd)

    Serializes the read-modify-write under the same advisory file lock
    that storage and inbox use, so two concurrent web POSTs creating
    distinct new namespaces don't lose-update each other (dogcat-436f).
    The atomic save (dogcat-1s7e) covers the corruption side of the same
    race; the lock here covers the lost-update side.
    """
    from pathlib import Path as _Path

    from dogcat.config import load_local_config, save_local_config
    from dogcat.constants import LOCK_FILENAME
    from dogcat.locking import advisory_file_lock

    lock_path = _Path(dogcats_dir) / LOCK_FILENAME
    with advisory_file_lock(lock_path):
        config = load_local_config(dogcats_dir)
        pinned: list[str] = list(config.get("pinned_namespaces", []))
        if namespace in pinned:
            return
        if len(pinned) >= MAX_PINNED_NAMESPACES:
            msg = (
                f"pinned_namespaces is full ({MAX_PINNED_NAMESPACES} entries); "
                f"refusing to grow further."
            )
            raise ValueError(msg)
        pinned.append(namespace)
        config["pinned_namespaces"] = pinned
        save_local_config(dogcats_dir, config)


# Cookie token shape: secrets.token_urlsafe(32) yields ~43 chars from
# [A-Za-z0-9_-]; we accept anything that looks like that to reject a
# client-controlled empty/short cookie pair before reaching the
# compare_digest step. (dogcat-2icd)
_valid_token_re = _re.compile(r"^[A-Za-z0-9_-]{40,128}$")


def _is_valid_token_shape(value: str) -> bool:
    """Reject malformed CSRF tokens (wrong length / characters)."""
    return bool(_valid_token_re.fullmatch(value))


def _issue_nonce(request: Request) -> str:
    """Mint and register a fresh single-use CSRF nonce.

    The nonce is stored on ``app.state.csrf_nonces`` with an expiry
    timestamp; submit_proposal rejects tokens that aren't present (or
    are expired), and consumes the entry on a successful POST.
    """
    import time

    nonces: dict[str, float] = request.app.state.csrf_nonces
    # Opportunistically purge expired entries so the table doesn't grow
    # unbounded across long-running servers.
    now = time.time()
    expired = [tok for tok, exp in nonces.items() if exp < now]
    for tok in expired:
        nonces.pop(tok, None)
    token = secrets.token_urlsafe(32)
    nonces[token] = now + CSRF_NONCE_TTL_SECONDS
    return token


def _consume_nonce(request: Request, token: str) -> bool:
    """Single-use check: token must be registered and not expired."""
    import time

    if not _is_valid_token_shape(token):
        return False
    nonces: dict[str, float] = request.app.state.csrf_nonces
    expiry = nonces.pop(token, None)
    return expiry is not None and expiry > time.time()


def _origin_is_allowed(request: Request) -> bool:
    """Check Origin / Sec-Fetch-Site against an allowlist.

    The allowlist is the request host (host header) — same-origin only.
    Browsers send Origin on form POSTs; a missing Origin is allowed for
    CLI tools (curl, etc.) that won't pass the CSRF check anyway.
    """
    origin = request.headers.get("origin")
    if origin is None:
        # Sec-Fetch-Site is a defense-in-depth signal sent by modern browsers.
        site = request.headers.get("sec-fetch-site")
        return not (
            site is not None and site not in {"same-origin", "same-site", "none"}
        )
    host = request.headers.get("host", "")
    return origin.endswith("//" + host) if host else False


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
    from dogcat.inbox import InboxStorage

    inbox: InboxStorage | None = getattr(request.app.state, "inbox", None)
    dogcats_dir: str = request.app.state.dogcats_dir
    if inbox is None:
        inbox = InboxStorage(dogcats_dir=dogcats_dir)
    else:
        state_dict: dict[str, float] = getattr(request.app.state, "_inbox_stat", {})
        _refresh_inbox_if_stale(inbox, state_dict)
        request.app.state._inbox_stat = state_dict

    proposal = inbox.create_proposal(
        title=title,
        namespace=namespace,
        description=desc,
        proposed_by="web",
    )
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
    proposal_id_param = request.query_params.get("id")
    ns_param = request.query_params.get("namespace")
    if ns_param and ns_param in request.app.state.namespaces:
        namespace = ns_param

    # Look up the proposal title server-side rather than echoing the
    # query-string value, so a crafted ``/?submitted=true&id=...&title=evil``
    # URL cannot reflect attacker-controlled text into dogcat's brand
    # chrome. We only display the banner when the id resolves to a real
    # proposal in this app's inbox. (dogcat-khb5)
    proposal_title: str | None = None
    proposal_id: str | None = None
    if submitted and proposal_id_param:
        from dogcat.inbox import InboxStorage

        inbox: InboxStorage | None = getattr(request.app.state, "inbox", None)
        if inbox is None:
            try:
                inbox = InboxStorage(dogcats_dir=request.app.state.dogcats_dir)
            except (ValueError, RuntimeError):
                inbox = None
        if inbox is not None:
            proposal = inbox.get(proposal_id_param)
            if proposal is not None:
                proposal_id = proposal.full_id
                proposal_title = proposal.title

    # Always mint a fresh single-use nonce per GET. Reusing the previous
    # cookie value is unsafe because it would extend the replay window.
    # (dogcat-2icd)
    csrf_token = _issue_nonce(request)
    response = templates.TemplateResponse(
        request,
        "propose.html",
        _form_context(
            request,
            namespace,
            csrf_token,
            submitted=submitted and proposal_id is not None,
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
    # Defense layers (dogcat-2icd):
    # 1. Cookie + form token must be present, well-shaped, and equal.
    # 2. The token must be a server-issued nonce — single-use within
    #    CSRF_NONCE_TTL_SECONDS — so a captured pair cannot be replayed.
    # 3. Origin / Sec-Fetch-Site must be same-origin (or absent on a
    #    non-browser client, which still loses on the nonce check).
    csrf_ok = (
        bool(cookie_token)
        and bool(csrf_token)
        and _is_valid_token_shape(cookie_token)
        and _is_valid_token_shape(csrf_token)
        and hmac.compare_digest(cookie_token, csrf_token)
        and _origin_is_allowed(request)
        and _consume_nonce(request, csrf_token)
    )
    if not csrf_ok:
        # Issue a fresh single-use nonce so the rejected client gets a clean slate.
        new_token = _issue_nonce(request)
        rejected = templates.TemplateResponse(
            request,
            "propose.html",
            _form_context(
                request, namespace, new_token, error="Invalid form submission."
            ),
        )
        _issue_csrf_token(rejected, new_token)
        return rejected

    # On a successful CSRF check, mint a fresh nonce so the next form
    # submit gets a new single-use token. The previous nonce was consumed
    # by ``_consume_nonce`` above. (dogcat-2icd)
    session_token = _issue_nonce(request)

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

    # Pre-cap raw namespace BEFORE NFKC normalization or template
    # rendering. Without this, an attacker can submit a 5 MB namespace,
    # pay NFKC over the full payload, and get the body reflected back in
    # the error template (2x bandwidth amplification). Replace with a
    # placeholder so _render_error does not echo a multi-MB string.
    # (dogcat-1tbd)
    if len(namespace) > MAX_NAMESPACE_LEN * 4:
        # The form context echoes ``namespace`` back into the rendered
        # page — clamp the value before that happens.
        namespace = "<oversize>"
        return _render_error(
            f"Namespace must be 1-{MAX_NAMESPACE_LEN} ASCII letters, "
            f"digits, '-' or '_'."
        )

    namespace = _normalize_namespace(namespace)
    if not _is_valid_namespace(namespace):
        # On rejection, do not echo the (possibly attacker-controlled)
        # namespace value back into the form. (dogcat-1tbd)
        namespace = ""
        return _render_error(
            "Namespace must be 1-64 ASCII letters, digits, '-' or '_'."
        )

    valid_namespaces: list[str] = request.app.state.namespaces
    allow_creating: bool = getattr(
        request.app.state, "allow_creating_namespaces", False
    )
    is_new_namespace = namespace not in valid_namespaces
    if is_new_namespace and not allow_creating:
        return _render_error(f"Invalid namespace: {namespace}")

    dogcats_dir: str = request.app.state.dogcats_dir
    try:
        full_id, _ = await asyncio.to_thread(
            _create_proposal_sync, request, namespace, title, desc
        )
        logger.info("Proposal created: %s", full_id)
        # Mutate in-process state and persist AFTER a successful proposal
        # write — otherwise a failed write leaves the namespace in
        # ``valid_namespaces`` for the rest of the process lifetime, the
        # next submit's ``is_new_namespace`` check returns False, and the
        # namespace never makes it into ``pinned_namespaces`` (so it
        # vanishes on restart even though valid_namespaces remembers it).
        if is_new_namespace:
            valid_namespaces.append(namespace)
            try:
                await asyncio.to_thread(
                    _persist_pinned_namespace, dogcats_dir, namespace
                )
            except (ValueError, RuntimeError, OSError):
                # Roll back the in-process append so the next submit's
                # ``is_new_namespace`` check correctly classifies this
                # namespace as still-new — otherwise the namespace would
                # be invisible to the persisted pin layer for the rest of
                # the process lifetime, vanishing on restart while
                # silently passing the in-process validity check.
                # (dogcat-30jb)
                if namespace in valid_namespaces:
                    valid_namespaces.remove(namespace)
                raise
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
