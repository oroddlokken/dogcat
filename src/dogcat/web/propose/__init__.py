"""Dogcat web server for inbox proposals."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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
        issues_path = str(Path(dogcats_dir) / "issues.jsonl")
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

    app.state.dogcats_dir = dogcats_dir
    app.state.namespace = resolved_namespace
    app.state.namespaces = namespaces
    app.state.allow_creating_namespaces = allow_creating_namespaces
    app.state.csrf_token = secrets.token_urlsafe(32)
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    from starlette.middleware.base import BaseHTTPMiddleware

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Response:
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'self'; script-src 'unsafe-inline'"
            )
            return response

    app.add_middleware(SecurityHeadersMiddleware)

    from starlette.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    from dogcat.web.propose.routes import router

    app.include_router(router)

    return app


__all__ = ["create_app"]
