"""Tests for Dogcat CLI commands."""

import json
from pathlib import Path

from cli_test_helpers import _init_with_namespace, _set_ns_config
from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


class TestCLIDoctor:
    """Test doctor diagnostic command."""

    def test_doctor_with_proper_setup(self, tmp_path: Path) -> None:
        """Test doctor command with properly configured repository."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        # Should pass basic checks even without git config
        assert ".dogcats/ directory exists" in result.stdout
        assert ".dogcats/issues.jsonl is valid JSON" in result.stdout

    def test_doctor_missing_dogcats(self, tmp_path: Path) -> None:
        """Test doctor command with missing .dogcats directory."""
        dogcats_dir = tmp_path / ".dogcats"

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert ".dogcats/ directory exists" in result.stdout
        assert "✗" in result.stdout

    def test_doctor_json_output(self, tmp_path: Path) -> None:
        """Test doctor command with JSON output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir), "--json"],
        )
        # When dogcat is properly installed in venv, all checks pass
        assert result.exit_code == 0

        # Parse JSON output
        output = json.loads(result.stdout)
        assert "status" in output
        assert output["status"] == "ok"
        assert "checks" in output
        assert isinstance(output["checks"], dict)

        # Verify check structure
        for check_data in output["checks"].values():
            assert "passed" in check_data
            assert "description" in check_data
            assert isinstance(check_data["passed"], bool)

    def test_doctor_with_invalid_jsonl(self, tmp_path: Path) -> None:
        """Test doctor command with corrupted JSONL file."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()

        # Create invalid JSON
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.write_text("not valid json\n")

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "is valid JSON" in result.stdout
        assert "✗" in result.stdout

    def test_doctor_missing_config_toml(self, tmp_path: Path) -> None:
        """Test doctor detects missing config.toml."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.touch()

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "config.toml not found" in result.stdout
        assert "✗" in result.stdout
        # Prefix check should be skipped when config.toml is missing
        assert "namespace is not configured" not in result.stdout

    def test_doctor_empty_namespace(self, tmp_path: Path) -> None:
        """Test doctor detects empty namespace in config.toml."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.touch()

        # Create config.toml with empty namespace
        config_file = dogcats_dir / "config.toml"
        config_file.write_text('namespace = ""\n')

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "namespace is not configured" in result.stdout
        assert "✗" in result.stdout

    def test_doctor_fix_missing_config(self, tmp_path: Path) -> None:
        """Test doctor --fix creates config.toml with auto-detected prefix."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.touch()

        config_file = dogcats_dir / "config.toml"
        assert not config_file.exists()

        result = runner.invoke(
            app,
            ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)],
        )
        assert config_file.exists()
        assert "Fixed: Created config.toml" in result.stdout

    def test_doctor_valid_config(self, tmp_path: Path) -> None:
        """Test doctor passes when config.toml is properly set up."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "config.toml exists" in result.stdout
        assert "namespace is configured" in result.stdout
        # Both config checks should pass (green checkmarks)
        # Count the ✗ marks - there should be none for config checks
        lines = result.stdout.splitlines()
        config_lines = [ln for ln in lines if "config.toml" in ln or "namespace" in ln]
        for line in config_lines:
            assert "✗" not in line

    def test_doctor_finds_dogcats_from_subdirectory(self, tmp_path: Path) -> None:
        """Test doctor resolves .dogcats when run from a subdirectory."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(
            app,
            ["init", "--dogcats-dir", str(dogcats_dir)],
        )

        # Create a nested subdirectory and run doctor from there
        subdir = tmp_path / "a" / "b" / "c"
        subdir.mkdir(parents=True)

        import os

        old_cwd = Path.cwd()
        try:
            os.chdir(subdir)
            # Run without --dogcats-dir so it must walk up to find it
            result = runner.invoke(app, ["doctor"])
            assert "✓" in result.stdout
            assert ".dogcats/ directory exists" in result.stdout
        finally:
            os.chdir(old_cwd)


