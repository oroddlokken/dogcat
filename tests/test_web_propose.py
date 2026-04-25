"""Tests for the web propose server."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path
from fastapi.testclient import TestClient

from dogcat.cli import app as cli_app
from dogcat.config import save_config
from dogcat.inbox import InboxStorage
from dogcat.storage import JSONLStorage
from dogcat.web.propose import create_app

runner = CliRunner()


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
    """Prime a CSRF session via GET /, return the issued token.

    Side effects: sets the ``dcat_csrf`` cookie on the client. Tests that
    submit the form should call this once per client to establish a session.
    """
    import re

    resp = client.get("/")
    match = re.search(r'name="csrf_token" value="([^"]+)"', resp.text)
    assert match, "CSRF token not found in form HTML"
    return match.group(1)


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

    def test_form_has_home_link(self, client: TestClient) -> None:
        """The header links back to /."""
        resp = client.get("/")
        assert '<a href="/">' in resp.text

    def test_csp_disallows_inline_script(self, client: TestClient) -> None:
        """CSP must not include 'unsafe-inline' for script-src.

        Inline JS allows trivially bypassing XSS protection. The form's JS
        is served from /static/js/propose.js so 'self' is enough.
        """
        resp = client.get("/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "script-src" in csp
        assert "unsafe-inline" not in csp
        assert "script-src 'self'" in csp

    def test_x_content_type_options_header(self, client: TestClient) -> None:
        """The nosniff header is set on responses.

        Without this header, a browser may sniff a response body for
        executable content and bypass the declared content-type.
        """
        resp = client.get("/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options_header(self, client: TestClient) -> None:
        """The X-Frame-Options DENY header is set on responses.

        Without this header, the form could be rendered inside an attacker
        frame and used for clickjacking against the namespace dropdown or
        submit button.
        """
        resp = client.get("/")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_no_inline_script_tag(self, client: TestClient) -> None:
        """Form HTML loads JS via external src — no inline <script> body."""
        resp = client.get("/")
        # External script tag is present, but its body must be empty.
        assert "static/js/propose.js" in resp.text
        # No inline IIFE remains.
        assert "function()" not in resp.text


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
        multi_client.post(
            "/",
            data={
                "csrf_token": _csrf(multi_client),
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
                "csrf_token": _csrf(restricted_client),
                "namespace": "bogus",
                "title": "Bad ns",
                "description": "",
            },
        )
        assert resp.status_code == 200
        assert "Invalid namespace" in resp.text

    def test_submit_new_namespace_when_allowed(self, web_dogcats: Path) -> None:
        """Submitting to a new namespace succeeds when explicitly allowed."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        ns_client = TestClient(app)
        resp = ns_client.post(
            "/",
            data={
                "csrf_token": _csrf(ns_client),
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

    def test_submit_new_namespace_rejected_by_default(self, client: TestClient) -> None:
        """Submitting to an unknown namespace is rejected by default."""
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
        assert "Invalid namespace" in resp.text

    def test_submit_shows_proposal_id(self, client: TestClient) -> None:
        """Submitted proposal confirmation shows the proposal ID."""
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "ID test",
                "description": "",
            },
        )
        assert resp.status_code == 200
        assert "testns-inbox-" in resp.text

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

    def test_submit_redirect_includes_id(self, client: TestClient) -> None:
        """Successful POST redirect includes the proposal ID query param."""
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "ID redirect",
                "description": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "id=testns-inbox-" in resp.headers["location"]

    def test_submit_redirect_includes_namespace(self, client: TestClient) -> None:
        """Successful POST redirect includes the namespace query param."""
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "NS redirect",
                "description": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "namespace=testns" in resp.headers["location"]

    def test_submit_preserves_non_default_namespace(
        self, web_dogcats_multi_ns: Path
    ) -> None:
        """After submit to non-default ns, form keeps it selected."""
        app = create_app(dogcats_dir=str(web_dogcats_multi_ns))
        multi_client = TestClient(app)
        resp = multi_client.post(
            "/",
            data={
                "csrf_token": _csrf(multi_client),
                "namespace": "beta",
                "title": "Beta proposal",
                "description": "",
            },
        )
        # After redirect, the form should have beta as the active namespace
        assert 'value="beta"' in resp.text
        # The hidden namespace input should be set to beta
        assert 'name="namespace" value="beta"' in resp.text

    def test_get_with_submitted_shows_success(self, client: TestClient) -> None:
        """GET /?submitted=true&title=X shows the success message."""
        resp = client.get("/?submitted=true&title=My+proposal")
        assert resp.status_code == 200
        assert "Proposal submitted" in resp.text
        assert "My proposal" in resp.text

    def test_get_with_namespace_param_selects_namespace(
        self, web_dogcats_multi_ns: Path
    ) -> None:
        """GET /?namespace=beta selects that namespace in the form."""
        app = create_app(dogcats_dir=str(web_dogcats_multi_ns))
        multi_client = TestClient(app)
        resp = multi_client.get("/?namespace=beta")
        assert 'name="namespace" value="beta"' in resp.text

    def test_get_with_invalid_namespace_param_ignores_it(
        self, client: TestClient
    ) -> None:
        """GET /?namespace=bogus falls back to default namespace."""
        resp = client.get("/?namespace=bogus")
        assert 'name="namespace" value="testns"' in resp.text


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
        from dogcat.constants import WEB_DEFAULT_HOST, WEB_DEFAULT_PORT

        assert WEB_DEFAULT_PORT == 48042
        assert WEB_DEFAULT_HOST == "127.0.0.1"

    def test_port_env_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DCAT_WEB_PORT env var overrides the default."""
        from dogcat.cli._cmd_web import _env_default_port
        from dogcat.constants import WEB_PORT_ENV_VAR

        monkeypatch.setenv(WEB_PORT_ENV_VAR, "55555")
        assert _env_default_port() == 55555

    def test_port_env_var_unset_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without the env var, the compiled default applies."""
        from dogcat.cli._cmd_web import _env_default_port
        from dogcat.constants import WEB_DEFAULT_PORT, WEB_PORT_ENV_VAR

        monkeypatch.delenv(WEB_PORT_ENV_VAR, raising=False)
        assert _env_default_port() == WEB_DEFAULT_PORT

    def test_port_env_var_invalid_falls_back(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A non-integer env value warns and falls back to the default."""
        from dogcat.cli._cmd_web import _env_default_port
        from dogcat.constants import WEB_DEFAULT_PORT, WEB_PORT_ENV_VAR

        monkeypatch.setenv(WEB_PORT_ENV_VAR, "not-a-port")
        assert _env_default_port() == WEB_DEFAULT_PORT
        captured = capsys.readouterr()
        assert "not-a-port" in captured.err
        assert WEB_PORT_ENV_VAR in captured.err

    def test_allow_creating_namespaces_default(self, web_dogcats: Path) -> None:
        """By default allow_creating_namespaces is False."""
        app = create_app(dogcats_dir=str(web_dogcats))
        assert app.state.allow_creating_namespaces is False

    def test_allow_creating_namespaces_false(self, web_dogcats: Path) -> None:
        """Explicit False is stored in app state."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=False)
        assert app.state.allow_creating_namespaces is False

    def test_form_shows_new_option_when_allowed(self, web_dogcats: Path) -> None:
        """Form includes 'New...' dropdown item when namespace creation is allowed."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        client = TestClient(app)
        resp = client.get("/")
        assert "New&hellip;" in resp.text

    def test_form_hides_new_option_by_default(self, web_dogcats: Path) -> None:
        """Form omits 'New...' dropdown item by default."""
        app = create_app(dogcats_dir=str(web_dogcats))
        client = TestClient(app)
        resp = client.get("/")
        assert "New&hellip;" not in resp.text


class TestAriaSemantics:
    """Regression tests for dogcat-5vsb: ARIA attributes on the proposal form."""

    def test_dropdown_has_combobox_role_with_aria_state(
        self, client: TestClient
    ) -> None:
        """The namespace dropdown is a combobox with aria-expanded/controls."""
        resp = client.get("/")
        assert 'role="combobox"' in resp.text
        assert 'aria-expanded="false"' in resp.text
        assert 'aria-controls="ns-menu"' in resp.text
        assert 'role="listbox"' in resp.text
        assert 'role="option"' in resp.text

    def test_active_option_marked_aria_selected(self, client: TestClient) -> None:
        """The currently-selected namespace has aria-selected=true."""
        resp = client.get("/")
        assert 'aria-selected="true"' in resp.text

    def test_form_has_aria_labelledby(self, client: TestClient) -> None:
        """The form is associated with the page heading."""
        resp = client.get("/")
        assert 'id="page-title"' in resp.text
        assert 'aria-labelledby="page-title"' in resp.text

    def test_required_title_has_aria_required(self, client: TestClient) -> None:
        """Required title input is also marked aria-required for screen readers."""
        resp = client.get("/")
        # aria-required on the title input
        assert 'aria-required="true"' in resp.text

    def test_status_region_uses_aria_live(self, client: TestClient) -> None:
        """A polite live region announces submission outcomes."""
        resp = client.get("/")
        assert 'aria-live="polite"' in resp.text
        assert 'role="status"' in resp.text

    def test_error_message_uses_role_alert_and_aria_invalid(
        self, client: TestClient
    ) -> None:
        """Title-validation errors mark the field invalid and use role=alert."""
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "  ",
                "description": "",
            },
        )
        assert 'role="alert"' in resp.text
        assert 'aria-invalid="true"' in resp.text


class TestNewNamespacePersistence:
    """Regression tests for dogcat-5a2f: dynamically created namespaces survive restart.

    Previously they were appended to the in-memory namespaces list only and
    vanished when the server stopped.
    """

    def test_new_namespace_pinned_in_local_config(self, web_dogcats: Path) -> None:
        """Submitting to a new namespace persists it under pinned_namespaces."""
        from dogcat.config import load_local_config

        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        client = TestClient(app)
        client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "freshly_minted",
                "title": "first",
                "description": "",
            },
        )
        local = load_local_config(str(web_dogcats))
        assert "freshly_minted" in local.get("pinned_namespaces", [])

    def test_new_namespace_visible_after_restart(self, web_dogcats: Path) -> None:
        """A new namespace appears in the dropdown of a freshly-built app."""
        app1 = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        client1 = TestClient(app1)
        client1.post(
            "/",
            data={
                "csrf_token": _csrf(client1),
                "namespace": "persisted",
                "title": "first",
                "description": "",
            },
        )

        # Simulate restart: build a new app from the same dogcats dir.
        app2 = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        client2 = TestClient(app2)
        resp = client2.get("/")
        assert 'data-value="persisted"' in resp.text

    def test_pinned_namespace_not_duplicated(self, web_dogcats: Path) -> None:
        """Submitting twice to the same new namespace doesn't dup the pin."""
        from dogcat.config import load_local_config

        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        client = TestClient(app)
        for i in range(3):
            client.post(
                "/",
                data={
                    "csrf_token": _csrf(client),
                    "namespace": "once",
                    "title": f"submission-{i}",
                    "description": "",
                },
            )
        local = load_local_config(str(web_dogcats))
        pinned = local.get("pinned_namespaces", [])
        assert pinned.count("once") == 1


class TestNamespaceValidation:
    """Regression tests for dogcat-1819: namespace format whitelist.

    The form previously accepted arbitrary strings (spaces, control chars,
    Unicode homoglyphs); now only ``[A-Za-z0-9_-]`` is allowed and input
    is NFKC-normalized before checking.
    """

    @pytest.mark.parametrize(
        "bad_ns",
        [
            "with spaces",
            "ctrl\x01char",
            "newline\nhere",
            "tab\there",
            "../etc/passwd",
            "name/with/slashes",
            "name.with.dots",
            "name:with:colons",
            "   ",  # whitespace-only collapses to empty after strip
            "a" * 65,  # over the length cap
        ],
    )
    def test_invalid_namespace_rejected(self, web_dogcats: Path, bad_ns: str) -> None:
        """Malformed namespaces are rejected with a clear error."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        client = TestClient(app)
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": bad_ns,
                "title": "x",
                "description": "",
            },
        )
        assert resp.status_code == 200
        assert "Namespace must be" in resp.text or "Invalid namespace" in resp.text
        # And nothing was written to the inbox.
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        assert inbox.list() == []

    def test_unicode_homoglyph_rejected(self, web_dogcats: Path) -> None:
        """Unicode chars that look like ASCII are rejected, not silently accepted."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        client = TestClient(app)
        # Build "t<Cyrillic e>stns" without writing the homoglyph literally,
        # to keep ruff's RUF001 check happy.
        cyrillic_e = chr(0x0435)
        spoofed = "t" + cyrillic_e + "stns"
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": spoofed,
                "title": "spoof",
                "description": "",
            },
        )
        assert "Namespace must be" in resp.text

    def test_fullwidth_namespace_normalized(self, web_dogcats: Path) -> None:
        """NFKC folds fullwidth ASCII to plain ASCII before whitelist check."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        client = TestClient(app)
        # Construct fullwidth "testns" via codepoints (U+FF54..) so the source
        # file stays free of ambiguous Latin lookalikes.
        fullwidth = "".join(chr(0xFF00 + ord(c) - 0x20) for c in "testns")
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": fullwidth,
                "title": "fullwidth",
                "description": "",
            },
        )
        assert "Proposal submitted" in resp.text or "submitted=true" in resp.text
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        assert any(p.namespace == "testns" for p in inbox.list())

    def test_valid_namespace_accepted(self, web_dogcats: Path) -> None:
        """Underscores and hyphens are allowed."""
        app = create_app(dogcats_dir=str(web_dogcats), allow_creating_namespaces=True)
        client = TestClient(app)
        for ns in ("alpha", "beta-1", "snake_case", "MixedCase"):
            resp = client.post(
                "/",
                data={
                    "csrf_token": _csrf(client),
                    "namespace": ns,
                    "title": f"ok-{ns}",
                    "description": "",
                },
            )
            assert "Namespace must be" not in resp.text


class TestCSRFPerSession:
    """Regression tests for dogcat-5dd4: CSRF tokens must rotate per session.

    Previously a single token was minted at app start and shared across all
    sessions, so any client that ever obtained it could reuse it indefinitely
    until server restart.
    """

    def test_each_session_gets_a_distinct_token(self, web_dogcats: Path) -> None:
        """Two independent clients see different CSRF tokens."""
        app = create_app(dogcats_dir=str(web_dogcats))
        c1 = TestClient(app)
        c2 = TestClient(app)
        t1 = _csrf(c1)
        t2 = _csrf(c2)
        assert t1 != t2
        # And both are non-empty, urlsafe-ish.
        assert len(t1) > 20
        assert len(t2) > 20

    def test_token_from_one_session_rejected_in_another(
        self, web_dogcats: Path
    ) -> None:
        """A token leaked from session A cannot be used by session B."""
        app = create_app(dogcats_dir=str(web_dogcats))
        attacker = TestClient(app)
        victim = TestClient(app)
        victim_token = _csrf(victim)

        # Attacker tries to submit using the victim's token but their own
        # cookie jar (their cookie is either absent or different).
        resp = attacker.post(
            "/",
            data={
                "csrf_token": victim_token,
                "namespace": "testns",
                "title": "Forged",
                "description": "",
            },
        )
        assert "Invalid form submission" in resp.text

    def test_csrf_cookie_has_security_flags(self, client: TestClient) -> None:
        """The CSRF cookie is HttpOnly and SameSite=Strict."""
        resp = client.get("/")
        set_cookie = resp.headers.get("set-cookie", "")
        assert "dcat_csrf=" in set_cookie
        assert "HttpOnly" in set_cookie
        # Starlette spells it lowercase; accept either.
        assert "samesite=strict" in set_cookie.lower()

    def test_csrf_cookie_max_age_matches_constant(self, client: TestClient) -> None:
        """Set-Cookie carries Max-Age equal to CSRF_COOKIE_MAX_AGE.

        Without this assertion a regression that silently extends session
        lifetime (e.g. dropping max_age, or bumping it without intent) would
        slip through.
        """
        from dogcat.web.propose import CSRF_COOKIE_MAX_AGE

        resp = client.get("/")
        set_cookie = resp.headers.get("set-cookie", "")
        # Max-Age is case-insensitive in the spec; accept either spelling.
        lower = set_cookie.lower()
        assert f"max-age={CSRF_COOKIE_MAX_AGE}" in lower

    def test_post_without_cookie_is_rejected(self, web_dogcats: Path) -> None:
        """POST without a CSRF cookie fails even if form has a value."""
        app = create_app(dogcats_dir=str(web_dogcats))
        client = TestClient(app)
        resp = client.post(
            "/",
            data={
                "csrf_token": "anything",
                "namespace": "testns",
                "title": "No cookie",
                "description": "",
            },
        )
        assert "Invalid form submission" in resp.text


class TestWebProposeInit:
    """Tests for dcat web propose initialization checks."""

    def test_fails_without_initialized_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Running 'web propose' without .dogcats directory fails."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli_app, ["web", "propose"])
        assert result.exit_code == 1
        assert "not initialized" in result.output


class TestLengthLimits:
    """Boundary tests for MAX_TITLE_LEN / MAX_DESC_LEN enforcement.

    These guard against a typo loosening the bounds shipping silently.
    """

    def test_title_at_limit_accepted(
        self, client: TestClient, web_dogcats: Path
    ) -> None:
        """A title exactly MAX_TITLE_LEN characters is accepted."""
        from dogcat.web.propose.routes import MAX_TITLE_LEN

        title = "a" * MAX_TITLE_LEN
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": title,
                "description": "",
            },
        )
        assert resp.status_code == 200
        assert "Title must be" not in resp.text
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        assert any(p.title == title for p in inbox.list())

    def test_title_over_limit_rejected(
        self, client: TestClient, web_dogcats: Path
    ) -> None:
        """A title MAX_TITLE_LEN+1 characters is rejected."""
        from dogcat.web.propose.routes import MAX_TITLE_LEN

        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "a" * (MAX_TITLE_LEN + 1),
                "description": "",
            },
        )
        assert resp.status_code == 200
        assert "Title must be" in resp.text
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        assert inbox.list() == []

    def test_description_at_limit_accepted(
        self, client: TestClient, web_dogcats: Path
    ) -> None:
        """A description exactly MAX_DESC_LEN characters is accepted."""
        from dogcat.web.propose.routes import MAX_DESC_LEN

        description = "d" * MAX_DESC_LEN
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "boundary",
                "description": description,
            },
        )
        assert resp.status_code == 200
        assert "Description must be" not in resp.text
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        assert any(p.description == description for p in inbox.list())

    def test_description_over_limit_rejected(
        self, client: TestClient, web_dogcats: Path
    ) -> None:
        """A description MAX_DESC_LEN+1 characters is rejected."""
        from dogcat.web.propose.routes import MAX_DESC_LEN

        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "boundary",
                "description": "d" * (MAX_DESC_LEN + 1),
            },
        )
        assert resp.status_code == 200
        assert "Description must be" in resp.text
        inbox = InboxStorage(dogcats_dir=str(web_dogcats))
        assert inbox.list() == []


class TestPersistentInboxStorage:
    """Regression tests for dogcat-4r5i: web app holds persistent InboxStorage.

    Previously every POST constructed a fresh InboxStorage which read+parsed
    the entire file. The persistent instance lives on app.state and is
    refreshed on mtime change.
    """

    def test_app_state_holds_inbox_storage(self, web_dogcats: Path) -> None:
        """create_app stashes a persistent InboxStorage on app.state."""
        from dogcat.inbox import InboxStorage

        app = create_app(dogcats_dir=str(web_dogcats))
        assert isinstance(app.state.inbox, InboxStorage)

    def test_submit_uses_persistent_inbox_instance(self, web_dogcats: Path) -> None:
        """Submit reuses the same InboxStorage instance — no per-request rebuild."""
        from dogcat.inbox import InboxStorage

        app = create_app(dogcats_dir=str(web_dogcats))
        client = TestClient(app)
        original_inbox = app.state.inbox

        client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "First",
                "description": "",
            },
        )
        client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "Second",
                "description": "",
            },
        )
        # The state-held instance should still be the same object.
        assert app.state.inbox is original_inbox
        assert isinstance(app.state.inbox, InboxStorage)

    def test_submit_picks_up_external_writes_via_reload(
        self, web_dogcats: Path
    ) -> None:
        """Mtime-based reload surfaces writes made by another process."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        app = create_app(dogcats_dir=str(web_dogcats))
        client = TestClient(app)

        # An external writer adds a proposal — touches the inbox file.
        external = InboxStorage(dogcats_dir=str(web_dogcats))
        external.create(Proposal(id="ext1", title="external", namespace="testns"))

        # The persistent instance hasn't seen the new record yet — but the
        # next submit must still succeed (reload picks the new state up).
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "testns",
                "title": "After external write",
                "description": "",
            },
        )
        assert resp.status_code == 200
        # Both proposals should be present on disk.
        verify = InboxStorage(dogcats_dir=str(web_dogcats))
        titles = {p.title for p in verify.list()}
        assert "external" in titles
        assert "After external write" in titles


