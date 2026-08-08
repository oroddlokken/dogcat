"""Tests for `dcat prime` output paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app
from dogcat.global_config import save_global_config_value

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


class TestPrimeNoLocalNoGlobal:
    """Tests for testprimenolocalnoglobal."""

    def test_message_when_no_dogcats_and_no_global(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify message when no dogcats and no global."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "No .dogcats/ found" in result.output


class TestPrimeWithGlobalConfig:
    """Tests for testprimewithglobalconfig."""

    def test_uses_global_when_no_local(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify uses global when no local."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "læring"
        repo.mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "DOGCAT WORKFLOW GUIDE" in result.output

    def test_message_when_global_storage_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """default_storage points to missing dir → message points at fix-up command."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        save_global_config_value("default_storage", str(tmp_path / "missing"))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "global" in result.output.lower()
        assert "default_storage" in result.output


class TestPrimeGlobalFallbackSection:
    """prime names the active store and namespace in global-fallback mode.

    (dogcat-mbk1) An agent primed in a directory with no visible store
    must learn where its issues actually go and how to opt out.
    """

    def test_names_store_and_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fallback mode: guide opens with store path, namespace, overrides."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "myrepo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "Active Storage (global fallback)" in result.output
        assert str(global_store.resolve()) in result.output
        assert "Namespace: myrepo" in result.output
        assert "dcat init --use-existing-folder" in result.output

    def test_absent_with_local_store(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A locally resolved store keeps the guide unchanged."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "repo"
        (repo / ".dogcats").mkdir(parents=True)
        monkeypatch.chdir(repo)

        result = runner.invoke(app, ["prime"])
        assert result.exit_code == 0
        assert "Active Storage" not in result.output


class TestPrimeDocumentsRealFlags:
    """The doctrine `dcat prime` prints must name options that exist.

    An agent follows this output literally, so a flag listed here that no
    command defines turns into a "No such option" exit on the agent's next
    move. `--editor` sat in the create/update list with no such option
    anywhere in ``src/``. (dogcat-51pg)
    """

    def test_create_update_flag_list_matches_the_commands(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Every --flag prime attributes to create/update must exist on both."""
        import re

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".dogcats").mkdir()

        prime = runner.invoke(app, ["prime"])
        assert prime.exit_code == 0

        marker = "`dcat create` and `dcat update` both support"
        start = prime.output.index(marker)
        paragraph = prime.output[start : prime.output.index("\n\n", start)]
        flags = set(re.findall(r"--[a-z][a-z-]+", paragraph))
        assert flags, "flag paragraph parsed empty — the marker text moved"

        for command in ("create", "update"):
            rendered = runner.invoke(app, [command, "--help"]).output
            # Typer wraps long option lines, so compare against the text with
            # line breaks and padding removed.
            flat = " ".join(rendered.split())
            missing = sorted(f for f in flags if f not in flat)
            assert not missing, f"dcat {command} does not define: {missing}"

    def test_snooze_example_omits_a_nonexistent_until_option(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`snooze` takes the date as its second positional, not --until."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".dogcats").mkdir()

        prime = runner.invoke(app, ["prime"])
        assert "--until" not in prime.output

        snooze_help = " ".join(runner.invoke(app, ["snooze", "--help"]).output.split())
        assert "--until" not in snooze_help


class TestGuideStatesTheDeferredParentException:
    """`dcat guide` must not call parent-child purely organizational.

    `get_ready_work` drops every issue with a deferred ancestor
    (deps.py:93) and `_collapse_deferred_subtrees` hides them from
    `dcat list` unless --expand. Defer an epic and its children vanish
    from both, which "children are NOT blocked by their parent" denies.
    (dogcat-5epn)
    """

    def test_guide_names_the_exception(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The caveat names deferred parents, dcat ready and --expand."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".dogcats").mkdir()

        guide = runner.invoke(app, ["guide"]).output

        assert "purely organizational" not in guide
        assert "deferred parent" in guide
        assert "--expand" in guide

    def test_deferred_parent_collapses_children_as_documented(
        self, tmp_path: Path
    ) -> None:
        """The behaviour the caveat describes is real, and bounded as stated.

        `dcat ready` drops them all; `dcat list` still previews up to
        MAX_PREVIEW_SUBTASKS (3) under the parent and counts the rest,
        which is why the caveat says "previewing up to 3" rather than
        claiming they vanish. (dogcat-5epn)
        """
        from dogcat.constants import MAX_PREVIEW_SUBTASKS

        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        parent = runner.invoke(
            app, ["create", "Epic", "-t", "epic", "--dogcats-dir", str(dogcats_dir)]
        )
        parent_id = parent.stdout.split(": ")[0].split()[-1]

        child_ids: list[str] = []
        for n in range(MAX_PREVIEW_SUBTASKS + 1):
            child = runner.invoke(
                app,
                [
                    "create",
                    f"Child {n}",
                    "--parent",
                    parent_id,
                    "--dogcats-dir",
                    str(dogcats_dir),
                ],
            )
            child_ids.append(child.stdout.split(": ")[0].split()[-1])

        runner.invoke(
            app,
            [
                "update",
                parent_id,
                "--status",
                "deferred",
                "--dogcats-dir",
                str(dogcats_dir),
            ],
        )

        ready = runner.invoke(app, ["ready", "--dogcats-dir", str(dogcats_dir)]).stdout
        listed = runner.invoke(app, ["list", "--dogcats-dir", str(dogcats_dir)]).stdout
        expanded = runner.invoke(
            app, ["list", "--expand", "--dogcats-dir", str(dogcats_dir)]
        ).stdout

        # Ready drops every child of a deferred parent.
        assert not any(cid in ready for cid in child_ids)
        # List previews at most MAX_PREVIEW_SUBTASKS of them.
        shown = [cid for cid in child_ids if cid in listed]
        assert len(shown) == MAX_PREVIEW_SUBTASKS
        assert "hidden" in listed
        # --expand shows all of them.
        assert all(cid in expanded for cid in child_ids)


class TestEnumOptionHelpMatchesTheParsers:
    """Option help must list every value the parser accepts.

    `--status` help on create and update omitted `closed`, which
    `storage.update` handles and tab-completion offers, so the help and
    the completion menu on one flag disagreed. The lists are now rendered
    from constants.STATUS_OPTIONS / TYPE_OPTIONS. (dogcat-85m4)
    """

    @staticmethod
    def _help(*args: str) -> str:
        """Render --help wide, so Typer does not truncate the value list.

        At the default width Typer clips the option column with an
        ellipsis, which silently hid `minimal` from the priority list.
        """
        result = runner.invoke(app, [*args, "--help"], env={"COLUMNS": "200"})
        return " ".join(result.output.split())

    def test_status_help_lists_every_user_facing_status(self) -> None:
        """Both --status helps carry the full STATUS_OPTIONS set."""
        from dogcat.constants import STATUS_OPTIONS

        for command in ("create", "update"):
            flat = self._help(command)
            for _label, value in STATUS_OPTIONS:
                assert value in flat, f"dcat {command} --help omits status {value!r}"

    def test_type_help_lists_every_type_on_all_three_commands(self) -> None:
        """create, update and inbox accept must agree on the type list."""
        from dogcat.constants import TYPE_OPTIONS

        for args in (["create"], ["update"], ["inbox", "accept"]):
            flat = self._help(*args)
            for _label, value in TYPE_OPTIONS:
                assert value in flat, f"dcat {' '.join(args)} --help omits {value!r}"

    def test_priority_help_lists_the_named_forms(self) -> None:
        """`dcat update -p high` works, so --help must say so."""
        from dogcat.constants import PRIORITY_NAMES

        for command in ("create", "update"):
            flat = self._help(command)
            for name in PRIORITY_NAMES:
                assert name in flat, f"dcat {command} --help omits priority {name!r}"

    def test_named_priority_is_actually_accepted(self, tmp_path: Path) -> None:
        """Guard the claim the help now makes, not just the help text."""
        dogcats_dir = tmp_path / ".dogcats"
        runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
        created = runner.invoke(
            app, ["create", "Named priority", "--dogcats-dir", str(dogcats_dir)]
        )
        issue_id = created.stdout.split(": ")[0].split()[-1]

        result = runner.invoke(
            app,
            ["update", issue_id, "-p", "high", "--dogcats-dir", str(dogcats_dir)],
        )
        assert result.exit_code == 0


class TestSharedOptionAliasesSurviveDecorators:
    """`--json` must stay `--json` on every command that declares it.

    `with_ns_shim` copied raw annotation strings, so Typer resolved the
    shared `_list_options` aliases against `_helpers`' globals — which do
    not import them — and silently regenerated a default option. Every
    ns-shimmed command exposed `--json-output` instead of `--json`, with
    no error anywhere. (dogcat-1fr8)
    """

    @staticmethod
    def _flags(*args: str) -> str:
        result = runner.invoke(app, [*args, "--help"], env={"COLUMNS": "200"})
        return " ".join(result.output.split())

    def test_ns_shimmed_commands_keep_the_json_flag(self) -> None:
        """defer, close and the status shortcuts all use --json."""
        for command in ("defer", "close", "reopen", "in-progress", "in-review"):
            flat = self._flags(command)
            assert "--json " in flat or "--json│" in flat or "--json" in flat
            assert "--json-output" not in flat, (
                f"dcat {command} regenerated a default option instead of using JsonOpt"
            )

    def test_dogcats_dir_help_names_the_walk_up(self) -> None:
        """The alias's help reaches the rendered page, not just the source."""
        flat = self._flags("defer")
        assert ".dogcatrc" in flat
        assert "default_storage" in flat