class TestDoctorNamespaceConfig:
    """Test doctor checks for namespace config mutual exclusivity."""

    def test_both_keys_warns(self, tmp_path: Path) -> None:
        """Both keys set → doctor warns."""
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")
        _set_ns_config(dogcats_dir, "visible_namespaces", ["a"])
        _set_ns_config(dogcats_dir, "hidden_namespaces", ["b"])

        result = runner.invoke(app, ["doctor", "--dogcats-dir", str(dogcats_dir)])
        assert result.exit_code == 1
        assert "visible_namespaces" in result.stdout
        assert "hidden_namespaces" in result.stdout

    def test_both_keys_fix_removes_hidden(self, tmp_path: Path) -> None:
        """Both keys set + --fix → removes hidden_namespaces."""
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")
        _set_ns_config(dogcats_dir, "visible_namespaces", ["a"])
        _set_ns_config(dogcats_dir, "hidden_namespaces", ["b"])

        result = runner.invoke(
            app,
            ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Removed 'hidden_namespaces'" in result.stdout

        from dogcat.config import load_config

        config = load_config(str(dogcats_dir))
        assert "hidden_namespaces" not in config
        assert "visible_namespaces" in config

    def test_only_one_key_no_warning(self, tmp_path: Path) -> None:
        """Only one set → no warning."""
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "proj")
        _set_ns_config(dogcats_dir, "visible_namespaces", ["a"])

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        assert data["checks"]["namespace_config_mutual"]["passed"] is True


class TestDoctorInbox:
    """Test doctor inbox.jsonl validation."""

    def test_doctor_no_inbox_no_check(self, tmp_path: Path) -> None:
        """Doctor skips inbox checks when inbox.jsonl doesn't exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "inbox_jsonl" not in data["checks"]
        assert "inbox_data_integrity" not in data["checks"]

    def test_doctor_valid_inbox(self, tmp_path: Path) -> None:
        """Doctor passes when inbox.jsonl is valid."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create a valid proposal
        runner.invoke(
            app,
            ["propose", "Test proposal", "--to", str(tmp_path), "--json"],
        )

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "inbox.jsonl is valid JSON" in result.stdout
        assert "Inbox data integrity" in result.stdout

    def test_doctor_valid_inbox_json(self, tmp_path: Path) -> None:
        """Doctor JSON output includes inbox checks when inbox exists."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        runner.invoke(
            app,
            ["propose", "Test proposal", "--to", str(tmp_path), "--json"],
        )

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["checks"]["inbox_jsonl"]["passed"] is True
        assert data["checks"]["inbox_data_integrity"]["passed"] is True

    def test_doctor_invalid_inbox_json(self, tmp_path: Path) -> None:
        """Doctor detects invalid JSON in inbox.jsonl."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Write invalid JSON to inbox.jsonl
        inbox_file = dogcats_dir / "inbox.jsonl"
        inbox_file.write_text("not valid json\n")

        result = runner.invoke(
            app,
            ["doctor", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code != 0
        assert "inbox.jsonl is valid JSON" in result.stdout
        assert "✗" in result.stdout

    def test_doctor_inbox_invalid_status(self, tmp_path: Path) -> None:
        """Doctor detects invalid proposal status."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        import orjson

        inbox_file = dogcats_dir / "inbox.jsonl"
        record = {
            "record_type": "proposal",
            "id": "test",
            "namespace": "dc",
            "title": "Bad status",
            "status": "invalid_status",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        inbox_file.write_bytes(orjson.dumps(record) + b"\n")

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        assert data["checks"]["inbox_data_integrity"]["passed"] is False
        assert any("invalid status" in d["message"] for d in data["validation_details"])

    def test_doctor_inbox_missing_required_fields(self, tmp_path: Path) -> None:
        """Doctor detects missing required fields in proposals."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        import orjson

        inbox_file = dogcats_dir / "inbox.jsonl"
        # Missing title and status
        record = {
            "record_type": "proposal",
            "id": "test",
            "namespace": "dc",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        inbox_file.write_bytes(orjson.dumps(record) + b"\n")

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        assert data["checks"]["inbox_data_integrity"]["passed"] is False
        assert any(
            "missing required field" in d["message"] for d in data["validation_details"]
        )

    def test_doctor_inbox_invalid_timestamp(self, tmp_path: Path) -> None:
        """Doctor detects invalid timestamps in proposals."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        import orjson

        inbox_file = dogcats_dir / "inbox.jsonl"
        record = {
            "record_type": "proposal",
            "id": "test",
            "namespace": "dc",
            "title": "Bad timestamp",
            "status": "open",
            "created_at": "not-a-date",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        inbox_file.write_bytes(orjson.dumps(record) + b"\n")

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        assert data["checks"]["inbox_data_integrity"]["passed"] is False
        assert any(
            "invalid timestamp" in d["message"] for d in data["validation_details"]
        )
