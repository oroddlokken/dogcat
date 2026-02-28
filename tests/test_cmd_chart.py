"""Tests for the chart command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _init(tmp_path: Path) -> str:
    """Initialize a .dogcats directory and return its path."""
    dogcats_dir = tmp_path / ".dogcats"
    runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    return str(dogcats_dir)


def _create_issue(
    dogcats_dir: str,
    title: str,
    *,
    issue_type: str = "task",
    priority: int = 2,
    labels: str | None = None,
) -> str:
    """Create an issue and return its full ID."""
    cmd = [
        "create",
        title,
        "--type",
        issue_type,
        "--priority",
        str(priority),
        "--json",
        "--dogcats-dir",
        dogcats_dir,
    ]
    if labels is not None:
        cmd.extend(["--labels", labels])
    result = runner.invoke(app, cmd)
    data = json.loads(result.stdout)
    return f"{data['namespace']}-{data['id']}"


class TestChartCommand:
    """Test the chart CLI command."""

    def test_chart_no_issues(self, tmp_path: Path) -> None:
        """Chart with no issues shows 'no issues' message."""
        dd = _init(tmp_path)
        result = runner.invoke(app, ["chart", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "no issues" in result.stdout

    def test_chart_status_default(self, tmp_path: Path) -> None:
        """Chart defaults to status grouping."""
        dd = _init(tmp_path)
        _create_issue(dd, "Issue one")
        _create_issue(dd, "Issue two")

        result = runner.invoke(app, ["chart", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "Status Distribution" in result.stdout
        assert "2 issues" in result.stdout
        assert "open" in result.stdout

    def test_chart_by_type(self, tmp_path: Path) -> None:
        """Chart grouped by type shows type distribution."""
        dd = _init(tmp_path)
        _create_issue(dd, "A bug", issue_type="bug")
        _create_issue(dd, "A feature", issue_type="feature")
        _create_issue(dd, "Another bug", issue_type="bug")

        result = runner.invoke(app, ["chart", "--by", "type", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "Type Distribution" in result.stdout
        assert "3 issues" in result.stdout
        assert "bug" in result.stdout
        assert "feature" in result.stdout

    def test_chart_by_priority(self, tmp_path: Path) -> None:
        """Chart grouped by priority shows priority distribution."""
        dd = _init(tmp_path)
        _create_issue(dd, "Critical", priority=0)
        _create_issue(dd, "Low", priority=3)

        result = runner.invoke(app, ["chart", "--by", "priority", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "Priority Distribution" in result.stdout
        assert "2 issues" in result.stdout

    def test_chart_excludes_closed_by_default(self, tmp_path: Path) -> None:
        """Chart excludes closed issues unless --all is passed."""
        dd = _init(tmp_path)
        _create_issue(dd, "Open issue")
        closed_id = _create_issue(dd, "Closed issue")
        runner.invoke(app, ["close", closed_id, "--dogcats-dir", dd])

        result = runner.invoke(app, ["chart", "--json", "--dogcats-dir", dd])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total"] == 1

        # With --all, includes closed
        result = runner.invoke(app, ["chart", "--all", "--json", "--dogcats-dir", dd])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total"] == 2

    def test_chart_json_output(self, tmp_path: Path) -> None:
        """Chart --json produces valid JSON with counts."""
        dd = _init(tmp_path)
        _create_issue(dd, "Issue A")
        _create_issue(dd, "Issue B")

        result = runner.invoke(app, ["chart", "--json", "--dogcats-dir", dd])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["group_by"] == "all"
        assert data["total"] == 2
        assert data["counts"]["status"]["open"] == 2

    def test_chart_json_by_type(self, tmp_path: Path) -> None:
        """Chart --json --by type produces typed counts."""
        dd = _init(tmp_path)
        _create_issue(dd, "Bug one", issue_type="bug")
        _create_issue(dd, "Feature one", issue_type="feature")

        result = runner.invoke(
            app, ["chart", "--json", "--by", "type", "--dogcats-dir", dd]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["group_by"] == "type"
        assert data["counts"]["bug"] == 1
        assert data["counts"]["feature"] == 1

    def test_chart_invalid_by(self, tmp_path: Path) -> None:
        """Chart with invalid --by value exits with error."""
        dd = _init(tmp_path)
        result = runner.invoke(app, ["chart", "--by", "invalid", "--dogcats-dir", dd])
        assert result.exit_code == 1

    def test_chart_with_type_filter(self, tmp_path: Path) -> None:
        """Chart respects --type filter."""
        dd = _init(tmp_path)
        _create_issue(dd, "Bug", issue_type="bug")
        _create_issue(dd, "Task", issue_type="task")

        result = runner.invoke(
            app,
            ["chart", "--type", "bug", "--json", "--dogcats-dir", dd],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total"] == 1

    def test_chart_single_issue(self, tmp_path: Path) -> None:
        """Chart with 1 issue uses singular form."""
        dd = _init(tmp_path)
        _create_issue(dd, "Solo")

        result = runner.invoke(app, ["chart", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "1 issue)" in result.stdout

    def test_chart_mixed_statuses(self, tmp_path: Path) -> None:
        """Chart shows multiple statuses when issues have different states."""
        dd = _init(tmp_path)
        _create_issue(dd, "Open one")
        ip_id = _create_issue(dd, "WIP")
        runner.invoke(
            app,
            ["update", ip_id, "--status", "in_progress", "--dogcats-dir", dd],
        )

        result = runner.invoke(
            app, ["chart", "--json", "--by", "status", "--dogcats-dir", dd]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["counts"]["open"] == 1
        assert data["counts"]["in_progress"] == 1

    def test_chart_default_all_categories(self, tmp_path: Path) -> None:
        """Chart with no --by shows all four distributions."""
        dd = _init(tmp_path)
        _create_issue(dd, "Bug one", issue_type="bug", labels="cli")
        _create_issue(dd, "Task one", issue_type="task")

        result = runner.invoke(app, ["chart", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "Status Distribution" in result.stdout
        assert "Type Distribution" in result.stdout
        assert "Priority Distribution" in result.stdout
        assert "Label Distribution" in result.stdout

    def test_chart_default_all_json(self, tmp_path: Path) -> None:
        """Chart --json with no --by returns nested counts for all categories."""
        dd = _init(tmp_path)
        _create_issue(dd, "Bug", issue_type="bug", labels="cli")
        _create_issue(dd, "Task", issue_type="task")

        result = runner.invoke(app, ["chart", "--json", "--dogcats-dir", dd])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["group_by"] == "all"
        assert data["total"] == 2
        assert "status" in data["counts"]
        assert "type" in data["counts"]
        assert "priority" in data["counts"]
        assert "label" in data["counts"]
        assert data["counts"]["status"]["open"] == 2
        assert data["counts"]["type"]["bug"] == 1
        assert data["counts"]["label"]["cli"] == 1

    def test_chart_by_label(self, tmp_path: Path) -> None:
        """Chart grouped by label shows label distribution."""
        dd = _init(tmp_path)
        _create_issue(dd, "CLI bug", labels="cli")
        _create_issue(dd, "CLI feature", labels="cli,ux")
        _create_issue(dd, "API task", labels="api")

        result = runner.invoke(app, ["chart", "--by", "label", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "Label Distribution" in result.stdout
        assert "cli" in result.stdout
        assert "api" in result.stdout

    def test_chart_by_label_json(self, tmp_path: Path) -> None:
        """Chart --json --by label produces label counts."""
        dd = _init(tmp_path)
        _create_issue(dd, "CLI bug", labels="cli")
        _create_issue(dd, "CLI feature", labels="cli,ux")
        _create_issue(dd, "API task", labels="api")

        result = runner.invoke(
            app, ["chart", "--json", "--by", "label", "--dogcats-dir", dd]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["group_by"] == "label"
        assert data["total"] == 3
        assert data["counts"]["cli"] == 2
        assert data["counts"]["ux"] == 1
        assert data["counts"]["api"] == 1

    def test_chart_by_label_no_labels(self, tmp_path: Path) -> None:
        """Chart by label with no labeled issues shows 'no issues'."""
        dd = _init(tmp_path)
        _create_issue(dd, "No labels")

        result = runner.invoke(app, ["chart", "--by", "label", "--dogcats-dir", dd])
        assert result.exit_code == 0
        assert "no issues" in result.stdout
