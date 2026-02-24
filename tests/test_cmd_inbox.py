"""Tests for the dcat inbox CLI command group."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


def _init(tmp_path: Path) -> Path:
    """Initialize a .dogcats directory and return its path."""
    dogcats_dir = tmp_path / ".dogcats"
    runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    return dogcats_dir


def _create_proposal(tmp_path: Path, title: str = "Test proposal") -> str:
    """Create a proposal and return its full ID."""
    result = runner.invoke(
        app,
        [
            "propose",
            title,
            "--to",
            str(tmp_path),
            "--json",
        ],
    )
    data = json.loads(result.stdout)
    return f"{data['namespace']}-inbox-{data['id']}"


class TestInboxList:
    """Test the inbox list command."""

    def test_list_empty(self, tmp_path: Path) -> None:
        """Test listing with no proposals."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app,
            ["inbox", "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "No proposals" in result.stdout

    def test_list_with_proposals(self, tmp_path: Path) -> None:
        """Test listing with proposals present."""
        dogcats_dir = _init(tmp_path)
        _create_proposal(tmp_path, "First proposal")
        _create_proposal(tmp_path, "Second proposal")

        result = runner.invoke(
            app,
            ["inbox", "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "First proposal" in result.stdout
        assert "Second proposal" in result.stdout

    def test_list_json_output(self, tmp_path: Path) -> None:
        """Test list with --json output."""
        dogcats_dir = _init(tmp_path)
        _create_proposal(tmp_path, "JSON list test")

        result = runner.invoke(
            app,
            ["inbox", "list", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data: list[dict[str, object]] = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["title"] == "JSON list test"

    def test_list_hides_closed_by_default(self, tmp_path: Path) -> None:
        """Test that closed proposals are hidden by default."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Will be closed")

        runner.invoke(
            app,
            ["inbox", "close", full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["inbox", "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Will be closed" not in result.stdout

    def test_list_all_includes_closed(self, tmp_path: Path) -> None:
        """Test that --all shows closed proposals."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Closed but visible")

        runner.invoke(
            app,
            ["inbox", "close", full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["inbox", "list", "--all", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed but visible" in result.stdout


class TestInboxShow:
    """Test the inbox show command."""

    def test_show_proposal(self, tmp_path: Path) -> None:
        """Test showing a proposal's details."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Show me")

        result = runner.invoke(
            app,
            ["inbox", "show", full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Show me" in result.stdout
        assert full_id in result.stdout

    def test_show_json_output(self, tmp_path: Path) -> None:
        """Test show with --json output."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "JSON show test")

        result = runner.invoke(
            app,
            [
                "inbox",
                "show",
                full_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "JSON show test"
        constructed_id = f"{data['namespace']}-inbox-{data['id']}"
        assert constructed_id == full_id

    def test_show_nonexistent(self, tmp_path: Path) -> None:
        """Test showing a nonexistent proposal."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "inbox",
                "show",
                "dc-inbox-xxxx",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_show_displays_status(self, tmp_path: Path) -> None:
        """Test that show displays status field."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Status check")

        result = runner.invoke(
            app,
            ["inbox", "show", full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "open" in result.stdout

    def test_show_falls_back_to_remote(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Show finds a proposal in the remote inbox when not local."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "Remote detail")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "show", proposal_id])
        assert result.exit_code == 0
        assert "Remote detail" in result.stdout

    def test_show_remote_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Show --json works for remote proposals."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "Remote JSON")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "show", proposal_id, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "Remote JSON"


class TestInboxClose:
    """Test the inbox close command."""

    def test_close_proposal(self, tmp_path: Path) -> None:
        """Test closing a proposal."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Close me")

        result = runner.invoke(
            app,
            ["inbox", "close", full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Closed" in result.stdout
        assert "Close me" in result.stdout

    def test_close_with_reason(self, tmp_path: Path) -> None:
        """Test closing with a reason."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Reasoned close")

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                full_id,
                "--reason",
                "Not needed",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Closed" in result.stdout

    def test_close_with_issue(self, tmp_path: Path) -> None:
        """Test closing with a linked issue ID."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Issue link close")

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                full_id,
                "--issue",
                "dc-abcd",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0

    def test_close_json_output(self, tmp_path: Path) -> None:
        """Test close with --json output."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "JSON close")

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                full_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "closed"

    def test_close_multiple(self, tmp_path: Path) -> None:
        """Test closing multiple proposals at once."""
        dogcats_dir = _init(tmp_path)
        id1 = _create_proposal(tmp_path, "Close first")
        id2 = _create_proposal(tmp_path, "Close second")

        result = runner.invoke(
            app,
            ["inbox", "close", id1, id2, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Close first" in result.stdout
        assert "Close second" in result.stdout

    def test_close_multiple_json(self, tmp_path: Path) -> None:
        """Test closing multiple proposals with --json output."""
        dogcats_dir = _init(tmp_path)
        id1 = _create_proposal(tmp_path, "JSON first")
        id2 = _create_proposal(tmp_path, "JSON second")

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                id1,
                id2,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert data["status"] == "closed"

    def test_close_multiple_partial_failure(self, tmp_path: Path) -> None:
        """Test that closing continues on error and exits 1."""
        dogcats_dir = _init(tmp_path)
        valid_id = _create_proposal(tmp_path, "Valid close")

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                valid_id,
                "dc-inbox-xxxx",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Valid close" in result.stdout

    def test_close_nonexistent(self, tmp_path: Path) -> None:
        """Test closing a nonexistent proposal."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "inbox",
                "close",
                "dc-inbox-xxxx",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1


class TestInboxDelete:
    """Test the inbox delete command."""

    def test_delete_proposal(self, tmp_path: Path) -> None:
        """Test deleting a proposal."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Delete me")

        result = runner.invoke(
            app,
            ["inbox", "delete", full_id, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Deleted" in result.stdout
        assert "Delete me" in result.stdout

    def test_delete_json_output(self, tmp_path: Path) -> None:
        """Test delete with --json output."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "JSON delete")

        result = runner.invoke(
            app,
            [
                "inbox",
                "delete",
                full_id,
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "tombstone"

    def test_delete_multiple(self, tmp_path: Path) -> None:
        """Test deleting multiple proposals at once."""
        dogcats_dir = _init(tmp_path)
        id1 = _create_proposal(tmp_path, "Delete first")
        id2 = _create_proposal(tmp_path, "Delete second")

        result = runner.invoke(
            app,
            ["inbox", "delete", id1, id2, "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Delete first" in result.stdout
        assert "Delete second" in result.stdout

    def test_delete_multiple_partial_failure(self, tmp_path: Path) -> None:
        """Test that deleting continues on error and exits 1."""
        dogcats_dir = _init(tmp_path)
        valid_id = _create_proposal(tmp_path, "Valid delete")

        result = runner.invoke(
            app,
            [
                "inbox",
                "delete",
                valid_id,
                "dc-inbox-xxxx",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "Valid delete" in result.stdout

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        """Test deleting a nonexistent proposal."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app,
            [
                "inbox",
                "delete",
                "dc-inbox-xxxx",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1

    def test_delete_with_by(self, tmp_path: Path) -> None:
        """Test deleting with --by attribution."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Delete with by")

        result = runner.invoke(
            app,
            [
                "inbox",
                "delete",
                full_id,
                "--by",
                "admin@example.com",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "tombstone"
        assert data["deleted_by"] == "admin@example.com"
        assert data["deleted_at"] is not None

    def test_deleted_proposal_hidden_from_list(self, tmp_path: Path) -> None:
        """Test that deleted proposals are hidden from default list."""
        dogcats_dir = _init(tmp_path)
        full_id = _create_proposal(tmp_path, "Will be deleted")

        runner.invoke(
            app,
            ["inbox", "delete", full_id, "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["inbox", "list", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        assert "Will be deleted" not in result.stdout


def _setup_remote_inbox(
    tmp_path: Path,
    local_ns: str = "myproj",
) -> tuple[Path, Path]:
    """Set up a local project and a remote inbox for testing.

    Returns:
        Tuple of (local_dogcats_dir, remote_dogcats_dir).
    """
    from dogcat.config import save_config, save_local_config

    # Set up local project
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_dogcats = local_dir / ".dogcats"
    runner.invoke(app, ["init", "--dogcats-dir", str(local_dogcats)])
    save_config(str(local_dogcats), {"namespace": local_ns})

    # Set up remote inbox
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    remote_dogcats = remote_dir / ".dogcats"
    runner.invoke(app, ["init", "--dogcats-dir", str(remote_dogcats)])
    save_config(str(remote_dogcats), {"namespace": "inbox"})

    # Point local at remote
    save_local_config(str(local_dogcats), {"inbox_remote": str(remote_dir)})

    return local_dogcats, remote_dogcats


def _create_remote_proposal(
    remote_dir: Path,
    title: str,
    namespace: str = "myproj",
) -> str:
    """Create a proposal in the remote inbox with a given namespace."""
    remote_root = remote_dir.parent
    result = runner.invoke(
        app,
        [
            "propose",
            title,
            "--to",
            str(remote_root),
            "--namespace",
            namespace,
            "--json",
        ],
    )
    data = json.loads(result.stdout)
    return f"{data['namespace']}-inbox-{data['id']}"


class TestInboxListRemote:
    """Test inbox list with remote inbox integration."""

    def test_list_shows_remote_proposals(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Remote proposals appear in inbox list."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        _create_remote_proposal(remote_dogcats, "Remote idea")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "list"])
        assert result.exit_code == 0
        assert "Remote idea" in result.stdout
        assert "Remote proposals" in result.stdout

    def test_remote_filtered_by_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Only proposals matching local namespace appear."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        _create_remote_proposal(remote_dogcats, "My proposal", namespace="myproj")
        _create_remote_proposal(remote_dogcats, "Other proposal", namespace="other")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "list"])
        assert "My proposal" in result.stdout
        assert "Other proposal" not in result.stdout

    def test_remote_all_namespaces(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--all-namespaces shows all remote proposals."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        _create_remote_proposal(remote_dogcats, "My proposal", namespace="myproj")
        _create_remote_proposal(remote_dogcats, "Other proposal", namespace="other")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "list", "--all-namespaces"])
        assert "My proposal" in result.stdout
        assert "Other proposal" in result.stdout

    def test_remote_json_includes_source(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """JSON output includes source field for remote proposals."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        _create_remote_proposal(remote_dogcats, "JSON remote")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["source"] == "remote"
        assert data[0]["title"] == "JSON remote"

    def test_no_remote_when_not_configured(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without inbox_remote, no remote section appears."""
        _init(tmp_path)

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["inbox", "list"])
        assert result.exit_code == 0
        assert "Remote proposals" not in result.stdout

    def test_local_and_remote_both_shown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Both local and remote proposals appear when both exist."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        _create_remote_proposal(remote_dogcats, "Remote idea")

        # Create a local proposal too
        monkeypatch.chdir(local_dogcats.parent)
        runner.invoke(
            app,
            ["propose", "Local idea", "--to", str(local_dogcats.parent)],
        )

        result = runner.invoke(app, ["inbox", "list"])
        assert result.exit_code == 0
        assert "Local idea" in result.stdout
        assert "Remote idea" in result.stdout
        assert "Remote proposals" in result.stdout

    def test_empty_remote_shows_no_proposals(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Empty remote inbox shows no proposals message."""
        local_dogcats, _remote_dogcats = _setup_remote_inbox(tmp_path)

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "list"])
        assert result.exit_code == 0
        assert "No proposals" in result.stdout


class TestInboxAccept:
    """Test inbox accept command."""

    def test_accept_creates_local_issue(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Accept creates a local issue from a remote proposal."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "Great feature idea")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "accept", proposal_id])
        assert result.exit_code == 0
        assert "Created" in result.stdout
        assert "from proposal" in result.stdout

        # Verify local issue was created
        list_result = runner.invoke(app, ["list"])
        assert "Great feature idea" in list_result.stdout

    def test_accept_closes_remote_proposal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Accept closes the proposal in the remote inbox."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "Will be accepted")

        monkeypatch.chdir(local_dogcats.parent)
        runner.invoke(app, ["inbox", "accept", proposal_id])

        # Proposal should be closed in remote
        from dogcat.inbox import InboxStorage

        remote_inbox = InboxStorage(dogcats_dir=str(remote_dogcats))
        proposal = remote_inbox.get(proposal_id)
        assert proposal is not None
        assert proposal.status.value == "closed"
        assert proposal.resolved_issue is not None
        assert proposal.close_reason == "Accepted as issue"

    def test_accept_with_priority_and_labels(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Accept passes priority and labels to the created issue."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "Labeled feature")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(
            app,
            ["inbox", "accept", proposal_id, "-p", "1", "-l", "cli,ux", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["priority"] == 1
        assert set(data["labels"]) == {"cli", "ux"}

    def test_accept_json_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Accept with --json returns issue data."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "JSON accept test")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "accept", proposal_id, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["title"] == "JSON accept test"
        assert "id" in data

    def test_accept_not_found(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Accept fails gracefully for nonexistent proposal."""
        local_dogcats, _remote_dogcats = _setup_remote_inbox(tmp_path)

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "accept", "myproj-inbox-xxxx"])
        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "not found" in output

    def test_accept_no_remote_configured(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Accept fails when no remote inbox is configured."""
        _init(tmp_path)

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["inbox", "accept", "dc-inbox-xxxx"])
        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "No remote inbox" in output

    def test_accept_copies_description(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Accept copies description from proposal to issue."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)

        # Create proposal with description
        remote_root = remote_dogcats.parent
        propose_result = runner.invoke(
            app,
            [
                "propose",
                "Feature with details",
                "--to",
                str(remote_root),
                "--namespace",
                "myproj",
                "-d",
                "This is the detailed description",
                "--json",
            ],
        )
        data = json.loads(propose_result.stdout)
        proposal_id = f"{data['namespace']}-inbox-{data['id']}"

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "accept", proposal_id, "--json"])
        assert result.exit_code == 0
        issue_data = json.loads(result.stdout)
        assert issue_data["description"] == "This is the detailed description"


class TestInboxReject:
    """Test inbox reject command."""

    def test_reject_closes_remote_proposal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reject closes the proposal in the remote inbox."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "Bad idea")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "reject", proposal_id])
        assert result.exit_code == 0
        assert "Rejected" in result.stdout
        assert "Bad idea" in result.stdout

    def test_reject_with_reason(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reject stores the reason in the proposal."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "Duplicate idea")

        monkeypatch.chdir(local_dogcats.parent)
        runner.invoke(
            app,
            ["inbox", "reject", proposal_id, "-r", "Already implemented"],
        )

        from dogcat.inbox import InboxStorage

        remote_inbox = InboxStorage(dogcats_dir=str(remote_dogcats))
        proposal = remote_inbox.get(proposal_id)
        assert proposal is not None
        assert proposal.status.value == "closed"
        assert proposal.close_reason == "Already implemented"

    def test_reject_multiple(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reject multiple proposals at once."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        id1 = _create_remote_proposal(remote_dogcats, "Reject me 1")
        id2 = _create_remote_proposal(remote_dogcats, "Reject me 2")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "reject", id1, id2])
        assert result.exit_code == 0
        assert "Reject me 1" in result.stdout
        assert "Reject me 2" in result.stdout

    def test_reject_json_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reject with --json outputs proposal data."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "JSON reject")

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(
            app,
            ["inbox", "reject", proposal_id, "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "closed"

    def test_reject_not_found(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reject fails gracefully for nonexistent proposal."""
        local_dogcats, _remote_dogcats = _setup_remote_inbox(tmp_path)

        monkeypatch.chdir(local_dogcats.parent)
        result = runner.invoke(app, ["inbox", "reject", "myproj-inbox-xxxx"])
        assert result.exit_code == 1

    def test_reject_no_remote_configured(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reject fails when no remote inbox is configured."""
        _init(tmp_path)

        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["inbox", "reject", "dc-inbox-xxxx"])
        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "No remote inbox" in output

    def test_reject_does_not_create_local_issue(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reject does NOT create a local issue."""
        local_dogcats, remote_dogcats = _setup_remote_inbox(tmp_path)
        proposal_id = _create_remote_proposal(remote_dogcats, "Rejected idea")

        monkeypatch.chdir(local_dogcats.parent)
        runner.invoke(app, ["inbox", "reject", proposal_id])

        # No local issues should exist
        list_result = runner.invoke(app, ["list"])
        assert "Rejected idea" not in list_result.stdout
