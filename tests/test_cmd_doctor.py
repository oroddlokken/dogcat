"""Tests for Dogcat CLI commands."""

import json
import subprocess
from pathlib import Path

import pytest
from cli_test_helpers import _init_with_namespace, _set_ns_config
from typer.testing import CliRunner

from dogcat.cli import app

runner = CliRunner()


def _assert_doctor_check_passes(dogcats_dir: Path, check_name: str) -> None:
    """Re-run ``dcat doctor`` and assert the named check now reports passed.

    The canonical user flow is ``doctor said X is broken → I --fix → doctor
    confirms X is healthy``. Inspecting the file directly after a --fix
    proves the file changed but not that the originally failing check
    actually passes now (the --fix could have mutated unrelated state
    that *looks* correct). (dogcat-4rb5)
    """
    result = runner.invoke(
        app,
        ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
    )
    data = json.loads(result.stdout)
    checks = data.get("checks", {})
    assert check_name in checks, (
        f"check {check_name!r} not in doctor output keys: {list(checks)}"
    )
    assert checks[check_name]["passed"] is True, (
        f"doctor still reports {check_name} as failing after --fix: "
        f"{checks[check_name]}"
    )


def _doctor_status(
    dogcats_dir: Path, *, extra_args: list[str] | None = None
) -> tuple[int, dict[str, object]]:
    """Run ``dcat doctor --json`` and return (exit_code, parsed payload).

    Avoids substring-matching glyphs (✓/✗) on the human output — the
    structured output exposes per-check ``passed`` booleans and an
    overall ``status`` field. (dogcat-3nfa)
    """
    result = runner.invoke(
        app,
        ["doctor", "--json", "--dogcats-dir", str(dogcats_dir), *(extra_args or [])],
    )
    return result.exit_code, json.loads(result.stdout)


