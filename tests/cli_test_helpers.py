"""Shared test helpers for CLI test modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from dogcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _init_with_namespace(dogcats_dir: Path, namespace: str = "proj-a") -> None:
    """Initialize a dogcats repo and set a specific namespace."""
    from dogcat.config import save_config

    runner.invoke(app, ["init", "--dogcats-dir", str(dogcats_dir)])
    save_config(str(dogcats_dir), {"namespace": namespace})


def _create_issue(dogcats_dir: Path, title: str, **kwargs: str) -> None:
    """Create an issue with optional extra flags."""
    cmd: list[str] = ["create", title, "--dogcats-dir", str(dogcats_dir)]
    for key, val in kwargs.items():
        cmd.extend([f"--{key}", val])
    result = runner.invoke(app, cmd)
    assert result.exit_code == 0, result.stdout


def _create_multi_ns_issues(dogcats_dir: Path) -> None:
    """Create issues across two namespaces: proj-a (primary) and proj-b."""
    from dogcat.config import load_config, save_config

    _init_with_namespace(dogcats_dir, "proj-a")
    _create_issue(dogcats_dir, "Issue A1")
    _create_issue(dogcats_dir, "Issue A2")
    # Switch namespace and create issues
    config = load_config(str(dogcats_dir))
    config["namespace"] = "proj-b"
    save_config(str(dogcats_dir), config)
    _create_issue(dogcats_dir, "Issue B1")
    # Restore primary namespace
    config = load_config(str(dogcats_dir))
    config["namespace"] = "proj-a"
    save_config(str(dogcats_dir), config)


def _set_ns_config(
    dogcats_dir: Path,
    key: str,
    value: list[str],
) -> None:
    """Set a namespace config key (visible_namespaces or hidden_namespaces)."""
    from dogcat.config import load_config, save_config

    config = load_config(str(dogcats_dir))
    config[key] = value
    save_config(str(dogcats_dir), config)