class TestAllowCreatingNamespacesDefault:
    """Regression tests for dogcat-kz1a: getattr default must not flip the policy.

    Both call sites previously defaulted to True when ``allow_creating_namespaces``
    was unset on app.state — opposite of create_app's default of False — so a
    bare app construction silently allowed namespace minting.
    """

    def test_missing_attr_defaults_to_disallow(self, web_dogcats: Path) -> None:
        """If the attribute is missing on app.state, namespace creation is denied."""
        app = create_app(dogcats_dir=str(web_dogcats))
        # Simulate an older / hand-built app that never set the flag.
        del app.state.allow_creating_namespaces
        client = TestClient(app)
        resp = client.post(
            "/",
            data={
                "csrf_token": _csrf(client),
                "namespace": "freshly_minted",
                "title": "should fail",
                "description": "",
            },
        )
        assert resp.status_code == 200
        assert "Invalid namespace" in resp.text

    def test_form_hides_new_option_when_attr_missing(self, web_dogcats: Path) -> None:
        """The form's 'New...' option is hidden when the attribute is missing."""
        app = create_app(dogcats_dir=str(web_dogcats))
        del app.state.allow_creating_namespaces
        client = TestClient(app)
        resp = client.get("/")
        assert "New&hellip;" not in resp.text