def _failed_check_names(payload: dict[str, object]) -> set[str]:
    """Return the set of check names that reported ``passed: false``."""
    raw_checks = payload.get("checks")
    if not isinstance(raw_checks, dict):
        return set()
    failed: set[str] = set()
    items: list[tuple[object, object]] = list(raw_checks.items())  # type: ignore[arg-type]
    for name, data in items:
        if not isinstance(data, dict):
            continue
        passed = data.get("passed", True)  # type: ignore[misc]
        if not passed:
            failed.add(str(name))
    return failed


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
        assert "✗" in result.stdout
        # The failing row must state the failure, not the pass-phrased
        # description — the renderer prints `fail_description or description`,
        # so a missing fail_description rendered "✗ .dogcats/ directory
        # exists". (dogcat-1ah3)
        assert "No dogcat store found at" in result.stdout
        assert "✗ .dogcats/ directory exists" not in result.stdout

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

        exit_code, payload = _doctor_status(dogcats_dir)
        assert exit_code != 0
        assert "issues_jsonl" in _failed_check_names(payload)

    def test_doctor_missing_config_toml(self, tmp_path: Path) -> None:
        """Test doctor detects missing config.toml."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.touch()

        exit_code, payload = _doctor_status(dogcats_dir)
        assert exit_code != 0
        failed = _failed_check_names(payload)
        assert "config_toml" in failed
        # Prefix check is skipped when config.toml is missing — i.e., it
        # is either absent from the payload or not in the failed set.
        assert "namespace_config_mutual" not in failed

    def test_doctor_empty_namespace(self, tmp_path: Path) -> None:
        """Test doctor detects empty namespace in config.toml."""
        dogcats_dir = tmp_path / ".dogcats"
        dogcats_dir.mkdir()
        issues_file = dogcats_dir / "issues.jsonl"
        issues_file.touch()

        # Create config.toml with empty namespace
        config_file = dogcats_dir / "config.toml"
        config_file.write_text('namespace = ""\n')

        exit_code, payload = _doctor_status(dogcats_dir)
        assert exit_code != 0
        failed = _failed_check_names(payload)
        # Some check related to namespace must have failed.
        assert any("namespace" in name for name in failed), (
            f"expected a namespace check to fail, got: {failed}"
        )

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

        # Re-run doctor: the originally failing check must now pass.
        _assert_doctor_check_passes(dogcats_dir, "config_toml")

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


class TestDoctorCheckDataclass:
    """Unit tests for the HealthCheck / HealthReport refactor (dogcat-3gsn).

    The dataclass exists to stop the "if not passed: all_passed = False"
    bookkeeping repeating after every check; this test pins down the
    pieces that were previously implicit in the dict-shape pattern.
    """

    def test_required_check_failure_flips_all_passed(self) -> None:
        """A non-optional failed check fails the overall report."""
        from dogcat.cli._cmd_doctor import HealthCheck, HealthReport

        report = HealthReport()
        report.add("ok", HealthCheck(description="ok", passed=True))
        assert report.all_passed is True
        report.add("bad", HealthCheck(description="bad", passed=False))
        assert report.all_passed is False

    def test_optional_check_failure_does_not_flip_all_passed(self) -> None:
        """An optional failed check is informational; doesn't fail the report."""
        from dogcat.cli._cmd_doctor import HealthCheck, HealthReport

        report = HealthReport()
        report.add(
            "warn",
            HealthCheck(description="warn", passed=False, optional=True),
        )
        assert report.all_passed is True

    def test_to_dict_omits_unset_optional_fields(self) -> None:
        """Legacy serialization only emits keys that were actually populated."""
        from dogcat.cli._cmd_doctor import HealthCheck

        check = HealthCheck(description="just a check", passed=True)
        assert check.to_dict() == {"description": "just a check", "passed": True}

    def test_to_dict_includes_all_set_fields(self) -> None:
        """All populated fields surface in the legacy dict shape."""
        from dogcat.cli._cmd_doctor import HealthCheck

        check = HealthCheck(
            description="d",
            passed=False,
            fix="run thing",
            fail_description="oh no",
            optional=True,
            note="careful",
        )
        assert check.to_dict() == {
            "description": "d",
            "passed": False,
            "fix": "run thing",
            "fail_description": "oh no",
            "optional": True,
            "note": "careful",
        }


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

        # Re-run doctor: the data_integrity check that surfaced the
        # dangling dep must now pass. (dogcat-4rb5)
        _assert_doctor_check_passes(dogcats_dir, "data_integrity")


