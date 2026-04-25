"""Tests for `dcat random`."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


def _init(tmp_path: Path) -> Path:
    dogcats_dir = tmp_path / ".dogcats"
    runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    return dogcats_dir


def _create(dogcats_dir: Path, *args: str) -> str:
    result = runner.invoke(app, ["create", *args, "--dogcats-dir", str(dogcats_dir)])
    assert result.exit_code == 0, result.stdout
    return result.stdout.split(": ")[0].split()[-1]


class TestCLIRandom:
    """Tests for the random pick command."""

    def test_random_picks_one_issue(self, tmp_path: Path) -> None:
        """Random returns one issue from the candidate set."""
        dogcats_dir = _init(tmp_path)
        ids = {_create(dogcats_dir, f"Issue {i}") for i in range(5)}

        result = runner.invoke(app, ["random", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        # show-style output starts with `ID: <id>`
        first_line = result.stdout.splitlines()[0]
        assert first_line.startswith("ID: ")
        picked_id = first_line.removeprefix("ID: ").strip()
        assert picked_id in ids

    def test_random_empty_set_exits_1(self, tmp_path: Path) -> None:
        """Empty candidate set prints `No issues found` and exits 1."""
        dogcats_dir = _init(tmp_path)
        _create(dogcats_dir, "Only issue")

        result = runner.invoke(
            app,
            ["random", "--priority", "9", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 1
        assert "No issues found" in result.stdout

    def test_random_empty_json_emits_null_exit_1(self, tmp_path: Path) -> None:
        """Empty candidate set in JSON mode emits `null` and exits 1."""
        dogcats_dir = _init(tmp_path)

        result = runner.invoke(
            app, ["random", "--json", "--dogcats-dir", str(dogcats_dir)]
        )
        assert result.exit_code == 1
        assert result.stdout.strip() == "null"

    def test_random_json_shape_matches_show(self, tmp_path: Path) -> None:
        """`random --json` returns the same shape as `show --json`."""
        dogcats_dir = _init(tmp_path)
        issue_id = _create(dogcats_dir, "Lonely issue")

        rand_result = runner.invoke(
            app, ["random", "--json", "--dogcats-dir", str(dogcats_dir)]
        )
        assert rand_result.exit_code == 0
        rand_data = json.loads(rand_result.stdout)

        show_result = runner.invoke(
            app,
            ["show", issue_id, "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        show_data = json.loads(show_result.stdout)

        assert rand_data == show_data

    def test_random_honors_label_filter(self, tmp_path: Path) -> None:
        """`--label` restricts the candidate set."""
        dogcats_dir = _init(tmp_path)
        wanted_ids = {
            _create(dogcats_dir, f"Match {i}", "--labels", "wanted") for i in range(3)
        }
        for i in range(5):
            _create(dogcats_dir, f"Other {i}", "--labels", "other")

        for _ in range(20):
            result = runner.invoke(
                app,
                [
                    "random",
                    "--label",
                    "wanted",
                    "--json",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            full_id = f"{data['namespace']}-{data['id']}"
            assert full_id in wanted_ids

    def test_random_honors_closed_filter(self, tmp_path: Path) -> None:
        """Default excludes closed; `--closed` restricts to closed."""
        dogcats_dir = _init(tmp_path)
        open_id = _create(dogcats_dir, "Open one")
        closed_id = _create(dogcats_dir, "Will close")
        runner.invoke(
            app,
            ["close", closed_id, "--dogcats-dir", str(dogcats_dir)],
        )

        # Default excludes closed
        for _ in range(10):
            result = runner.invoke(
                app, ["random", "--json", "--dogcats-dir", str(dogcats_dir)]
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert f"{data['namespace']}-{data['id']}" == open_id

        # --closed picks only the closed one
        for _ in range(5):
            result = runner.invoke(
                app,
                ["random", "--closed", "--json", "--dogcats-dir", str(dogcats_dir)],
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert f"{data['namespace']}-{data['id']}" == closed_id

    def test_random_text_output_includes_show_sections(self, tmp_path: Path) -> None:
        """Random renders the picked issue with the same sections as `show`."""
        dogcats_dir = _init(tmp_path)
        _create(dogcats_dir, "Solo issue", "-d", "A description")

        result = runner.invoke(app, ["random", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 0
        out = result.stdout
        assert "ID: " in out
        assert "Title: Solo issue" in out
        assert "Description:" in out
        assert "A description" in out

    def test_random_comments_filters_mutually_exclusive(self, tmp_path: Path) -> None:
        """`--has-comments` and `--without-comments` cannot be combined."""
        dogcats_dir = _init(tmp_path)
        _create(dogcats_dir, "Issue")

        result = runner.invoke(
            app,
            [
                "random",
                "--has-comments",
                "--without-comments",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in (result.stdout + result.stderr)
