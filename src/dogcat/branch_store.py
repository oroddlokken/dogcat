"""Write issue mutations to another branch's store without checking it out.

``dcat <command> --branch main`` on ``feature-x`` runs the command against a
scratch copy of ``main:.dogcats/issues.jsonl`` and commits the result onto
``main`` through git plumbing (:func:`dogcat.git.commit_file_to_branch`). The
current branch, index and working tree are never touched, and only the local
``refs/heads/<branch>`` moves — pushing stays with the user (dogcat-1fvb).

While a :func:`branch_store` context is open, ``get_storage`` in
``cli/_helpers.py`` returns the scratch storage instead of resolving one, so
command bodies need no branch awareness.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson

import dogcat.git as git_helpers
from dogcat.config import CONFIG_FILENAME, LOCAL_CONFIG_FILENAME
from dogcat.constants import ISSUES_FILENAME
from dogcat.storage import JSONLStorage

if TYPE_CHECKING:
    from collections.abc import Generator

_active: BranchStorage | None = None


class BranchWriteError(Exception):
    """The ``--branch`` target can't be written; the message says why."""


class BranchStorage(JSONLStorage):
    """Scratch storage holding another branch's issues.

    Differs from :class:`JSONLStorage` in two ways. It never compacts: the
    default-branch check would see the *current* checkout, and a compaction
    here would commit a whole-file rewrite onto the target. And new ids are
    minted against ``reserved_ids`` too — the current branch's ids — so the
    issue can't collide when the branches later merge.
    """

    def __init__(self, path: str, reserved_ids: set[str]) -> None:
        """Load the scratch file at ``path``; see the class docstring."""
        self.reserved_ids = reserved_ids
        super().__init__(path)

    def _is_default_branch(self) -> bool:
        return False

    def get_issue_ids(self) -> set[str]:
        """Return this store's ids plus the reserved ids from the current branch."""
        return super().get_issue_ids() | self.reserved_ids


@dataclass
class BranchWrite:
    """What :func:`branch_store` yields: the scratch storage, then the commit."""

    branch: str
    storage: BranchStorage
    # Set on exit when the block changed the store; None means nothing to commit.
    commit: str | None = None


def active_branch_storage() -> BranchStorage | None:
    """Return the scratch storage of the open :func:`branch_store`, if any."""
    return _active


def _touched_ids(old: bytes, new: bytes) -> list[str]:
    """Return issue ids named by the lines appended to ``old``, in order."""
    added = new.removeprefix(old)
    ids: list[str] = []
    for line in added.splitlines():
        try:
            record: dict[str, Any] = orjson.loads(line)
        except orjson.JSONDecodeError:
            continue
        if record.get("record_type") == "issue":
            ns, short = record.get("namespace"), record.get("id")
            candidate = f"{ns}-{short}" if ns else short
        else:
            candidate = record.get("issue_id") or record.get("from_id")
        if isinstance(candidate, str) and candidate not in ids:
            ids.append(candidate)
    return ids


