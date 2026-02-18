"""Routes for the dogcat web proposal server."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_TITLE_LEN = 500
MAX_DESC_LEN = 50_000


def _form_context(
    request: Request,
    namespace: str,
    *,
    submitted: bool = False,
    error: str | None = None,
    proposal_title: str | None = None,
) -> dict[str, object]:
    """Build the template context dict for propose.html."""
    namespaces: list[str] = request.app.state.namespaces
    allow_creating_namespaces: bool = getattr(
        request.app.state, "allow_creating_namespaces", True
    )
    ctx: dict[str, object] = {
        "request": request,
        "namespace": namespace,
        "namespaces": namespaces,
        "allow_creating_namespaces": allow_creating_namespaces,
        "csrf_token": request.app.state.csrf_token,
        "submitted": submitted,
        "error": error,
    }
    if proposal_title is not None:
        ctx["proposal_title"] = proposal_title
    return ctx


@router.get("/", response_class=HTMLResponse)
async def propose_form(request: Request) -> HTMLResponse:
    """Render the proposal submission form."""
    templates = request.app.state.templates
    namespace = request.app.state.namespace
    submitted = request.query_params.get("submitted") == "true"
    proposal_title = request.query_params.get("title")
    return templates.TemplateResponse(
        request,
        "propose.html",
        _form_context(
            request,
            namespace,
            submitted=submitted,
            proposal_title=proposal_title,
        ),
    )


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
    dogcats_dir: str = request.app.state.dogcats_dir

    expected_token: str = request.app.state.csrf_token
    if not hmac.compare_digest(csrf_token, expected_token):
        return templates.TemplateResponse(
            request,
            "propose.html",
            _form_context(request, namespace, error="Invalid form submission."),
        )

    title = title.strip()
    desc: str | None = description.strip() or None

    if not title:
        return templates.TemplateResponse(
            request,
            "propose.html",
            _form_context(request, namespace, error="Title is required."),
        )

    if len(title) > MAX_TITLE_LEN:
        return templates.TemplateResponse(
            request,
            "propose.html",
            _form_context(
                request,
                namespace,
                error=f"Title must be {MAX_TITLE_LEN} characters or fewer.",
            ),
        )

    if desc and len(desc) > MAX_DESC_LEN:
        return templates.TemplateResponse(
            request,
            "propose.html",
            _form_context(
                request,
                namespace,
                error=f"Description must be {MAX_DESC_LEN} characters or fewer.",
            ),
        )

    valid_namespaces: list[str] = request.app.state.namespaces
    allow_creating: bool = getattr(request.app.state, "allow_creating_namespaces", True)
    if namespace not in valid_namespaces:
        if not allow_creating:
            return templates.TemplateResponse(
                request,
                "propose.html",
                _form_context(
                    request,
                    namespace,
                    error=f"Invalid namespace: {namespace}",
                ),
            )
        # Accept new namespace — add it to the known list for this session
        valid_namespaces.append(namespace)

    try:
        from dogcat.idgen import IDGenerator
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        inbox = InboxStorage(dogcats_dir=dogcats_dir)
        id_gen = IDGenerator(
            existing_ids=inbox.get_proposal_ids(),
            prefix=f"{namespace}-inbox",
        )
        proposal_id = id_gen.generate_proposal_id(
            title,
            namespace=f"{namespace}-inbox",
        )
        proposal = Proposal(
            id=proposal_id,
            title=title,
            namespace=namespace,
            description=desc,
            proposed_by="web",
        )
        inbox.create(proposal)
        logger.info("Proposal created: %s", proposal.full_id)
    except (ValueError, RuntimeError, OSError):
        logger.exception("Failed to create proposal")
        return templates.TemplateResponse(
            request,
            "propose.html",
            _form_context(request, namespace, error="Failed to submit proposal."),
        )

    query = urlencode({"submitted": "true", "title": title})
    return RedirectResponse(url=f"/?{query}", status_code=303)
