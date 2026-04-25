"""Tests for Dogcat CLI commands."""

import json
import subprocess
from pathlib import Path

import pytest
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

    def test_doctor_detects_unparseable_config(self, tmp_path: Path) -> None:
        """Doctor reports config.toml that exists but doesn't parse.

        Regression for dogcat-5ctk: previously the parse error was
        swallowed and the doctor reported success while the user's
        settings were silently ignored.
        """
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        (dogcats_dir / "issues.jsonl").touch()
        (dogcats_dir / "config.toml").write_text("this is [not valid toml")

        result = runner.invoke(
            app, ["doctor", "--dogcats-dir", str(dogcats_dir), "--json"]
        )
        assert result.exit_code != 0
        output = json.loads(result.stdout)
        assert "config_toml_parseable" in output["checks"]
        assert output["checks"]["config_toml_parseable"]["passed"] is False


class TestDoctorFixDanglingDeps:
    """Tests for ``dcat doctor --fix`` repairing dangling dependencies.

    Regression for dogcat-3v9b: the helper ``remove_dependencies`` was
    unit-tested but the doctor wiring that calls it was not.
    """

    def test_fix_removes_dangling_dependency(self, tmp_path: Path) -> None:
        """A dependency referencing a missing issue is removed by --fix."""
        dogcats_dir = tmp_path / ".dogcats"
        _init_with_namespace(dogcats_dir, "ns")

        from dogcat.storage import JSONLStorage

        storage_path = dogcats_dir / "issues.jsonl"
        storage = JSONLStorage(str(storage_path))
        from dogcat.models import Issue

        storage.create(Issue(id="aaaa", namespace="ns", title="A"))

        # Hand-write a dependency record pointing at a non-existent issue,
        # the way a hand-edit or merge artifact would surface a dangling dep.
        with storage_path.open("ab") as f:
            f.write(
                b'{"record_type": "dependency", '
                b'"issue_id": "ns-aaaa", '
                b'"depends_on_id": "ns-ghost", '
                b'"type": "blocks", '
                b'"created_at": "2026-04-25T12:00:00+00:00"}\n'
            )

        # Sanity: dep is dangling now
        storage2 = JSONLStorage(str(storage_path))
        assert len(storage2.find_dangling_dependencies()) == 1

        runner.invoke(app, ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)])

        storage3 = JSONLStorage(str(storage_path))
        assert storage3.find_dangling_dependencies() == []


class TestDoctorFixIssuePrefixMigration:
    """Tests for ``dcat doctor --fix`` migrating ``issue_prefix`` → ``namespace``.

    Regression for dogcat-3v9b: ``migrate_config_keys`` was unit-tested
    but the doctor wiring that calls it was not.
    """

    def test_fix_migrates_deprecated_issue_prefix_key(self, tmp_path: Path) -> None:
        """A config.toml with ``issue_prefix`` is migrated to ``namespace``."""
        from dogcat.config import load_config

        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        (dogcats_dir / "issues.jsonl").touch()
        (dogcats_dir / "config.toml").write_text('issue_prefix = "legacy"\n')

        result = runner.invoke(
            app, ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)]
        )
        # The fix should run and either succeed or progress.
        assert "Fixed" in result.stdout or result.exit_code == 0

        config = load_config(str(dogcats_dir))
        assert config.get("namespace") == "legacy"
        assert "issue_prefix" not in config


class TestAtomicSettingsWrite:
    """Regression tests for dogcat-3yz1: settings.json must be written atomically.

    The previous ``settings_path.write_text(...)`` call could leave a
    partial file on crash and would last-writer-wins on concurrent edits.
    The replacement uses a temp + fsync + replace pattern.
    """

    def test_settings_json_replaced_atomically(self, tmp_path: Path) -> None:
        """``_atomic_write_json`` produces valid JSON and replaces target."""
        from dogcat.cli._cmd_doctor import _atomic_write_json

        target = tmp_path / "settings.json"
        target.write_text('{"old": true}')
        _atomic_write_json(target, {"hooks": {"PreCompact": []}})
        assert target.exists()
        # Reload and verify shape — atomic replace should not leave junk.
        reloaded = json.loads(target.read_text())
        assert reloaded == {"hooks": {"PreCompact": []}}

    def test_settings_json_no_temp_left_behind(self, tmp_path: Path) -> None:
        """No leftover .json tempfiles remain after a successful write."""
        from dogcat.cli._cmd_doctor import _atomic_write_json

        target = tmp_path / "settings.json"
        _atomic_write_json(target, {"k": 1})
        siblings = [
            p for p in tmp_path.iterdir() if p != target and p.suffix == ".json"
        ]
        assert siblings == []


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


