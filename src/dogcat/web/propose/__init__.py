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

    from starlette.middleware.base import BaseHTTPMiddleware

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Response:
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = WEB_CSP_HEADER
            return response

    app.add_middleware(SecurityHeadersMiddleware)

    from starlette.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    from dogcat.web.propose.routes import router

    app.include_router(router)

    return app


__all__ = ["ProposeAppState", "create_app"]
