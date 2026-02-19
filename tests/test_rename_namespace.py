"""Tests for the rename-namespace command and storage method."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.config import set_issue_prefix
from dogcat.models import Issue
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


@pytest.fixture
def storage(temp_dogcats_dir: Path) -> JSONLStorage:
    """Create a storage instance with temporary directory."""
    storage_path = temp_dogcats_dir / "issues.jsonl"
    return JSONLStorage(str(storage_path), create_dir=True)


# ── Storage layer tests ──────────────────────────────────────────────


class TestRenameNamespace:
    """Test JSONLStorage.rename_namespace()."""

    def test_basic_rename(self, storage: JSONLStorage) -> None:
        """All issues in the old namespace get the new namespace."""
        storage.create(Issue(id="aaa1", title="One", namespace="old"))
        storage.create(Issue(id="bbb2", title="Two", namespace="old"))

        renamed = storage.rename_namespace("old", "new")

        assert len(renamed) == 2
        assert storage.get("new-aaa1") is not None
        assert storage.get("new-bbb2") is not None
        assert storage.get("old-aaa1") is None
        assert storage.get("old-bbb2") is None

    def test_only_affects_target_namespace(self, storage: JSONLStorage) -> None:
        """Issues in other namespaces are untouched."""
        storage.create(Issue(id="aaa1", title="Rename me", namespace="old"))
        storage.create(Issue(id="bbb2", title="Leave me", namespace="other"))

        storage.rename_namespace("old", "new")

        assert storage.get("new-aaa1") is not None
        assert storage.get("other-bbb2") is not None

    def test_error_no_issues(self, storage: JSONLStorage) -> None:
        """Raises ValueError when namespace has no issues."""
        with pytest.raises(ValueError, match="No issues found"):
            storage.rename_namespace("nonexistent", "new")

    def test_error_on_collision(self, storage: JSONLStorage) -> None:
        """Raises ValueError if any new ID already exists."""
        storage.create(Issue(id="abc1", title="Old", namespace="old"))
        storage.create(Issue(id="abc1", title="Existing", namespace="new"))

        with pytest.raises(ValueError, match="already exists"):
            storage.rename_namespace("old", "new")

    def test_cascades_parent_references(self, storage: JSONLStorage) -> None:
        """Parent references in children are updated."""
        storage.create(Issue(id="par1", title="Parent", namespace="old"))
        storage.create(
            Issue(id="ch1", title="Child", namespace="other", parent="old-par1")
        )

        storage.rename_namespace("old", "new")

        child = storage.get("other-ch1")
        assert child is not None
        assert child.parent == "new-par1"

    def test_cascades_duplicate_of(self, storage: JSONLStorage) -> None:
        """duplicate_of references are updated."""
        storage.create(Issue(id="orig", title="Original", namespace="old"))
        storage.create(
            Issue(id="dup1", title="Dup", namespace="other", duplicate_of="old-orig")
        )

        storage.rename_namespace("old", "new")

        dup = storage.get("other-dup1")
        assert dup is not None
        assert dup.duplicate_of == "new-orig"

    def test_cascades_dependencies(self, storage: JSONLStorage) -> None:
        """Dependency records are updated."""
        storage.create(Issue(id="is1", title="Issue 1", namespace="old"))
        storage.create(Issue(id="is2", title="Issue 2", namespace="other"))
        storage.add_dependency("old-is1", "other-is2", "blocks")

        storage.rename_namespace("old", "new")

        deps = storage.get_dependencies("new-is1")
        assert len(deps) == 1
        assert deps[0].issue_id == "new-is1"
        assert deps[0].depends_on_id == "other-is2"

    def test_cascades_links(self, storage: JSONLStorage) -> None:
        """Link records are updated."""
        storage.create(Issue(id="is1", title="Issue 1", namespace="old"))
        storage.create(Issue(id="is2", title="Issue 2", namespace="other"))
        storage.add_link("old-is1", "other-is2", "relates_to")

        storage.rename_namespace("old", "new")

        links = storage.get_links("new-is1")
        assert len(links) == 1
        assert links[0].from_id == "new-is1"

    def test_persists_after_reload(self, storage: JSONLStorage) -> None:
        """Rename survives a storage reload."""
        storage.create(Issue(id="aaa1", title="One", namespace="old"))

        storage.rename_namespace("old", "new")

        reloaded = JSONLStorage(str(storage.path))
        assert reloaded.get("new-aaa1") is not None
        assert reloaded.get("old-aaa1") is None

    def test_intra_namespace_parent_refs(self, storage: JSONLStorage) -> None:
        """Parent references within the renamed namespace are updated."""
        storage.create(Issue(id="par1", title="Parent", namespace="old"))
        storage.create(
            Issue(id="ch1", title="Child", namespace="old", parent="old-par1")
        )

        storage.rename_namespace("old", "new")

        child = storage.get("new-ch1")
        assert child is not None
        assert child.parent == "new-par1"


# ── Inbox tests ──────────────────────────────────────────────────────


class TestInboxRenameNamespace:
    """Test InboxStorage.rename_namespace()."""

    def test_basic_rename(self, temp_dogcats_dir: Path) -> None:
        """Proposals in the old namespace get the new namespace."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        inbox.create(Proposal(id="p1", title="Prop 1", namespace="old"))
        inbox.create(Proposal(id="p2", title="Prop 2", namespace="old"))

        count = inbox.rename_namespace("old", "new")

        assert count == 2
        # Proposal full_id is "{namespace}-inbox-{id}"
        assert inbox.get("new-inbox-p1") is not None
        assert inbox.get("new-inbox-p2") is not None

    def test_no_proposals(self, temp_dogcats_dir: Path) -> None:
        """Returns 0 when no proposals match."""
        from dogcat.inbox import InboxStorage

        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))

        count = inbox.rename_namespace("nonexistent", "new")

        assert count == 0

    def test_only_affects_target_namespace(self, temp_dogcats_dir: Path) -> None:
        """Proposals in other namespaces are untouched."""
        from dogcat.inbox import InboxStorage
        from dogcat.models import Proposal

        inbox = InboxStorage(dogcats_dir=str(temp_dogcats_dir))
        inbox.create(Proposal(id="p1", title="Rename me", namespace="old"))
        inbox.create(Proposal(id="p2", title="Leave me", namespace="other"))

        inbox.rename_namespace("old", "new")

        assert inbox.get("new-inbox-p1") is not None
        assert inbox.get("other-inbox-p2") is not None