class TestDoctorPreCompactHook:
    """Test doctor check for Claude Code PreCompact hook."""

    def test_no_check_without_claude_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor skips PreCompact check when .claude/ doesn't exist."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        assert "claude_precompact" not in data["checks"]

    def test_warns_when_hook_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor warns when .claude/ exists but PreCompact hook is missing."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}")

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        check = data["checks"]["claude_precompact"]
        assert check["passed"] is False
        assert check.get("optional") is True

    def test_passes_when_hook_present(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor passes when PreCompact hook with dcat prime --replay exists."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {
            "hooks": {
                "PreCompact": [
                    {
                        "matcher": "",
                        "hooks": [
                            {"type": "command", "command": "dcat prime --replay"}
                        ],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings))

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        assert data["checks"]["claude_precompact"]["passed"] is True

    def test_detects_hook_in_local_settings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor finds PreCompact hook in settings.local.json."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}")
        settings = {
            "hooks": {
                "PreCompact": [
                    {
                        "matcher": "",
                        "hooks": [
                            {"type": "command", "command": "dcat prime --replay"}
                        ],
                    }
                ]
            }
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(settings))

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        assert data["checks"]["claude_precompact"]["passed"] is True

    def test_fix_installs_hook(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor --fix installs PreCompact hook."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}")

        result = runner.invoke(
            app,
            ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Installed PreCompact hook" in result.stdout

        # Verify it was written with --replay
        data = json.loads((claude_dir / "settings.json").read_text())
        hooks = data["hooks"]["PreCompact"]
        assert any(
            "dcat prime --replay" in h.get("command", "")
            for group in hooks
            for h in group.get("hooks", [])
        )

    def test_fix_prefers_local_settings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor --fix writes to settings.local.json when it exists."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}")
        (claude_dir / "settings.local.json").write_text('{"permissions": {}}')

        runner.invoke(
            app,
            ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)],
        )

        # Hook should be in local, not project settings
        local_data = json.loads((claude_dir / "settings.local.json").read_text())
        project_data = json.loads((claude_dir / "settings.json").read_text())
        assert "PreCompact" in local_data.get("hooks", {})
        assert "PreCompact" not in project_data.get("hooks", {})
        # Existing keys preserved
        assert "permissions" in local_data

    def test_warns_when_old_hook_without_replay(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor warns when PreCompact hook uses 'dcat prime' without --replay."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {
            "hooks": {
                "PreCompact": [
                    {
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "dcat prime"}],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings))

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        check = data["checks"]["claude_precompact"]
        assert check["passed"] is False
        assert check.get("optional") is True
        assert "--replay" in check.get("description", "")

    def test_fix_upgrades_old_hook(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor --fix upgrades old 'dcat prime' hook to 'dcat prime --replay'."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {
            "hooks": {
                "PreCompact": [
                    {
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "dcat prime"}],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings))

        result = runner.invoke(
            app,
            ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)],
        )
        assert "Upgraded PreCompact hook" in result.stdout

        # Verify the hook was updated
        data = json.loads((claude_dir / "settings.json").read_text())
        hooks = data["hooks"]["PreCompact"]
        assert any(
            "dcat prime --replay" in h.get("command", "")
            for group in hooks
            for h in group.get("hooks", [])
        )

    def test_fix_merges_with_existing_hooks(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor --fix merges with existing hooks config."""
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo hi"}],
                    }
                ]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        runner.invoke(
            app,
            ["doctor", "--fix", "--dogcats-dir", str(dogcats_dir)],
        )

        data = json.loads((claude_dir / "settings.json").read_text())
        assert "PreToolUse" in data["hooks"]
        assert "PreCompact" in data["hooks"]


class TestDoctorLocalConfigGitignore:
    """Test doctor check for config.local.toml gitignore status."""

    def _init_git_repo(self, path: Path) -> None:
        """Initialize a git repo at the given path."""
        subprocess.run(
            ["git", "init"],
            cwd=str(path),
            capture_output=True,
            check=True,
        )

    def test_no_check_when_local_config_missing(self, tmp_path: Path) -> None:
        """Doctor skips check when config.local.toml doesn't exist."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        assert "local_config_gitignored" not in data["checks"]

    def test_warns_when_not_gitignored(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor warns when config.local.toml exists but is not gitignored."""
        monkeypatch.chdir(tmp_path)
        self._init_git_repo(tmp_path)

        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Create config.local.toml without adding to .gitignore
        # (remove from .gitignore if init added it)
        gitignore = tmp_path / ".gitignore"
        if gitignore.exists():
            lines = gitignore.read_text().splitlines()
            lines = [ln for ln in lines if "config.local.toml" not in ln]
            gitignore.write_text("\n".join(lines) + "\n" if lines else "")

        local_config = dogcats_dir / "config.local.toml"
        local_config.write_text('inbox_remote = "/some/path"\n')

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        check = data["checks"]["local_config_gitignored"]
        assert check["passed"] is False
        assert check.get("optional") is True

    def test_passes_when_gitignored(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor passes when config.local.toml is properly gitignored."""
        monkeypatch.chdir(tmp_path)
        self._init_git_repo(tmp_path)

        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Ensure it's in .gitignore
        gitignore = tmp_path / ".gitignore"
        content = gitignore.read_text() if gitignore.exists() else ""
        if ".dogcats/config.local.toml" not in content:
            with gitignore.open("a") as f:
                f.write(".dogcats/config.local.toml\n")

        local_config = dogcats_dir / "config.local.toml"
        local_config.write_text('inbox_remote = "/some/path"\n')

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        data = json.loads(result.stdout)
        check = data["checks"]["local_config_gitignored"]
        assert check["passed"] is True


class TestDoctorIdDistribution:
    """Test the opt-in --check-id-distribution flag."""

    def test_flag_omitted_by_default(self, tmp_path: Path) -> None:
        """Without the flag, no id_distribution check or table is reported."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        result = runner.invoke(
            app, ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)]
        )
        data = json.loads(result.stdout)
        assert "id_distribution" not in data
        assert "id_distribution" not in data["checks"]

    def test_flag_emits_distribution_table(self, tmp_path: Path) -> None:
        """With the flag, the distribution table is rendered in human output."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            ["create", "Test", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "doctor",
                "--check-id-distribution",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        assert "ID distribution:" in result.stdout
        assert "p_step" in result.stdout
        assert "p_all" in result.stdout

    def test_flag_emits_distribution_json(self, tmp_path: Path) -> None:
        """With the flag, JSON output exposes the id_distribution rows."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            ["create", "Test", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "doctor",
                "--check-id-distribution",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(result.stdout)
        assert "id_distribution" in data
        rows: list[dict[str, object]] = data["id_distribution"]
        assert isinstance(rows, list)
        assert rows, "expected at least one namespace row"
        row = rows[0]
        assert {"namespace", "count", "length", "p_step", "p_cumulative"} <= set(row)
        assert isinstance(row["count"], int)
        assert row["count"] >= 1
        assert isinstance(row["p_step"], float)
        assert 0.0 <= row["p_step"] <= 1.0
        assert isinstance(row["p_cumulative"], float)
        assert 0.0 <= row["p_cumulative"] <= 1.0

    def test_check_passes_for_small_database(self, tmp_path: Path) -> None:
        """A tiny database is well below the 5% cumulative threshold."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(
            app,
            ["create", "Test", "--dogcats-dir", str(dogcats_dir)],
        )

        result = runner.invoke(
            app,
            [
                "doctor",
                "--check-id-distribution",
                "--json",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )
        data = json.loads(result.stdout)
        assert data["checks"]["id_distribution"]["passed"] is True
