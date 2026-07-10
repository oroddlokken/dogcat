"""End-to-end tests for global config fallback in storage resolution.

XDG_CONFIG_HOME isolation comes from the autouse ``_isolate_global_config``
fixture in conftest.py; ``save_global_config_value`` writes there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import find_dogcats_dir
from dogcat.config import get_issue_prefix, get_namespace_filter
from dogcat.global_config import save_global_config_value

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


class TestGlobalConfigStorageFallback:
    """Storage resolution priority: local .dogcats > .dogcatrc > global."""

    def test_local_dogcats_wins_over_global(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A local .dogcats/ in cwd is preferred over global default_storage."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "repo"
        local_store = repo / ".dogcats"
        local_store.mkdir(parents=True)

        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == str(local_store)

    def test_rc_wins_over_global(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A walk-up .dogcatrc is preferred over global default_storage."""
        from dogcat.constants import DOGCATRC_FILENAME

        global_store = tmp_path / "global" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        rc_target = tmp_path / "rc" / ".dogcats"
        rc_target.mkdir(parents=True)
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / DOGCATRC_FILENAME).write_text(str(rc_target) + "\n")

        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == str(rc_target)

    def test_global_used_when_nothing_local(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No local .dogcats and no .dogcatrc → fall back to global default_storage."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        assert find_dogcats_dir() == str(global_store)

    def test_global_fallback_prints_stderr_notice(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Falling back to the global store is announced on stderr, once."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        find_dogcats_dir()
        find_dogcats_dir()
        err = capsys.readouterr().err
        assert err.count("using global default_storage") == 1
        assert str(global_store) in err
        assert "'repo'" in err  # derived namespace is part of the notice

    def test_global_ignored_when_path_does_not_exist(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """default_storage points to missing dir → fall through to .dogcats default."""
        save_global_config_value("default_storage", str(tmp_path / "does-not-exist"))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == ".dogcats"

    def test_global_ignored_when_path_is_a_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """default_storage points to a regular file, fall through to .dogcats."""
        not_a_dir = tmp_path / "shared-as-file"
        not_a_dir.write_text("not a directory")
        save_global_config_value("default_storage", str(not_a_dir))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == ".dogcats"

    def test_no_global_config_is_unchanged(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no global config file exists, behavior matches current dcat."""
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)
        assert find_dogcats_dir() == ".dogcats"


class TestGlobalConfigNamespace:
    """Namespace derivation when storage resolves via the global fallback."""

    def test_namespace_uses_cwd_dir_slug(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Resolved via global fallback → namespace is the cwd folder slug."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "læring"
        repo.mkdir()
        monkeypatch.chdir(repo)

        resolved = find_dogcats_dir()
        assert resolved == str(global_store)
        assert get_issue_prefix(resolved) == "laering"

    def test_cwd_slug_beats_shared_store_config_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Shared store's own namespace must not leak into cwd-derived mode."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        (global_store / "config.toml").write_text('namespace = "shared"\n')
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "læring"
        repo.mkdir()
        monkeypatch.chdir(repo)

        assert get_issue_prefix(find_dogcats_dir()) == "laering"

    def test_unsluggable_cwd_falls_back_to_shared_store_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When cwd is not sluggable, fall through to the shared store's namespace."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        (global_store / "config.toml").write_text('namespace = "shared"\n')
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "测试"
        repo.mkdir()
        monkeypatch.chdir(repo)

        assert get_issue_prefix(find_dogcats_dir()) == "shared"

    def test_local_config_overrides_cwd_slug(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A repo with .dogcatrc + config.local.toml resolves via rc, not global."""
        from dogcat.constants import DOGCATRC_FILENAME

        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        (global_store / "config.toml").write_text('namespace = "shared"\n')
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "læring"
        repo.mkdir()
        (repo / DOGCATRC_FILENAME).write_text(str(global_store) + "\n")
        (repo / ".dogcats").mkdir()
        (repo / ".dogcats" / "config.local.toml").write_text('namespace = "custom"\n')

        monkeypatch.chdir(repo)
        assert get_issue_prefix(find_dogcats_dir()) == "custom"


class TestGlobalFallbackDoesNotLeak:
    """Repos NOT resolved via the fallback keep pre-global-config semantics.

    Regression tests for the path-equality detection the first version
    of this feature used: pointing at the same directory as the global
    store must not by itself switch a repo into cwd-slug mode.
    """

    def test_rc_repo_without_local_namespace_uses_store_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """.dogcatrc → same store as global: namespace comes from store config."""
        from dogcat.constants import DOGCATRC_FILENAME

        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        (global_store / "config.toml").write_text('namespace = "shared"\n')
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "some-repo"
        repo.mkdir()
        (repo / DOGCATRC_FILENAME).write_text(str(global_store) + "\n")

        monkeypatch.chdir(repo)
        resolved = find_dogcats_dir()
        assert resolved == str(global_store)
        assert get_issue_prefix(resolved) == "shared"

    def test_store_home_repo_keeps_own_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Running inside the store's home dir uses the store's own config."""
        home = tmp_path / "tracker"
        store = home / ".dogcats"
        store.mkdir(parents=True)
        (store / "config.toml").write_text('namespace = "issues"\n')
        save_global_config_value("default_storage", str(store))

        monkeypatch.chdir(home)
        resolved = find_dogcats_dir()
        assert resolved == str(store)
        assert get_issue_prefix(resolved) == "issues"
        # No rc, no fallback, no visible/hidden config → unfiltered view.
        assert get_namespace_filter(resolved) is None


class TestGlobalVisibleNamespaces:
    """Global visible_namespaces applies only in fallback mode."""

    def test_fallback_filters_to_derived_namespace(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fallback mode with no configured visibility filters to the slug."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        ns_filter = get_namespace_filter(find_dogcats_dir())
        assert ns_filter is not None
        assert ns_filter("repo")
        assert not ns_filter("other")

    def test_fallback_layers_global_visible_namespaces(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Global visible_namespaces extend the derived namespace in fallback mode."""
        global_store = tmp_path / "shared" / ".dogcats"
        global_store.mkdir(parents=True)
        save_global_config_value("default_storage", str(global_store))
        save_global_config_value("visible_namespaces", ["misc"])

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.chdir(repo)

        ns_filter = get_namespace_filter(find_dogcats_dir())
        assert ns_filter is not None
        assert ns_filter("repo")
        assert ns_filter("misc")
        assert not ns_filter("other")