# ── CLI tests ────────────────────────────────────────────────────────


def _init_workspace(tmp_path: Path, namespace: str = "dc") -> Path:
    """Initialize a workspace with a fixed namespace and return the dogcats_dir."""
    dogcats_dir = tmp_path / ".dogcats"
    runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    # Set a predictable namespace instead of the auto-detected temp dir name
    set_issue_prefix(str(dogcats_dir), namespace)
    return dogcats_dir


class TestRenameNamespaceCLI:
    """Test the rename-namespace CLI command."""

    def test_basic_rename(self, tmp_path: Path) -> None:
        """Command renames issues and prints summary."""
        dogcats_dir = _init_workspace(tmp_path)
        runner.invoke(
            app,
            ["create", "Issue A", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "rename-namespace",
                "dc",
                "proj",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        assert result.exit_code == 0
        assert "Renamed namespace 'dc' → 'proj'" in result.stdout
        assert "1 issue(s) renamed" in result.stdout

    def test_json_output(self, tmp_path: Path) -> None:
        """Command outputs valid JSON."""
        import json

        dogcats_dir = _init_workspace(tmp_path)
        runner.invoke(
            app,
            ["create", "Issue A", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "rename-namespace",
                "dc",
                "proj",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["old_namespace"] == "dc"
        assert data["new_namespace"] == "proj"
        assert data["issues_renamed"] == 1

    def test_same_namespace_error(self, tmp_path: Path) -> None:
        """Command errors when old == new."""
        dogcats_dir = _init_workspace(tmp_path)

        result = runner.invoke(
            app,
            [
                "rename-namespace",
                "dc",
                "dc",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        assert result.exit_code == 1

    def test_nonexistent_namespace_error(self, tmp_path: Path) -> None:
        """Command errors when namespace has no issues."""
        dogcats_dir = _init_workspace(tmp_path)

        result = runner.invoke(
            app,
            [
                "rename-namespace",
                "nonexistent",
                "new",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        assert result.exit_code == 1

    def test_updates_primary_config(self, tmp_path: Path) -> None:
        """Renaming the primary namespace updates config."""
        from dogcat.config import get_issue_prefix

        dogcats_dir = _init_workspace(tmp_path)
        runner.invoke(
            app,
            ["create", "Issue A", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "rename-namespace",
                "dc",
                "proj",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        assert result.exit_code == 0
        assert get_issue_prefix(str(dogcats_dir)) == "proj"