class TestDoctorRemediesNameCommands:
    """A failed check's Fix line must name a command, not a file to edit.

    "Review errors above and fix issues.jsonl" pointed the user at the
    append-only store. Hand-editing it corrupts the audit log that the
    merge driver and compaction both read in order — the exact edit
    AGENTS.md forbids. (dogcat-4opn)
    """

    def test_data_integrity_fix_names_a_command(self, tmp_path: Path) -> None:
        """The data_integrity remedy names dcat update, not the JSONL file."""
        from dogcat.models import Issue
        from dogcat.storage import JSONLStorage

        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        storage_path = dogcats_dir / "issues.jsonl"
        JSONLStorage(str(storage_path)).create(
            Issue(id="aaaa", namespace="ns", title="A")
        )
        with storage_path.open("ab") as f:
            f.write(
                b'{"record_type": "dependency", '
                b'"issue_id": "ns-aaaa", '
                b'"depends_on_id": "ns-ghost", '
                b'"type": "blocks", '
                b'"created_at": "2026-04-25T12:00:00+00:00"}\n'
            )

        result = runner.invoke(app, ["doctor", "--dogcats-dir", str(dogcats_dir)])

        assert result.exit_code != 0
        assert "dcat update <id>" in result.stdout
        assert "Do not edit issues.jsonl by hand" in result.stdout
        assert "Review errors above and fix issues.jsonl" not in result.stdout


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

        # Re-run doctor: the deprecated-keys check must now pass. (dogcat-4rb5)
        _assert_doctor_check_passes(dogcats_dir, "config_deprecated_keys")


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

        # Re-run doctor: the namespace mutual-exclusion check must now
        # pass. (dogcat-4rb5)
        _assert_doctor_check_passes(dogcats_dir, "namespace_config_mutual")

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

    def test_non_dict_settings_does_not_crash_doctor(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doctor handles a non-dict settings.json (e.g. ``[]``) gracefully.

        Regression for dogcat-2yho: a user file containing ``[]``,
        ``null``, or a scalar used to crash doctor with AttributeError
        — and doctor IS the recovery tool, so it must not crash.
        """
        monkeypatch.chdir(tmp_path)
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        # Non-dict — used to crash doctor.
        (claude_dir / "settings.json").write_text("[]")

        result = runner.invoke(
            app,
            ["doctor", "--json", "--dogcats-dir", str(dogcats_dir)],
        )
        # Must not crash; doctor reports the hook as missing.
        data = json.loads(result.stdout)
        assert data["checks"]["claude_precompact"]["passed"] is False

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

        # Re-run doctor: the claude_precompact check must now pass. (dogcat-4rb5)
        _assert_doctor_check_passes(dogcats_dir, "claude_precompact")

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


class TestDoctorPostMergeSkipReasons:
    """``doctor --post-merge`` must surface a clear skip reason instead of silent pass.

    Regression for dogcat-40t6: when not in a git repo, or when .dogcats
    is outside the repo root, the concurrent-edit detector silently
    no-op'd, so the user thought no concurrent edits were detected.
    """

    def test_post_merge_skip_outside_git_repo(self, tmp_path: Path) -> None:
        """Outside any git repo, the skip reason is reported on stderr."""
        dogcats_dir = tmp_path / ".dogcats"
        # Initialize without a git repo wrapper.
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        # Run doctor with --post-merge and --json from a path that isn't
        # under a git repo. The CWD for tests is typically the dogcat
        # repo, so use --dogcats-dir to point at our tmp_path; the git
        # check operates on cwd -> repo_root, which finds dogcat. To
        # make this deterministic, mock dogcat.git.repo_root.
        from unittest.mock import patch

        with patch("dogcat.git.repo_root", return_value=None):
            result = runner.invoke(
                app,
                [
                    "doctor",
                    "--post-merge",
                    "--json",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
        data = json.loads(result.stdout)
        assert data["post_merge_skipped"].startswith(
            "post-merge skipped: not inside a git repository"
        )

    def test_post_merge_skip_external_dogcats(self, tmp_path: Path) -> None:
        """When .dogcats is outside the repo root, surface a skip reason."""
        dogcats_dir = tmp_path / "external" / ".dogcats"
        dogcats_dir.parent.mkdir()
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])

        from unittest.mock import patch

        # repo_root() returns a path that does not contain dogcats_dir.
        unrelated_repo = tmp_path / "repo"
        unrelated_repo.mkdir()
        with patch("dogcat.git.repo_root", return_value=unrelated_repo.resolve()):
            result = runner.invoke(
                app,
                [
                    "doctor",
                    "--post-merge",
                    "--json",
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
        data = json.loads(result.stdout)
        assert "outside the git repo" in data["post_merge_skipped"]


class TestDoctorGlobalConfig:
    """Tests for testdoctorglobalconfig."""

    def test_doctor_reports_global_config_present(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify doctor reports global config present."""
        from dogcat.global_config import save_global_config_value

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "repo"
        repo.mkdir()
        runner.invoke(app, ["init", "--dogcats-dir", str(repo / ".dogcats")])
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["doctor"])
        assert "global config" in result.output.lower()
        assert str(global_store) in result.output

    def test_doctor_no_global_config_section(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify doctor no global config section."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        runner.invoke(app, ["init", "--dogcats-dir", str(repo / ".dogcats")])
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["doctor"])
        assert "global config" in result.output.lower()
        assert "not configured" in result.output.lower()


