"""Tests for the dcat graph command."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestGraph:
    """Test the graph command."""

    def _init(self, tmp_path: Path) -> str:
        dogcats_dir = str(tmp_path / ".dogcats")
        runner.invoke(app, ["init", "--dogcats-dir", dogcats_dir])
        return dogcats_dir

    def _create(self, dogcats_dir: str, title: str, **opts: str) -> str:
        """Create an issue and return its full_id."""
        args = ["create", title, "--dogcats-dir", dogcats_dir]
        for k, v in opts.items():
            args.extend([f"--{k}", v])
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.stdout
        return result.stdout.split(": ")[0].split()[-1]

    # ------------------------------------------------------------------
    # Empty graph
    # ------------------------------------------------------------------

    def test_no_issues(self, tmp_path: Path) -> None:
        """Empty tracker produces no graph."""
        dd = self._init(tmp_path)
        result = runner.invoke(app, ["graph", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "No dependency graph to display" in result.stdout

    def test_no_relationships(self, tmp_path: Path) -> None:
        """Standalone issues with no deps or children produce no graph."""
        dd = self._init(tmp_path)
        self._create(dd, "Standalone issue")
        result = runner.invoke(app, ["graph", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "No dependency graph to display" in result.stdout

    # ------------------------------------------------------------------
    # Blocking dependency edges
    # ------------------------------------------------------------------

    def test_blocking_dep(self, tmp_path: Path) -> None:
        """A blocks B should render with ▶ arrow."""
        dd = self._init(tmp_path)
        a = self._create(dd, "Blocker")
        b = self._create(dd, "Blocked")

        runner.invoke(
            app,
            ["dep", b, "add", "--depends-on", a, "--dogcats-dir", dd],
        )

        result = runner.invoke(app, ["graph", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "Blocker" in result.stdout
        assert "Blocked" in result.stdout
        # Should contain the blocks arrow character
        assert "\u25b6" in result.stdout  # ▶

    def test_chain_of_blocks(self, tmp_path: Path) -> None:
        """A blocks B blocks C should render as a chain."""
        dd = self._init(tmp_path)
        a = self._create(dd, "First")
        b = self._create(dd, "Second")
        c = self._create(dd, "Third")

        runner.invoke(
            app,
            ["dep", b, "add", "--depends-on", a, "--dogcats-dir", dd],
        )
        runner.invoke(
            app,
            ["dep", c, "add", "--depends-on", b, "--dogcats-dir", dd],
        )

        result = runner.invoke(app, ["graph", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "First" in result.stdout
        assert "Second" in result.stdout
        assert "Third" in result.stdout

    # ------------------------------------------------------------------
    # Parent-child edges
    # ------------------------------------------------------------------

    def test_parent_child(self, tmp_path: Path) -> None:
        """Parent-child relationships use ── connectors."""
        dd = self._init(tmp_path)
        parent = self._create(dd, "Epic parent", type="epic")
        self._create(dd, "Child task", parent=parent)

        result = runner.invoke(app, ["graph", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "Epic parent" in result.stdout
        assert "Child task" in result.stdout
        # Should contain tree connector (not the blocks arrow)
        assert "──" in result.stdout

    # ------------------------------------------------------------------
    # Mixed edges
    # ------------------------------------------------------------------

    def test_mixed_edges(self, tmp_path: Path) -> None:
        """Graph with both parent-child and blocking edges."""
        dd = self._init(tmp_path)
        epic = self._create(dd, "Epic", type="epic")
        child = self._create(dd, "Child", parent=epic)
        blocker = self._create(dd, "External blocker")

        runner.invoke(
            app,
            ["dep", child, "add", "--depends-on", blocker, "--dogcats-dir", dd],
        )

        result = runner.invoke(app, ["graph", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "Epic" in result.stdout
        assert "Child" in result.stdout
        assert "External blocker" in result.stdout

    # ------------------------------------------------------------------
    # Subgraph by issue ID
    # ------------------------------------------------------------------

    def test_subgraph(self, tmp_path: Path) -> None:
        """Dcat graph <id> shows only the reachable subgraph."""
        dd = self._init(tmp_path)
        a = self._create(dd, "Alpha")
        b = self._create(dd, "Beta")
        self._create(dd, "Gamma")  # unrelated

        runner.invoke(
            app,
            ["dep", b, "add", "--depends-on", a, "--dogcats-dir", dd],
        )

        # Graph from Alpha should show Alpha and Beta, not Gamma.
        result = runner.invoke(app, ["graph", a, "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "Alpha" in result.stdout
        assert "Beta" in result.stdout
        assert "Gamma" not in result.stdout

    def test_subgraph_nonexistent_id(self, tmp_path: Path) -> None:
        """Nonexistent issue ID returns exit code 1."""
        dd = self._init(tmp_path)
        result = runner.invoke(app, ["graph", "nonexistent", "--dogcats-dir", dd])
        assert result.exit_code == 1

    # ------------------------------------------------------------------
    # DAG convergence (visited dedup)
    # ------------------------------------------------------------------

    def test_dag_convergence_ref(self, tmp_path: Path) -> None:
        """When two paths converge on the same node, second shows (ref:)."""
        dd = self._init(tmp_path)
        root = self._create(dd, "Root")
        left = self._create(dd, "Left")
        right = self._create(dd, "Right")
        leaf = self._create(dd, "Leaf")

        # Root blocks Left and Right; both block Leaf.
        for mid in (left, right):
            runner.invoke(
                app,
                ["dep", mid, "add", "--depends-on", root, "--dogcats-dir", dd],
            )
            runner.invoke(
                app,
                ["dep", leaf, "add", "--depends-on", mid, "--dogcats-dir", dd],
            )

        result = runner.invoke(app, ["graph", "--dogcats-dir", dd])
        assert result.exit_code == 0
        # Leaf should appear once fully and once as (ref: ...).
        assert "ref:" in result.stdout

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def test_agent_only(self, tmp_path: Path) -> None:
        """--agent-only hides manual issues."""
        dd = self._init(tmp_path)
        a = self._create(dd, "Auto")
        b = self._create(dd, "Manual")

        runner.invoke(
            app,
            ["dep", b, "add", "--depends-on", a, "--dogcats-dir", dd],
        )
        runner.invoke(
            app,
            ["update", b, "--manual", "--dogcats-dir", dd],
        )

        result = runner.invoke(app, ["graph", "--agent-only", "--dogcats-dir", dd])
        assert result.exit_code == 0
        # After filtering out Manual, Auto has no relationship left.
        assert "Manual" not in result.stdout

    # ------------------------------------------------------------------
    # JSON output
    # ------------------------------------------------------------------

    def test_json_output(self, tmp_path: Path) -> None:
        """JSON output contains nodes and edges."""
        dd = self._init(tmp_path)
        a = self._create(dd, "Alpha")
        b = self._create(dd, "Beta")

        runner.invoke(
            app,
            ["dep", b, "add", "--depends-on", a, "--dogcats-dir", dd],
        )

        result = runner.invoke(app, ["graph", "--json", "--dogcats-dir", dd])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        edge = data["edges"][0]
        assert edge["type"] == "blocks"

    def test_json_empty(self, tmp_path: Path) -> None:
        """Empty graph returns empty nodes and edges in JSON."""
        dd = self._init(tmp_path)
        result = runner.invoke(app, ["graph", "--json", "--dogcats-dir", dd])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["nodes"] == []
        assert data["edges"] == []
