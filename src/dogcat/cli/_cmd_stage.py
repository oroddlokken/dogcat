"""Stage command for dogcat CLI - stage one issue's records in the git index."""

from __future__ import annotations

import tempfile
from pathlib import Path

import orjson
import typer

import dogcat.git as git_helpers

from ._completions import complete_issue_ids
from ._helpers import get_storage, with_ns_shim
from ._json_state import echo_error, is_json, set_json
from ._list_options import DogcatsDirOpt, JsonOpt


def register(app: typer.Typer) -> None:
    """Register stage command."""

    @app.command("stage")
    @with_ns_shim
    def stage(
        issue_ids: list[str] = typer.Argument(  # noqa: B008
            ...,
            help="Issue ID(s) whose uncommitted records to stage",
            autocompletion=complete_issue_ids,
        ),
        json_output: JsonOpt = False,
        dogcats_dir: DogcatsDirOpt = ".dogcats",
    ) -> None:
        """Stage issues' uncommitted records, leaving other issues' unstaged.

        Writes issues.jsonl into the git index as it stands there plus the
        named issues' new records: the issue record, its events, and its
        dependencies and links. Other issues' uncommitted writes stay in the
        working tree only. An edge to an issue that is neither committed nor
        staged is held back and named in the output.

        Follow with a plain `git commit`. `git add .dogcats` re-stages the
        whole file, and `git commit -- <path>` bypasses the index.
        """
        from dogcat.stage import plan_stage

        set_json(json_output)
        storage = get_storage(dogcats_dir)

        resolved: list[str] = []
        for issue_id in issue_ids:
            try:
                full_id = storage.resolve_id(issue_id)
            except ValueError as e:
                echo_error(str(e))
                raise typer.Exit(1) from e
            if full_id is None:
                echo_error(f"Issue {issue_id} not found")
                raise typer.Exit(1)
            if full_id not in resolved:
                resolved.append(full_id)

        store_path = storage.path.resolve()
        git_root = git_helpers.repo_root(cwd=storage.dogcats_dir)
        if git_root is None:
            echo_error(f"{store_path} is not inside a git repository")
            raise typer.Exit(1)
        try:
            repo_path = store_path.relative_to(git_root.resolve()).as_posix()
        except ValueError as e:
            echo_error(f"{store_path} is outside the git worktree at {git_root}")
            raise typer.Exit(1) from e

        base = git_helpers.show_file(f":{repo_path}", cwd=git_root) or b""
        plan = plan_stage(base, store_path.read_bytes(), resolved)

        if plan.changed:
            with tempfile.TemporaryDirectory() as tmp:
                blob_file = Path(tmp) / "issues.jsonl"
                blob_file.write_bytes(plan.blob)
                blob = git_helpers.hash_object(blob_file, cwd=git_root)
            if blob is None or not git_helpers.stage_blob(
                blob, repo_path, cwd=git_root
            ):
                echo_error(f"git could not stage {repo_path}")
                raise typer.Exit(1)

        if is_json():
            typer.echo(
                orjson.dumps(
                    {
                        "staged": {k: v for k, v in plan.staged.items() if v},
                        "unchanged": [k for k in resolved if not plan.staged[k]],
                        "held_back": [
                            {
                                "kind": h.kind,
                                "from_id": h.from_id,
                                "to_id": h.to_id,
                                "type": h.edge_type,
                                "missing_id": h.missing_id,
                            }
                            for h in plan.held_back
                        ],
                        "unstaged_parents": plan.unstaged_parents,
                        "rewritten": plan.rewritten,
                    }
                ).decode()
            )
            return

        held_ids = {end for h in plan.held_back for end in (h.from_id, h.to_id)}
        for full_id in resolved:
            count = plan.staged[full_id]
            if count:
                noun = "record" if count == 1 else "records"
                typer.echo(f"✓ Staged {full_id} ({count} {noun})")
            elif full_id in held_ids:
                typer.echo(f"{full_id}: nothing more to stage")
            else:
                typer.echo(f"{full_id}: no uncommitted records")
        for held in plan.held_back:
            arrow = f"{held.from_id} → {held.to_id} ({held.edge_type})"
            typer.echo(
                f"⚠ Held back {held.kind} {arrow}: "
                f"{held.missing_id} is not committed or staged"
            )
        for child, parent in plan.unstaged_parents.items():
            typer.echo(
                f"⚠ {child}'s parent {parent} is not committed or staged; stage it too"
            )
        if plan.rewritten and plan.changed:
            typer.echo(
                f"{repo_path} was rewritten since it was staged; "
                f"staged the changes as appended records"
            )
