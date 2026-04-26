"""Dogcat web server for inbox proposals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from dogcat.constants import (
    CSRF_COOKIE_MAX_AGE_SECONDS,
    ISSUES_FILENAME,
    WEB_CSP_HEADER,
)

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from dogcat.inbox import InboxStorage

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@dataclass
class ProposeAppState:
    """Typed bundle of values stored on ``app.state``.

    Replaces five separate ``app.state.<attr>`` writes (and the matching
    ``getattr(state, "name", default)`` reads scattered across the route
    module) with one named container. Mounted on ``app.state.dcat``;
    individual attributes are also kept on ``app.state`` for back-compat
    with existing route accesses while the migration proceeds.
    """

    dogcats_dir: str
    namespace: str
    namespaces: list[str]
    allow_creating_namespaces: bool
    templates: Jinja2Templates
    inbox: InboxStorage | None = None


# Maximum size of the pinned-namespaces list. A namespace-creation form
# bug or replay attack with --allow-creating-namespaces could otherwise
# grow this list unbounded. (dogcat-2icd)
MAX_PINNED_NAMESPACES = 100

# Single-use CSRF nonce TTL. After this window, an issued nonce is
# rejected even if not yet consumed. (dogcat-2icd)
CSRF_NONCE_TTL_SECONDS = 600

# Maximum POST body size (bytes) — the form needs only namespace + short
# title + 50 KB description + the CSRF token, so 256 KiB is a generous
# cap that still rejects multi-GB blow-ups before python-multipart
# materializes the body in memory. (dogcat-5zjh)
MAX_REQUEST_BODY_BYTES = 256 * 1024


# CSRF cookie lifetime. Tokens older than this are rejected even if the
# cookie still rides along — limits the window where a leaked token is
# usable. Tokens are also rotated on every successful POST. The unit-named
# constant (``..._SECONDS``) lives in :mod:`dogcat.constants`; this re-export
# keeps existing ``CSRF_COOKIE_MAX_AGE`` imports working.
CSRF_COOKIE_MAX_AGE = CSRF_COOKIE_MAX_AGE_SECONDS
CSRF_COOKIE_NAME = "dcat_csrf"


def create_app(
    dogcats_dir: str = ".dogcats",
    namespace: str | None = None,
    *,
    allow_creating_namespaces: bool = False,
) -> FastAPI:
    """Create a FastAPI app for submitting inbox proposals.

    Args:
        dogcats_dir: Path to the .dogcats directory.
        namespace: Override namespace (auto-detected if None).
        allow_creating_namespaces: Whether to allow creating new namespaces.

    Returns:
        Configured FastAPI application.
    """
    from dogcat.config import get_issue_prefix
    from dogcat.storage import JSONLStorage, get_namespaces

    resolved_namespace = namespace or get_issue_prefix(dogcats_dir)

    # Collect all namespaces from existing issues and inbox, primary first
    try:
        issues_path = str(Path(dogcats_dir) / ISSUES_FILENAME)
        storage = JSONLStorage(issues_path)
        from dogcat.storage import NamespaceCounts

        ns_counts = get_namespaces(storage, dogcats_dir=dogcats_dir)
        ns_counts.setdefault(resolved_namespace, NamespaceCounts())
        namespaces = sorted(ns_counts)
        # Move primary to front
        namespaces.remove(resolved_namespace)
        namespaces.insert(0, resolved_namespace)
    except Exception:
        namespaces = [resolved_namespace]

    app = FastAPI(
        title="dogcat propose",
        docs_url=None,
        redoc_url=None,
        # Disable the schema endpoint too — leaving it on at the
        # default /openapi.json discloses the full route + form-field
        # schema even when /docs and /redoc are disabled. (dogcat-6a5j)
        openapi_url=None,
    )

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Hold one InboxStorage on app state instead of constructing per request.
    # The constructor calls _load() which reads + parses the entire inbox
    # file; under per-request construction, submit latency grew linearly with
    # inbox size. Reload-on-mtime-change keeps the in-memory state fresh
    # without having to re-parse on every POST.
    from dogcat.inbox import InboxStorage

    inbox: InboxStorage | None
    try:
        inbox = InboxStorage(dogcats_dir=dogcats_dir)
    except (ValueError, RuntimeError):
        inbox = None

    state = ProposeAppState(
        dogcats_dir=dogcats_dir,
        namespace=resolved_namespace,
        namespaces=namespaces,
        allow_creating_namespaces=allow_creating_namespaces,
        templates=templates,
        inbox=inbox,
    )
    app.state.dcat = state
    # Mirror the dataclass fields onto app.state so existing route code
    # keeps working without a sweep. New code should reach for app.state.dcat.
    app.state.dogcats_dir = state.dogcats_dir
    app.state.namespace = state.namespace
    app.state.namespaces = state.namespaces
    app.state.allow_creating_namespaces = state.allow_creating_namespaces
    app.state.templates = state.templates
    app.state.inbox = state.inbox
    # Server-issued nonces, single-use within CSRF_NONCE_TTL_SECONDS.
    # Maps token (str) → expiry timestamp (float). Submitted POST tokens
    # must be present here, removed on consumption. (dogcat-2icd)
    app.state.csrf_nonces = {}

    from starlette.middleware.base import BaseHTTPMiddleware

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Response:
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = WEB_CSP_HEADER
            return response

    class BodySizeLimitMiddleware(BaseHTTPMiddleware):
        """Reject requests with a body larger than MAX_REQUEST_BODY_BYTES.

        Without this guard, python-multipart buffers the entire body
        before our Form-bound route fields run, so a single 10 GB
        request OOMs the server. Reject early via Content-Length and
        also stream-cap to catch chunked bodies that omit the header.
        (dogcat-5zjh)
        """

        async def dispatch(self, request: Request, call_next: Any) -> Response:
            from fastapi.responses import PlainTextResponse

            # Fast path: trust the Content-Length header when present.
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    parsed_length = int(content_length)
                except ValueError:
                    return PlainTextResponse("Bad Request", status_code=400)
                if parsed_length < 0:
                    return PlainTextResponse("Bad Request", status_code=400)
                if parsed_length > MAX_REQUEST_BODY_BYTES:
                    return PlainTextResponse("Payload Too Large", status_code=413)

            # Slow path for chunked bodies: wrap the receive callable so
            # we can count bytes as they arrive and abort once we cross
            # the limit, before the body is fully materialized.
            received_bytes = 0
            original_receive = request.receive

            async def cap_receive() -> Any:
                nonlocal received_bytes
                msg = await original_receive()
                if msg.get("type") == "http.request":
                    body = msg.get("body", b"")
                    received_bytes += len(body)
                    if received_bytes > MAX_REQUEST_BODY_BYTES:
                        return {"type": "http.disconnect"}
                return msg

            request._receive = cap_receive
            response = await call_next(request)
            if received_bytes > MAX_REQUEST_BODY_BYTES:
                return PlainTextResponse("Payload Too Large", status_code=413)
            return response

    # Order matters: body-size guard runs before security headers so
    # rejected requests still get the standard headers on their 413.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)

    from starlette.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    from dogcat.web.propose.routes import router

    app.include_router(router)

    return app


__all__ = ["ProposeAppState", "create_app"]