class TestExtractedDoctorHelpers:
    """Unit tests for the extracted per-check + renderer functions (dogcat-671h)."""

    def test_check_dogcats_dir_present(self, tmp_path: Path) -> None:
        """The .dogcats existence check passes when the directory exists."""
        from dogcat.cli._cmd_doctor import _check_dogcats_dir

        d = tmp_path / ".dogcats"
        d.mkdir()
        check = _check_dogcats_dir(str(d))
        assert check.passed is True

    def test_check_dogcats_dir_missing(self, tmp_path: Path) -> None:
        """The check fails (with an init fix hint) when the directory is absent."""
        from dogcat.cli._cmd_doctor import _check_dogcats_dir

        check = _check_dogcats_dir(str(tmp_path / "nope"))
        assert check.passed is False
        assert "dcat init" in (check.fix or "")
        # Without fail_description the renderer falls back to description,
        # printing a passing claim beside a ✗. (dogcat-1ah3)
        assert check.fail_description is not None
        assert "No dogcat store found at" in check.fail_description

    def test_id_uniqueness_failure_does_not_print_pass_phrasing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failing ID-uniqueness check must not render "All issue IDs are unique".

        The renderer prints `fail_description or description`, so without a
        fail_description this row read "✗ All issue IDs are unique". Forcing
        the check false is the only way to reach that branch — duplicate IDs
        cannot be produced through the CLI. (dogcat-1ah3)
        """
        from dogcat.storage import JSONLStorage

        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        runner.invoke(app, ["create", "Something", "--dogcats-dir", str(dogcats_dir)])

        def _not_unique(_self: JSONLStorage) -> bool:
            return False

        monkeypatch.setattr(
            JSONLStorage, "check_id_uniqueness", _not_unique, raising=True
        )
        result = runner.invoke(app, ["doctor", "--dogcats-dir", str(dogcats_dir)])

        assert result.exit_code != 0
        assert "✗ All issue IDs are unique" not in result.stdout
        assert "Issue ID uniqueness check failed" in result.stdout

    def test_check_dcat_in_path_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A dcat binary on PATH is a plain (non-optional) pass."""
        from dogcat.cli import _cmd_doctor

        def _which_found(_name: str) -> str:
            return "/usr/bin/dcat"

        monkeypatch.setattr(_cmd_doctor.shutil, "which", _which_found)
        check = _cmd_doctor._check_dcat_in_path()
        assert check.passed is True
        assert check.optional is False

    def test_check_dcat_in_path_missing_is_optional_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing PATH binary is an optional warning with a completions note."""
        from dogcat.cli import _cmd_doctor

        def _which_missing(_name: str) -> str | None:
            return None

        monkeypatch.setattr(_cmd_doctor.shutil, "which", _which_missing)
        check = _cmd_doctor._check_dcat_in_path()
        assert check.passed is False
        assert check.optional is True
        assert check.note is not None

    def test_render_doctor_json_shape(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The JSON renderer emits status + per-check passed/fix fields."""
        from dogcat.cli._cmd_doctor import _render_doctor_json
        from dogcat.cli._health import HealthCheck

        checks = {
            "a": HealthCheck(description="A", passed=True),
            "b": HealthCheck(description="B", passed=False, fix="do x"),
        }
        _render_doctor_json(
            checks,
            all_passed=False,
            validation=[],
            merge_warnings=[],
            post_merge_skip_reason=None,
            id_distribution=[],
        )
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "issues_found"
        assert data["checks"]["a"]["passed"] is True
        assert data["checks"]["b"]["fix"] == "do x"

    def test_render_doctor_text_marks_pass_and_fail(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The text renderer shows descriptions, the fix hint, and the summary."""
        from dogcat.cli._cmd_doctor import _render_doctor_text
        from dogcat.cli._health import HealthCheck

        checks = {
            "a": HealthCheck(description="A ok", passed=True),
            "b": HealthCheck(description="B bad", passed=False, fix="fix b"),
        }
        _render_doctor_text(
            checks,
            all_passed=False,
            validation=[],
            merge_warnings=[],
            id_distribution=[],
        )
        out = capsys.readouterr().out
        assert "A ok" in out
        assert "B bad" in out
        assert "fix b" in out
        assert "Some checks failed" in out