@contextlib.contextmanager
def branch_store(
    dogcats_dir: str,
    branch: str,
    *,
    command: str,
) -> Generator[BranchWrite]:
    """Open a scratch store for ``branch`` and commit what the block writes.

    ``dogcats_dir`` is the resolved store directory of the current checkout.
    The commit happens on exit whenever the file changed, also when the
    block raises — a normal run keeps the writes that landed before an
    error, and this mirrors that.

    Yields:
        A :class:`BranchWrite`. ``get_storage`` returns its storage until
        exit, and its ``commit`` holds the new SHA after exit.

    Raises:
        BranchWriteError: When the target can't be written — not a branch,
            the current branch, checked out elsewhere, no store on it, the
            store outside the repository the user is in, or the branch
            moved meanwhile.
    """
    global _active  # noqa: PLW0603 — one command per process; see module doc
    if _active is not None:
        msg = "A --branch write is already in progress"
        raise BranchWriteError(msg)

    store_dir = Path(dogcats_dir).resolve()
    root = git_helpers.repo_root(store_dir)
    if root is None:
        msg = f"--branch needs a git repository; {store_dir} is not in one"
        raise BranchWriteError(msg)
    root = root.resolve()
    here = git_helpers.repo_root()
    if here is None or here.resolve() != root:
        msg = (
            f"The store at {store_dir} belongs to the repository at {root},"
            " not the one you are in; --branch only writes to this repository"
        )
        raise BranchWriteError(msg)
    try:
        rel_dir = store_dir.relative_to(root).as_posix()
    except ValueError:
        msg = (
            f"The store at {store_dir} lives outside the repository at {root},"
            " so no branch holds it"
        )
        raise BranchWriteError(msg) from None

    parent = git_helpers.resolve_branch(branch, cwd=root)
    if parent is None:
        msg = f"No local branch named '{branch}'"
        raise BranchWriteError(msg)
    if git_helpers.current_branch(cwd=root) == branch:
        msg = f"'{branch}' is the current branch; run the command without --branch"
        raise BranchWriteError(msg)
    if branch in git_helpers.checked_out_branches(cwd=root):
        msg = f"'{branch}' is checked out in another worktree; run the command there"
        raise BranchWriteError(msg)

    repo_path = f"{rel_dir}/{ISSUES_FILENAME}"
    old = git_helpers.show_file(f"{parent}:{repo_path}", cwd=root)
    if old is None:
        msg = f"Branch '{branch}' has no {repo_path}"
        raise BranchWriteError(msg)

    reserved: set[str] = set()
    current_file = store_dir / ISSUES_FILENAME
    if current_file.exists():
        reserved = JSONLStorage(str(current_file)).get_issue_ids()

    with tempfile.TemporaryDirectory(prefix="dcat-branch-") as tmp:
        scratch_dir = Path(tmp) / store_dir.name
        scratch_dir.mkdir()
        scratch_file = scratch_dir / ISSUES_FILENAME
        scratch_file.write_bytes(old)
        # Config reads under --branch resolve here (cli/_branch.py), so they
        # see the target branch's shared config and this checkout's local
        # overrides, the same pair a checkout of the branch would.
        config = git_helpers.show_file(
            f"{parent}:{rel_dir}/{CONFIG_FILENAME}", cwd=root
        )
        if config is not None:
            (scratch_dir / CONFIG_FILENAME).write_bytes(config)
        local_config = store_dir / LOCAL_CONFIG_FILENAME
        if local_config.is_file():
            shutil.copyfile(local_config, scratch_dir / LOCAL_CONFIG_FILENAME)

        write = BranchWrite(branch, BranchStorage(str(scratch_file), reserved))
        _active = write.storage
        try:
            yield write
        finally:
            _active = None
            new = scratch_file.read_bytes()
            if new != old:
                write.commit = _commit(
                    root=root,
                    branch=branch,
                    parent=parent,
                    repo_path=repo_path,
                    scratch_file=scratch_file,
                    message=_message(
                        command, branch, _touched_ids(old, new), root=root
                    ),
                    scratch_index=Path(tmp) / "index",
                )


def _message(command: str, branch: str, ids: list[str], *, root: Path) -> str:
    subject = f"dcat {command} {' '.join(ids)}".rstrip()
    # rev-parse --abbrev-ref prints the literal "HEAD" when detached.
    current = git_helpers.current_branch(cwd=root)
    source = current if current not in (None, "HEAD") else "a detached HEAD"
    return (
        f"{subject}\n\nWritten from {source} with `dcat {command} --branch {branch}`."
    )


def _commit(
    *,
    root: Path,
    branch: str,
    parent: str,
    repo_path: str,
    scratch_file: Path,
    message: str,
    scratch_index: Path,
) -> str:
    blob = git_helpers.hash_object(scratch_file, cwd=root)
    commit = None
    if blob is not None:
        commit = git_helpers.commit_file_to_branch(
            branch,
            parent=parent,
            repo_path=repo_path,
            blob=blob,
            message=message,
            scratch_index=scratch_index,
            cwd=root,
        )
    if commit is None:
        moved = git_helpers.resolve_branch(branch, cwd=root) != parent
        reason = f"'{branch}' moved while the command ran" if moved else "git failed"
        msg = f"Nothing committed to '{branch}': {reason}. Re-run the command."
        raise BranchWriteError(msg)
    return commit
