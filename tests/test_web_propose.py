"""Tests for the web propose server."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from fastapi.testclient import TestClient

from dogcat.config import save_config
from dogcat.inbox import InboxStorage
from dogcat.storage import JSONLStorage
from dogcat.web.propose import create_app


@pytest.fixture
def web_dogcats(tmp_path: Path) -> Path:
    """Create a .dogcats directory with config and empty storage files."""
    dogcats = tmp_path / ".dogcats"
    dogcats.mkdir()
    (dogcats / "issues.jsonl").touch()
    (dogcats / "inbox.jsonl").touch()
    save_config(str(dogcats), {"namespace": "testns"})
    return dogcats


@pytest.fixture
def web_dogcats_multi_ns(tmp_path: Path) -> Path:
    """Create a .dogcats directory with issues in multiple namespaces."""
    dogcats = tmp_path / ".dogcats"
    dogcats.mkdir()
    (dogcats / "inbox.jsonl").touch()

    from dogcat.models import Issue

    storage = JSONLStorage(str(dogcats / "issues.jsonl"), create_dir=True)
    storage.create(Issue(id="aaa", title="Issue A", namespace="alpha"))
    storage.create(Issue(id="bbb", title="Issue B", namespace="beta"))
    storage.create(Issue(id="ccc", title="Issue C", namespace="alpha"))
    save_config(str(dogcats), {"namespace": "alpha"})
    return dogcats


@pytest.fixture
def client(web_dogcats: Path) -> TestClient:
    """Create a test client for the propose web app."""
    app = create_app(dogcats_dir=str(web_dogcats))
    return TestClient(app)


def _csrf(client: TestClient) -> str:
    """Extract the CSRF token from the app state."""
    return client.app.state.csrf_token  # type: ignore[union-attr]


class TestGetForm:
    """Tests for GET / (the proposal form)."""

    def test_form_renders(self, client: TestClient) -> None:
        """The form page renders successfully."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "propose" in resp.text

    def test_form_has_namespace_dropdown(self, client: TestClient) -> None:
        """The form contains the namespace dropdown."""
        resp = client.get("/")
        assert 'data-value="testns"' in resp.text

    def test_form_has_title_input(self, client: TestClient) -> None:
        """The form contains the title input."""
        resp = client.get("/")
        assert 'name="title"' in resp.text

    def test_form_has_description_textarea(self, client: TestClient) -> None:
        """The form contains the description textarea."""
        resp = client.get("/")
        assert 'name="description"' in resp.text

    def test_form_has_submit_button(self, client: TestClient) -> None:
        """The form contains the submit button."""
        resp = client.get("/")
        assert "Submit proposal" in resp.text


class TestNamespacePopulation:
    """Tests for namespace dropdown population."""

    def test_default_namespace_selected(self, client: TestClient) -> None:
        """The primary namespace is marked as active."""
        resp = client.get("/")
        assert "dropdown-item active" in resp.text
        assert 'data-value="testns"' in resp.text

    def test_multiple_namespaces(self, web_dogcats_multi_ns: Path) -> None:
        """All namespaces from issues appear in the dropdown."""
        app = create_app(dogcats_dir=str(web_dogcats_multi_ns))
        client = TestClient(app)
        resp = client.get("/")
        assert 'data-value="alpha"' in resp.text
        assert 'data-value="beta"' in resp.text

    def test_primary_namespace_first(self, web_dogcats_multi_ns: Path) -> None:
        """The primary namespace appears first in the dropdown."""
        app = create_app(dogcats_dir=str(web_dogcats_multi_ns))
        client = TestClient(app)
        resp = client.get("/")
        alpha_pos = resp.text.index('data-value="alpha"')
        beta_pos = resp.text.index('data-value="beta"')
        assert alpha_pos < beta_pos

    def test_namespace_override(self, web_dogcats: Path) -> None:
        """An explicit namespace override is used."""
        app = create_app(dogcats_dir=str(web_dogcats), namespace="custom")
        client = TestClient(app)
        resp = client.get("/")
        assert 'data-value="custom"' in resp.text


class TestSubmitProposal:
    """Tests for POST / (proposal submission)."""

    def test_submit_creates_proposal(
        self, client: TestClient, web_dogcats: Path
    ) -> None:
        """Submitting creates a proposal in the inbox."""
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "My proposal",
                "description": "Details",
            },
        )
        assert resp.status_code == 200
        assert "Proposal submitted" in resp.text
        assert "My proposal" in resp.text

        # Verify it landed in inbox storage
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        proposals = inbox.list()
        assert len(proposals) == 1
        assert proposals[0].title == "My proposal"
        assert proposals[0].namespace == "testns"
        assert proposals[0].description == "Details"
        assert proposals[0].proposed_by == "web"

    def test_submit_empty_title_shows_error(self, client: TestClient) -> None:
        """Submitting with an empty title shows an error."""
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "  ",
                "description": "",
            },
        )
        assert resp.status_code == 200
        assert "Title is required" in resp.text

    def test_submit_no_description(self, client: TestClient, web_dogcats: Path) -> None:
        """Submitting without a description sets it to None."""
        client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "No desc",
                "description": "",
            },
        )
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        proposals = inbox.list()
        assert len(proposals) == 1
        assert proposals[0].description is None

    def test_submit_strips_title(self, client: TestClient, web_dogcats: Path) -> None:
        """Title whitespace is stripped."""
        client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "  Padded title  ",
                "description": "",
            },
        )
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        proposals = inbox.list()
        assert proposals[0].title == "Padded title"

    def test_submit_multiple_proposals(
        self, client: TestClient, web_dogcats: Path
    ) -> None:
        """Multiple proposals can be submitted."""
        token = _csrf(client)
        client.post(
            "/",
            data={
                "csrf_token": token,
                "namespace": "testns",
                "title": "First",
                "description": "",
            },
        )
        client.post(
            "/",
            data={
                "csrf_token": token,
                "namespace": "testns",
                "title": "Second",
                "description": "",
            },
        )
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        proposals = inbox.list()
        assert len(proposals) == 2
        titles = {p.title for p in proposals}
        assert titles == {"First", "Second"}

    def test_submit_different_namespace(self, web_dogcats_multi_ns: Path) -> None:
        """A proposal can be submitted to a non-default namespace."""
        app = create_app(dogcats_dir=str(web_dogcats_multi_ns))
        multi_client = TestClient(app)
        token: str = app.state.csrf_token
        multi_client.post(
            "/",
            data={
                "csrf_token": token,
                "namespace": "beta",
                "title": "Cross-ns",
                "description": "",
            },
        )
        inbox = InboxStorage(dogcats_dir=str(web_dogcats_multi_ns))
        proposals = inbox.list()
        assert proposals[0].namespace == "beta"

    def test_submit_invalid_namespace_when_disallowed(self, web_dogcats: Path) -> None:
        """Submitting to an invalid namespace errors when disabled."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=False)
        restricted_client = TestClient(app)
        resp = restricted_client.post(
            "/",
            data={
                "csrf_token": app.state.csrf_token,
                "namespace": "bogus",
                "title": "Bad ns",
                "description": "",
            },
        )
        assert resp.status_code == 200
        assert "Invalid namespace" in resp.text

    def test_submit_new_namespace_when_allowed(
        self, client: TestClient, web_dogcats: Path
    ) -> None:
        """Submitting to a new namespace succeeds when creation is allowed (default)."""
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "newproject",
                "title": "New ns proposal",
                "description": "",
            },
        )
        assert resp.status_code == 200
        assert "Proposal submitted" in resp.text

        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        proposals = inbox.list()
        assert any(p.namespace == "newproject" for p in proposals)

    def test_submit_redirects_with_303(self, client: TestClient) -> None:
        """Successful POST returns a 303 redirect (Post/Redirect/Get)."""
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "PRG test",
                "description": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "submitted=true" in resp.headers["location"]
        assert "title=PRG+test" in resp.headers["location"]

    def test_get_with_submitted_shows_success(self, client: TestClient) -> None:
        """GET /?submitted=true&title=X shows the success message."""
        resp = client.get("/?submitted=true&title=My+proposal")
        assert resp.status_code == 200
        assert "Proposal submitted" in resp.text
        assert "My proposal" in resp.text


class TestAppFactory:
    """Tests for the create_app factory."""

    def test_docs_disabled(self, web_dogcats: Path) -> None:
        """OpenAPI docs endpoints are disabled."""
        app = create_app(dogcats_dir=str(web_dogcats))
        client = TestClient(app)
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404

    def test_default_namespace_autodetected(self, web_dogcats: Path) -> None:
        """Namespace is auto-detected from config."""
        app = create_app(dogcats_dir=str(web_dogcats))
        assert app.state.namespace == "testns"

    def test_namespace_override(self, web_dogcats: Path) -> None:
        """Explicit namespace overrides config."""
        app = create_app(dogcats_dir=str(web_dogcats), namespace="override")
        assert app.state.namespace == "override"

    def test_default_port_constant(self) -> None:
        """The default port constant is set."""
        from dogcat.cli._cmd_web import DEFAULT_PORT

        assert DEFAULT_PORT == 48042

    def test_allow_creating_namespaces_default(self, web_dogcats: Path) -> None:
        """By default allow_creating_namespaces is True."""
        app = create_app(dogcats_dir=str(web_dogcats))
        assert app.state.allow_creating_namespaces is True

    def test_allow_creating_namespaces_false(self, web_dogcats: Path) -> None:
        """Explicit False is stored in app state."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=False)
        assert app.state.allow_creating_namespaces is False

    def test_form_shows_new_option_when_allowed(self, web_dogcats: Path) -> None:
        """Form includes 'New...' dropdown item when namespace creation is allowed."""
        app = create_app(dogcats_dir=str(web_dogcats))
        client = TestClient(app)
        resp = client.get("/")
        assert "New&hellip;" in resp.text

    def test_form_hides_new_option_when_disallowed(self, web_dogcats: Path) -> None:
        """Form omits 'New...' dropdown item when namespace creation is disabled."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=False)
        client = TestClient(app)
        resp = client.get("/")
        assert "New&hellip;" not in resp.text
