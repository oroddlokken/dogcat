"""JSONL-based storage for issues with atomic writes."""

from __future__ import annotations

import dataclasses
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, cast

import orjson

from dogcat._compaction import should_compact
from dogcat._diff import field_value, tracked_changes
from dogcat._id_resolve import resolve_partial_id
from dogcat._indexes import rebuild_indexes
from dogcat._jsonl_io import append_jsonl_payload, atomic_rewrite_jsonl
from dogcat._schema import current_version_tuple, parse_version
from dogcat._version import version as _dcat_version
from dogcat.constants import (
    DEFAULT_BRANCH_NAMES,
    DOGCATS_DIR_NAME,
    ISSUES_FILENAME,
    LOCK_FILENAME,
    TRACKED_FIELDS,
)
from dogcat.locking import advisory_file_lock
from dogcat.models import (
    Dependency,
    DependencyType,
    FilterSpec,
    Issue,
    IssueType,
    Link,
    LinkType,
    Status,
    classify_record,
    dict_to_issue,
    issue_to_dict,
    link_type_value,
)

if TYPE_CHECKING:
    from contextlib import AbstractContextManager


class JSONLStorage:
    """Manages atomic JSONL storage for issues."""

    def __init__(
        self,
        path: str = f"{DOGCATS_DIR_NAME}/{ISSUES_FILENAME}",
        create_dir: bool = False,
    ) -> None:
        """Initialize storage.

        Args:
            path: Path to the JSONL storage file (default: .dogcats/issues.jsonl)
            create_dir: If True, create the directory if it doesn't exist.
                       If False (default), raise an error if directory doesn't exist.
        """
        self.path = Path(path)
        self.dogcats_dir = self.path.parent
        self._issues: dict[str, Issue] = {}
        self._dependencies: list[Dependency] = []
        self._links: list[Link] = []
        # Indexes for O(1) dependency/link lookups
        self._deps_by_issue: dict[str, list[Dependency]] = {}
        self._deps_by_depends_on: dict[str, list[Dependency]] = {}
        self._links_by_from: dict[str, list[Link]] = {}
        self._links_by_to: dict[str, list[Link]] = {}
        self._children_by_parent: dict[str, list[str]] = {}
        # Track lines for compaction decisions
        self._base_lines: int = 0
        self._appended_lines: int = 0

        if create_dir:
            # Create .dogcats directory if it doesn't exist (used by init)
            self.dogcats_dir.mkdir(parents=True, exist_ok=True)
        elif not self.dogcats_dir.exists():
            # Fail if directory doesn't exist and create_dir is False
            msg = (
                f"Directory '{self.dogcats_dir}' does not exist. "
                f"Run 'dcat init' first to initialize the repository."
            )
            raise ValueError(
                msg,
            )

        self._lock_path = self.dogcats_dir / LOCK_FILENAME
        self._needs_compaction = False  # Set when corrupt last line is skipped
        # Bad lines skipped during _load() — preserved (with line number and
        # reason) so doctor can surface a count and ``dcat admin repair-jsonl``
        # can copy them to a sidecar file before compaction drops them.
        self._bad_lines: list[tuple[int, bytes, str]] = []

        # Initialize event log for change tracking
        from dogcat.event_log import EventLog

        self._event_log = EventLog(self.dogcats_dir)

        # Load existing issues if file exists
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        """Load issues from JSONL file into memory.

        Replays the append-only log: later issue records override earlier ones
        (last-write-wins by ID).  Dependency and link records may carry an
        ``"op"`` field (``"add"`` or ``"remove"``); the default is ``"add"``
        for backwards compatibility with files written before append-only mode.

        Malformed lines (any position) are logged as warnings and skipped so
        the CLI keeps working after a crash, disk-full, or partial write.
        Skipped lines are recorded on ``self._bad_lines`` so doctor can
        surface the count and ``dcat admin repair-jsonl`` can preserve them
        in a ``.bad`` sidecar before compaction drops them.
        """
        self._issues.clear()
        self._dependencies.clear()
        self._links.clear()
        self._bad_lines = []

        # Use sets keyed by identity tuple for efficient add/remove replay
        dep_map: dict[tuple[str, str, str], Dependency] = {}
        link_map: dict[tuple[str, str, str], Link] = {}
        line_count = 0
        # Track the highest dcat_version observed across all records so we
        # can warn if the file was written by a newer tool than this one.
        # See dogcat._schema for the version-comparison contract.
        newest_record_version: tuple[tuple[int, int, int], str] | None = None

        try:
            with self.path.open("rb") as f:
                lines = f.readlines()
        except OSError as e:
            msg = f"Failed to read storage file: {e}"
            raise RuntimeError(msg) from e

        # Strip trailing empty lines so we can identify the true last line
        while lines and not lines[-1].strip():
            lines.pop()

        # Dispatch table for record-type-specific parsers. ``event`` records
        # are intentionally absent — they're loaded lazily by EventLog.read
        # and skipped during issue replay.
        parsers = {
            "link": self._parse_link_record,
            "dependency": self._parse_dependency_record,
        }

        for line_idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue

            line_count += 1

            try:
                raw_data = orjson.loads(line)
                if not isinstance(raw_data, dict):
                    msg = f"expected JSON object, got {type(raw_data).__name__}"
                    raise TypeError(msg)  # noqa: TRY301
                data = cast("dict[str, Any]", raw_data)
                raw_v = data.get("dcat_version")
                if isinstance(raw_v, str):
                    parsed_v = parse_version(raw_v)
                    if parsed_v is not None and (
                        newest_record_version is None
                        or parsed_v > newest_record_version[0]
                    ):
                        newest_record_version = (parsed_v, raw_v)
                rtype = classify_record(data)
                if rtype == "event":
                    continue
                parser = parsers.get(rtype)
                if parser is not None:
                    parser(data, link_map=link_map, dep_map=dep_map)
                else:
                    # Default: treat as an issue record (last-write-wins).
                    self._parse_issue_record(data)
            except (
                orjson.JSONDecodeError,
                ValueError,
                KeyError,
                AttributeError,
                TypeError,
            ) as e:
                logging.getLogger(__name__).warning(
                    "Skipping malformed JSONL line %d in %s: %s",
                    line_idx + 1,
                    self.path,
                    e,
                )
                self._bad_lines.append((line_idx + 1, raw_line, str(e)))
                self._needs_compaction = True

        self._dependencies = list(dep_map.values())
        self._links = list(link_map.values())
        self._base_lines = line_count
        self._appended_lines = 0
        self._rebuild_indexes()

        # Warn (once per load) if any record was written by a newer tool
        # than the one currently running — readers ignore unknown fields
        # but new semantics may not be honored. See dogcat._schema.
        current = current_version_tuple()
        if current is not None and newest_record_version is not None:
            newest_tuple, newest_raw = newest_record_version
            if newest_tuple > current:
                logging.getLogger(__name__).warning(
                    "%s contains records written by dcat %s; "
                    "running tool is %s. Older versions read newer records "
                    "best-effort — upgrade dcat to silence this warning.",
                    self.path,
                    newest_raw,
                    _dcat_version,
                )

    @staticmethod
    def _parse_link_record(
        data: dict[str, Any],
        *,
        link_map: dict[tuple[str, str, str], Link],
        dep_map: dict[tuple[str, str, str], Dependency],  # noqa: ARG004
    ) -> None:
        """Apply one link record (``add`` or ``remove`` op) to the in-memory map."""
        op = data.get("op", "add")
        key = (
            data["from_id"],
            data["to_id"],
            data.get("link_type", "relates_to"),
        )
        if op == "remove":
            link_map.pop(key, None)
            return
        link_map[key] = Link(
            from_id=data["from_id"],
            to_id=data["to_id"],
            link_type=data.get("link_type", "relates_to"),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by"),
        )

    @staticmethod
    def _parse_dependency_record(
        data: dict[str, Any],
        *,
        link_map: dict[tuple[str, str, str], Link],  # noqa: ARG004
        dep_map: dict[tuple[str, str, str], Dependency],
    ) -> None:
        """Apply one dependency record (``add`` or ``remove`` op) to the map."""
        op = data.get("op", "add")
        key = (data["issue_id"], data["depends_on_id"], data["type"])
        if op == "remove":
            dep_map.pop(key, None)
            return
        from dogcat.models import _safe_enum

        dep_map[key] = Dependency(
            issue_id=data["issue_id"],
            depends_on_id=data["depends_on_id"],
            dep_type=_safe_enum(DependencyType, data["type"], "dependency.type"),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by"),
        )

    def _parse_issue_record(self, data: dict[str, Any]) -> None:
        """Apply one issue record under last-write-wins semantics."""
        issue = dict_to_issue(data)
        self._issues[issue.full_id] = issue

    def _rebuild_indexes(self) -> None:
        """Rebuild dependency, link, and parent indexes from the source lists.

        The actual computation lives in :func:`dogcat._indexes.rebuild_indexes`;
        this method is just a thin adapter that copies the resulting maps onto
        ``self`` so existing attribute-style access keeps working.
        """
        indexes = rebuild_indexes(
            self._issues.values(), self._dependencies, self._links
        )
        self._deps_by_issue = indexes.deps_by_issue
        self._deps_by_depends_on = indexes.deps_by_depends_on
        self._links_by_from = indexes.links_by_from
        self._links_by_to = indexes.links_by_to
        self._children_by_parent = indexes.children_by_parent

    def _file_lock(self) -> AbstractContextManager[None]:
        """Acquire an advisory file lock for exclusive writes."""
        return advisory_file_lock(self._lock_path)

    def _save(
        self,
        *,
        _reload: bool = True,
        _prune_event_ids: set[str] | None = None,
        _rename_event_ids: dict[str, str] | None = None,
    ) -> None:
        """Compact: rewrite the entire file with only current state.

        Eliminates superseded issue records, removed dependencies/links,
        and resets the append counter.

        Args:
            _reload: If True (default), reload from disk under the lock
                before writing so that records appended by other processes
                since our last ``_load()`` are not discarded.  Pass False
                when the caller has already modified in-memory state (e.g.
                removing dependencies) and that modification is the
                authoritative source of truth.
            _prune_event_ids: If set, drop event records whose ``issue_id``
                is in this set (used by ``prune_tombstones``).
            _rename_event_ids: If set, rewrite ``issue_id`` in event records
                according to this old→new mapping (used by ``change_namespace``).
        """
        with self._file_lock():
            self._save_locked(
                _reload=_reload,
                _prune_event_ids=_prune_event_ids,
                _rename_event_ids=_rename_event_ids,
            )

    def _save_locked(
        self,
        *,
        _reload: bool = True,
        _prune_event_ids: set[str] | None = None,
        _rename_event_ids: dict[str, str] | None = None,
    ) -> None:
        """Body of :meth:`_save` that assumes the file lock is already held.

        Use this from inside an existing ``self._file_lock()`` context to
        avoid re-entering the advisory lock (which would deadlock since
        ``advisory_file_lock`` opens a fresh fd each time).
        """
        if _reload and self.path.exists():
            self._load()

        def _write(tmp_file: IO[bytes]) -> int:
            line_count = 0
            for issue in self._issues.values():
                tmp_file.write(orjson.dumps(issue_to_dict(issue)))
                tmp_file.write(b"\n")
                line_count += 1

            for dep in self._dependencies:
                dep_data = {
                    "record_type": "dependency",
                    "dcat_version": _dcat_version,
                    "issue_id": dep.issue_id,
                    "depends_on_id": dep.depends_on_id,
                    "type": dep.dep_type.value,
                    "created_at": dep.created_at.isoformat(),
                    "created_by": dep.created_by,
                }
                tmp_file.write(orjson.dumps(dep_data))
                tmp_file.write(b"\n")
                line_count += 1

            for link in self._links:
                link_data = {
                    "record_type": "link",
                    "dcat_version": _dcat_version,
                    "from_id": link.from_id,
                    "to_id": link.to_id,
                    "link_type": link.link_type,
                    "created_at": link.created_at.isoformat(),
                    "created_by": link.created_by,
                }
                tmp_file.write(orjson.dumps(link_data))
                tmp_file.write(b"\n")
                line_count += 1

            # Preserve event records from the current file
            if self.path.exists():
                with self.path.open("rb") as src:
                    for line_idx, raw_line in enumerate(src):
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        # Match _load's exception tolerance: a corrupt
                        # last line that _load skipped (setting
                        # _needs_compaction) must not crash the next
                        # rewrite (dogcat-5tix). Catch the same exception
                        # set + non-dict guard.
                        try:
                            raw_data = orjson.loads(raw_line)
                            if not isinstance(raw_data, dict):
                                msg = (
                                    f"expected JSON object, got "
                                    f"{type(raw_data).__name__}"
                                )
                                raise TypeError(msg)  # noqa: TRY301
                            data = cast("dict[str, Any]", raw_data)
                        except (
                            orjson.JSONDecodeError,
                            ValueError,
                            KeyError,
                            AttributeError,
                            TypeError,
                        ) as e:
                            logging.getLogger(__name__).warning(
                                "Skipping malformed line %d in %s during "
                                "compaction: %s",
                                line_idx + 1,
                                self.path,
                                e,
                            )
                            continue
                        if data.get("record_type") == "event":
                            eid = data.get("issue_id", "")
                            if _prune_event_ids and eid in _prune_event_ids:
                                continue
                            if _rename_event_ids and eid in _rename_event_ids:
                                data["issue_id"] = _rename_event_ids[eid]
                                raw_line = orjson.dumps(data)
                            tmp_file.write(raw_line)
                            tmp_file.write(b"\n")
                            line_count += 1

            return line_count

        line_count = atomic_rewrite_jsonl(self.path, self.dogcats_dir, _write)
        self._base_lines = line_count
        self._appended_lines = 0

    def _append(self, records: list[dict[str, Any]]) -> None:
        """Append records to the JSONL file without rewriting it.

        Builds the payload in memory first and writes it in a single call
        so that a partial write (e.g. disk full) never leaves a truncated
        JSON line in the file.  If the file doesn't end with a newline
        (e.g. from a prior truncated write), a newline is prepended to
        avoid concatenating with the corrupt trailing content.

        Args:
            records: List of dicts to serialize and append as JSONL lines.
        """
        # If the file had a corrupt last line, rewrite it cleanly first
        # so the garbage doesn't persist between valid records.
        # Use _reload=False because callers (e.g. create()) may have already
        # added new records to in-memory state that aren't on disk yet.
        if self._needs_compaction:
            self._save(_reload=False)
            self._needs_compaction = False

        # Pre-serialize so the file write is a single operation
        payload = b"".join(orjson.dumps(r) + b"\n" for r in records)

        with self._file_lock():
            append_jsonl_payload(self.path, payload)
            self._appended_lines += len(records)
            # Eligibility check + compaction must run under the same lock
            # the append used. Otherwise two processes can both see counts
            # that look stale-and-eligible and rewrite the file twice.
            if (
                should_compact(self._base_lines, self._appended_lines)
                and self._is_default_branch()
            ):
                self._save_locked()

    _DEFAULT_BRANCHES = DEFAULT_BRANCH_NAMES

    def _is_default_branch(self) -> bool:
        """Check whether the working tree is on a default branch (main/master).

        ``True`` when there is genuinely no git repository (FileNotFoundError
        on the binary or git reports "not a git repo"). Any other non-zero
        return — permission denied, lock contention, internal git error —
        returns ``False`` and logs the stderr so we don't silently lose the
        feature-branch protection on a transient problem.

        The known-default-branch set is :data:`DEFAULT_BRANCH_NAMES` plus
        the user's ``init.defaultBranch`` git config when set, so projects
        on ``develop``/``trunk``/etc. don't silently lose auto-compaction.
        """
        try:
            # Force the C locale so stderr text matches the literal
            # English match below. Under non-English LC_ALL git emits
            # localized strings ("ce n'est pas un dépôt git", "Kein
            # Git-Repository", etc.) and the substring check would fail,
            # disabling auto-compaction silently. (dogcat-4tl1)
            #
            # Time-bound the call so a stalled HOME / credential helper
            # / LFS smudge cannot wedge dcat indefinitely. (dogcat-1uq7)
            from dogcat.git import _c_locale_env, _git_timeout

            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(self.dogcats_dir),
                env=_c_locale_env(),
                timeout=_git_timeout(),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return True  # git not installed / hung — safe to compact
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch in self._known_default_branches()
        stderr = (result.stderr or "").strip().lower()
        # "not a git repository" is the only non-zero outcome we treat as
        # "no repo here, safe to compact". Permission denied / locked
        # index / internal errors should NOT bypass the protection.
        if "not a git repository" in stderr:
            return True
        logging.getLogger(__name__).warning(
            "git rev-parse failed (rc=%s) under %s: %s. "
            "Skipping compaction to be safe.",
            result.returncode,
            self.dogcats_dir,
            result.stderr.strip() if result.stderr else "<no stderr>",
        )
        return False
        # NOTE: kept inline here (not via dogcat.git.current_branch) because
        # the storage path needs the stderr to distinguish "no repo" (safe)
        # from "permission denied" (not safe). The git module's helper
        # collapses both to None.

    def _known_default_branches(self) -> frozenset[str]:
        """Return the union of conventional default branches + ``init.defaultBranch``.

        ``init.defaultBranch`` lets users opt their non-conventional default
        branch (e.g. ``develop``) into auto-compaction without us having to
        ship a config flag. The git lookup is best-effort: if the helper
        can't reach git or the value isn't set, we fall back to the
        compiled defaults.
        """
        from dogcat import git as git_helpers

        configured = git_helpers.get_config("init.defaultBranch", cwd=self.dogcats_dir)
        if configured:
            # init.defaultBranch is per-repo and writable by any
            # collaborator. If it points to a non-conventional name,
            # log a one-line warning so the user notices before a
            # noisy compaction lands on a feature branch. (dogcat-2wys)
            if configured not in self._DEFAULT_BRANCHES:
                logging.getLogger(__name__).warning(
                    "init.defaultBranch=%r is not a conventional default "
                    "(main/master); auto-compaction is enabled on this "
                    "branch via the per-repo git config. Verify this is "
                    "intentional — set the value in .dogcats/config.toml "
                    "if you want it tracked in review.",
                    configured,
                )
            return self._DEFAULT_BRANCHES | {configured}
        return self._DEFAULT_BRANCHES

    # -- Event emission helpers ------------------------------------------

    def _emit_event(
        self,
        event_type: str,
        issue: Issue,
        changes: dict[str, dict[str, Any]],
        by: str | None = None,
    ) -> None:
        """Emit an event to the event log (best-effort)."""
        self._event_log.try_emit(
            event_type,
            issue.full_id,
            issue.updated_at.isoformat(),
            issue.title,
            changes,
            by=by,
        )

    def _build_event_record(
        self,
        event_type: str,
        issue: Issue,
        changes: dict[str, dict[str, Any]],
        by: str | None = None,
    ) -> dict[str, Any] | None:
        """Build the event JSONL dict for a mutation without writing it.

        Returns ``None`` when there are no changes to record, matching the
        no-op semantics of :meth:`_emit_event`. Used by mutation methods
        that want to coalesce the issue record + event record into a single
        locked append, halving file-lock + fsync churn per mutation.
        """
        return self._event_log.build_record(
            event_type,
            issue.full_id,
            issue.updated_at.isoformat(),
            issue.title,
            changes,
            by=by,
        )

    def _append_with_event(
        self,
        records: list[dict[str, Any]],
        event_record: dict[str, Any] | None,
    ) -> None:
        """Append data records and (optionally) an event record in one call.

        Equivalent to ``_append(records)`` followed by ``_event_log.emit(...)``
        but covered by a single file lock and a single fsync — eliminates
        the write amplification a 26-id ``dcat close`` batch otherwise pays.
        """
        if event_record is None:
            self._append(records)
            return
        # Best-effort event record: failures inside _append still raise, but
        # the event payload is always cheap to serialize, so swallowing it
        # here would be premature — let the caller's existing exception
        # handling decide.
        self._append([*records, event_record])

    @staticmethod
    def _field_value(value: Any) -> Any:
        """Normalize a field value for event storage (delegates to _diff)."""
        return field_value(value)

    def _tracked_changes(
        self,
        old_values: dict[str, Any],
        new_values: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Compute tracked field changes between old and new values."""
        # Restrict to fields present in old_values to preserve historical
        # behavior (only diff what the caller knew to compare).
        return tracked_changes(
            old_values, new_values, TRACKED_FIELDS & frozenset(old_values)
        )

    @staticmethod
    def _issue_record(issue: Issue) -> dict[str, Any]:
        """Serialize an issue to a dict for appending."""
        return issue_to_dict(issue)

    @staticmethod
    def _dep_record(dep: Dependency, *, op: str = "add") -> dict[str, Any]:
        """Serialize a dependency to a dict for appending."""
        d: dict[str, Any] = {
            "record_type": "dependency",
            "dcat_version": _dcat_version,
            "issue_id": dep.issue_id,
            "depends_on_id": dep.depends_on_id,
            "type": dep.dep_type.value,
            "created_at": dep.created_at.isoformat(),
            "created_by": dep.created_by,
        }
        if op != "add":
            d["op"] = op
        return d

    @staticmethod
    def _link_record(link: Link, *, op: str = "add") -> dict[str, Any]:
        """Serialize a link to a dict for appending."""
        d: dict[str, Any] = {
            "record_type": "link",
            "dcat_version": _dcat_version,
            "from_id": link.from_id,
            "to_id": link.to_id,
            "link_type": link.link_type,
            "created_at": link.created_at.isoformat(),
            "created_by": link.created_by,
        }
        if op != "add":
            d["op"] = op
        return d

    def create(self, issue: Issue) -> Issue:
        """Create a new issue.

        Args:
            issue: The issue to create

        Returns:
            The created issue

        Raises:
            ValueError: If ID already exists or issue is invalid
        """
        from dogcat.models import validate_issue

        if issue.full_id in self._issues:
            msg = f"Issue with ID {issue.full_id} already exists"
            raise ValueError(msg)

        validate_issue(issue)

        self._issues[issue.full_id] = issue
        if issue.parent:
            self._children_by_parent.setdefault(issue.parent, []).append(issue.full_id)

        # Build creation event alongside the issue record so we pay one lock
        # + one fsync instead of two.
        changes: dict[str, dict[str, Any]] = {}
        for field_name in TRACKED_FIELDS:
            value = getattr(issue, field_name, None)
            if value is not None and value != [] and value != "":
                changes[field_name] = {
                    "old": None,
                    "new": self._field_value(value),
                }
        event_record = self._build_event_record(
            "created", issue, changes, by=issue.created_by
        )
        self._append_with_event([self._issue_record(issue)], event_record)

        return issue

    def create_issue(
        self,
        *,
        title: str,
        namespace: str,
        description: str | None = None,
        status: Status = Status.OPEN,
        priority: int = 2,
        issue_type: IssueType = IssueType.TASK,
        owner: str | None = None,
        parent: str | None = None,
        labels: list[str] | None = None,
        external_ref: str | None = None,
        design: str | None = None,
        acceptance: str | None = None,
        notes: str | None = None,
        duplicate_of: str | None = None,
        created_by: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> Issue:
        """Generate an ID, build an :class:`Issue`, and persist it.

        Encapsulates the four-step pattern (namespace lookup → IDGenerator →
        ``generate_issue_id`` → build Issue → ``create``) that was previously
        re-implemented at every call site (CLI ``new``, ``inbox accept``,
        TUI detail panel, demo). Callers that need to wire dependencies or
        validate references stay in their own modules — this only owns the
        construction step.
        """
        from dogcat.idgen import IDGenerator

        ts = timestamp or datetime.now().astimezone()
        idgen = IDGenerator(existing_ids=self.get_issue_ids(), prefix=namespace)
        issue_id = idgen.generate_issue_id(
            title,
            timestamp=ts,
            namespace=namespace,
        )
        issue = Issue(
            id=issue_id,
            title=title,
            namespace=namespace,
            description=description,
            status=status,
            priority=priority,
            issue_type=issue_type,
            owner=owner,
            parent=parent,
            labels=list(labels) if labels else [],
            external_ref=external_ref,
            design=design,
            acceptance=acceptance,
            notes=notes,
            duplicate_of=duplicate_of,
            created_by=created_by,
            metadata=dict(metadata) if metadata else {},
        )
        return self.create(issue)

    def _cascade_id_rename(
        self, old_full_id: str, new_full_id: str
    ) -> list[dict[str, Any]]:
        """Rewrite every reference to ``old_full_id`` as ``new_full_id``.

        Walks the three reference collections (issues for parent /
        duplicate_of, dependency endpoints, link endpoints) and mutates
        each touched record in place. Returns the list of JSONL records
        the caller should append to persist the cascade. Caller is
        responsible for re-keying the issue map and rebuilding indexes.
        """
        records: list[dict[str, Any]] = []
        now = datetime.now().astimezone()

        for other in self._issues.values():
            changed = False
            if other.parent == old_full_id:
                other.parent = new_full_id
                changed = True
            if other.duplicate_of == old_full_id:
                other.duplicate_of = new_full_id
                changed = True
            if changed:
                other.updated_at = now
                records.append(self._issue_record(other))

        for dep in self._dependencies:
            changed = False
            if dep.issue_id == old_full_id:
                dep.issue_id = new_full_id
                changed = True
            if dep.depends_on_id == old_full_id:
                dep.depends_on_id = new_full_id
                changed = True
            if changed:
                records.append(self._dep_record(dep))

        for link in self._links:
            changed = False
            if link.from_id == old_full_id:
                link.from_id = new_full_id
                changed = True
            if link.to_id == old_full_id:
                link.to_id = new_full_id
                changed = True
            if changed:
                records.append(self._link_record(link))

        return records

    def _resolve_or_raise(self, issue_id: str, *, label: str = "Issue") -> str:
        """Resolve ``issue_id`` to a full id or raise ``ValueError``.

        Replaces the four-line ``resolved = resolve_id(...); if resolved is
        None: raise ValueError(...)`` pattern that was repeated across every
        mutation method (update / close / reopen / delete / dependency /
        link / comment). ``label`` lets callers surface a more specific
        noun (``"Parent issue"``, ``"Comment"``) in the error message.
        """
        resolved = self.resolve_id(issue_id)
        if resolved is None:
            msg = f"{label} {issue_id} not found"
            raise ValueError(msg)
        return resolved

    def resolve_id(self, partial_id: str) -> str | None:
        """Resolve a partial ID to a full issue ID.

        Supports multiple formats:
        - Full ID: "dc-3hup" -> "dc-3hup"
        - Hash only: "3hup" -> "dc-3hup"
        - Short hash: "hup" -> matches if unique

        Args:
            partial_id: Full or partial issue ID

        Returns:
            The full issue ID, or None if not found

        Raises:
            ValueError: If partial ID matches multiple issues (ambiguous)
        """
        return resolve_partial_id(partial_id, self._issues, kind="issues")

    def get(self, issue_id: str) -> Issue | None:
        """Get an issue by ID.

        Args:
            issue_id: The ID of the issue to retrieve (supports partial IDs)

        Returns:
            The issue, or None if not found
        """
        resolved_id = self.resolve_id(issue_id)
        if resolved_id:
            return self._issues.get(resolved_id)
        return None

    def list(
        self,
        filters: FilterSpec | dict[str, Any] | None = None,
    ) -> list[Issue]:
        """List all issues, optionally filtered.

        Args:
            filters: Either a :class:`FilterSpec` (typed, preferred) or a
                legacy dict with ``status``/``priority``/``type``/``label``/
                ``owner`` keys. ``None`` returns all issues.

        Returns:
            List of matching issues
        """
        issues = list(self._issues.values())

        if filters is None:
            return issues

        spec = (
            filters
            if isinstance(filters, FilterSpec)
            else FilterSpec.from_dict(filters)
        )

        if spec.status is not None:
            status_filter = (
                spec.status if isinstance(spec.status, Status) else Status(spec.status)
            )
            issues = [i for i in issues if i.status == status_filter]

        if spec.priority is not None:
            issues = [i for i in issues if i.priority == spec.priority]

        if spec.issue_type is not None:
            issues = [i for i in issues if i.issue_type.value == spec.issue_type]

        if spec.label is not None:
            if isinstance(spec.label, list):
                label_set: set[str] = set(spec.label)
                issues = [i for i in issues if label_set & set(i.labels)]
            else:
                issues = [i for i in issues if spec.label in i.labels]

        if spec.owner is not None:
            issues = [i for i in issues if i.owner == spec.owner]

        return issues

    # Fields that callers are allowed to modify via update().
    # Internal/identity fields (id, namespace, full_id, created_at, etc.) are excluded.
    UPDATABLE_FIELDS: frozenset[str] = frozenset(
        {
            "title",
            "description",
            "status",
            "priority",
            "issue_type",
            "owner",
            "parent",
            "labels",
            "external_ref",
            "design",
            "acceptance",
            "notes",
            "closed_reason",
            "updated_by",
            "closed_at",
            "closed_by",
            "deleted_at",
            "deleted_by",
            "deleted_reason",
            "original_type",
            "duplicate_of",
            "snoozed_until",
            "metadata",
            "comments",
        },
    )

    @staticmethod
    def _coerce_update_value(key: str, value: Any) -> Any:
        """Type-check + coerce a single ``update()`` field, raising on mismatch.

        Defense against silent corruption from setattr-with-anything:
        ``priority=True`` would pass ``isinstance(int)`` (bool is int);
        ``labels='bug'`` would iterate as ``{'b','u','g'}`` and break
        every label filter; ``status=42`` would store an int. (dogcat-3o3b)
        """
        from dogcat.models import (
            IssueType,
            Status,
            validate_priority,
        )

        if key == "priority":
            # bool is int subclass — exclude it explicitly so True/False
            # don't slip through validate_priority.
            if isinstance(value, bool) or not isinstance(value, int):
                msg = (
                    f"priority must be an int between 0 and 4, "
                    f"got {type(value).__name__}: {value!r}"
                )
                raise TypeError(msg)
            validate_priority(value)
            return value
        if key == "status":
            if isinstance(value, str):
                return Status(value)
            if isinstance(value, Status):
                return value
            msg = f"status must be a Status enum or string, got {type(value).__name__}"
            raise TypeError(msg)
        if key == "issue_type":
            if isinstance(value, str):
                return IssueType(value)
            if isinstance(value, IssueType):
                return value
            msg = (
                f"issue_type must be an IssueType enum or string, "
                f"got {type(value).__name__}"
            )
            raise TypeError(msg)
        if key == "original_type":
            if value is None:
                return None
            if isinstance(value, str):
                return IssueType(value)
            if isinstance(value, IssueType):
                return value
            msg = (
                f"original_type must be an IssueType, str, or None, "
                f"got {type(value).__name__}"
            )
            raise TypeError(msg)
        if key == "labels":
            if not isinstance(value, list):
                type_name = type(value).__name__
                msg = f"labels must be a list of strings, got {type_name}"
                raise TypeError(msg)
            items = cast("list[Any]", value)
            if not all(isinstance(item, str) for item in items):
                msg = "labels must be a list of strings, got non-string items"
                raise TypeError(msg)
            return cast("list[str]", value)
        if key == "metadata":
            if not isinstance(value, dict):
                msg = f"metadata must be a dict, got {type(value).__name__}"
                raise TypeError(msg)
            return cast("dict[str, Any]", value)
        if key == "comments":
            if not isinstance(value, list):
                msg = f"comments must be a list, got {type(value).__name__}"
                raise TypeError(msg)
            return cast("list[Any]", value)
        # String-or-None fields (description, owner, parent, notes,
        # closed_reason, deleted_reason, design, acceptance, external_ref,
        # updated_by, closed_by, deleted_by).
        string_or_none_fields = {
            "title",
            "description",
            "owner",
            "parent",
            "notes",
            "closed_reason",
            "deleted_reason",
            "design",
            "acceptance",
            "external_ref",
            "updated_by",
            "closed_by",
            "deleted_by",
        }
        if key in string_or_none_fields:
            if value is not None and not isinstance(value, str):
                msg = f"{key} must be a str or None, got {type(value).__name__}"
                raise TypeError(msg)
            return value
        # Datetime fields are allowed-through; the dataclass validates.
        return value

    def update(self, issue_id: str, updates: dict[str, Any]) -> Issue:
        """Update an issue.

        Args:
            issue_id: The ID of the issue to update (supports partial IDs)
            updates: Dictionary of fields to update

        Returns:
            The updated issue

        Raises:
            ValueError: If issue doesn't exist or updates contain disallowed fields
        """
        resolved_id = self._resolve_or_raise(issue_id)

        issue = self._issues[resolved_id]

        # Refuse to resurrect a tombstoned issue via update(). Without this
        # guard, ``dcat update <id> --status open`` after ``dcat delete``
        # flips a tombstone back to OPEN with deleted_* still populated.
        # ``dcat reopen`` only handles CLOSED→OPEN, not TOMBSTONE→*. The
        # right path for resurrecting a tombstone is a future explicit
        # "undelete" command. (dogcat-4g76)
        if issue.status == Status.TOMBSTONE and "status" in updates:
            new_status = updates["status"]
            if isinstance(new_status, str):
                new_status_value = new_status
            else:
                new_status_value = getattr(new_status, "value", new_status)
            if new_status_value != Status.TOMBSTONE.value:
                msg = (
                    f"Issue {issue.full_id} is tombstoned; "
                    f"refusing to update status to {new_status_value!r}. "
                    f"Tombstoned issues are immutable."
                )
                raise ValueError(msg)

        # Track old parent for index maintenance
        old_parent = issue.parent

        # Capture old values for event emission
        old_values: dict[str, Any] = {
            k: getattr(issue, k, None) for k in updates if k in TRACKED_FIELDS
        }
        old_metadata: dict[str, Any] | None = (
            dict(issue.metadata) if "metadata" in updates else None
        )

        # Update fields — only UPDATABLE_FIELDS are allowed.
        # Each field is type-checked before setattr so update() cannot
        # store a wrong-typed value and corrupt downstream code (e.g. a
        # string ``labels`` would iterate as characters in filters; a
        # bool ``priority`` would pass validate_priority because bool is
        # an int subclass). (dogcat-3o3b)
        for key, value in updates.items():
            if key not in self.UPDATABLE_FIELDS:
                continue
            value = self._coerce_update_value(key, value)
            setattr(issue, key, value)

        # Handle status transition side effects
        if "status" in updates:
            if issue.status == Status.CLOSED and issue.closed_at is None:
                # Transitioning to closed via update — set closed_at
                issue.closed_at = datetime.now().astimezone()
            elif issue.status != Status.CLOSED and issue.closed_at is not None:
                # Transitioning away from closed — clear closed fields
                issue.closed_at = None
                issue.closed_reason = None
                issue.closed_by = None

        # Maintain parent-child index if parent changed
        if issue.parent != old_parent:
            if old_parent and old_parent in self._children_by_parent:
                children = self._children_by_parent[old_parent]
                if resolved_id in children:
                    children.remove(resolved_id)
                if not children:
                    del self._children_by_parent[old_parent]
            if issue.parent:
                self._children_by_parent.setdefault(issue.parent, []).append(
                    resolved_id,
                )

        # Update timestamp
        issue.updated_at = datetime.now().astimezone()

        # Re-validate after applying updates so length / namespace / control-char
        # rules are enforced symmetrically with create() and the web form.
        from dogcat.models import validate_issue

        validate_issue(issue)

        new_values = {k: getattr(issue, k, None) for k in old_values}
        changes = self._tracked_changes(old_values, new_values)
        if old_metadata is not None:
            from dogcat.event_log import diff_metadata

            changes.update(diff_metadata(old_metadata, issue.metadata))
        by = updates.get("updated_by") or issue.updated_by
        event_type = "updated"
        if "status" in changes and changes["status"]["new"] == "closed":
            event_type = "closed"
        event_record = self._build_event_record(event_type, issue, changes, by=by)
        self._append_with_event([self._issue_record(issue)], event_record)

        return issue

    def change_namespace(
        self,
        issue_id: str,
        new_namespace: str,
        updated_by: str | None = None,
    ) -> Issue:
        """Change an issue's namespace, cascading to all references.

        Updates the namespace field and re-keys the issue.  All other
        issues that reference the old full_id (parent, duplicate_of) are
        patched, as are dependency and link records.

        Args:
            issue_id: The ID of the issue to update (supports partial IDs).
            new_namespace: The new namespace string.
            updated_by: Who is making the change.

        Returns:
            The updated issue with new namespace.

        Raises:
            ValueError: If issue doesn't exist or new ID already taken.
        """
        from dogcat.constants import (
            MAX_NAMESPACE_LEN,
            is_valid_namespace,
        )

        if not is_valid_namespace(new_namespace):
            msg = (
                f"Namespace {new_namespace!r} is invalid "
                f"(must match [A-Za-z0-9_-]+, 1-{MAX_NAMESPACE_LEN} chars)"
            )
            raise ValueError(msg)

        # Acquire the lock first, then reload to capture any concurrent
        # appends (a long-lived web/TUI process can hold a stale view that
        # predates a competing CLI mutation). _save_locked re-uses the
        # already-acquired lock.
        with self._file_lock():
            if self.path.exists():
                self._load()

            resolved_id = self._resolve_or_raise(issue_id)

            issue = self._issues[resolved_id]
            old_full_id = issue.full_id
            new_full_id = f"{new_namespace}-{issue.id}"

            if old_full_id == new_full_id:
                return issue  # no-op

            if new_full_id in self._issues:
                msg = f"Issue with ID {new_full_id} already exists"
                raise ValueError(msg)

            # Update the issue itself
            issue.namespace = new_namespace
            issue.updated_at = datetime.now().astimezone()
            if updated_by:
                issue.updated_by = updated_by

            # Re-key in _issues dict
            del self._issues[old_full_id]
            self._issues[new_full_id] = issue

            # Cascade the rename through everything referencing old_full_id.
            self._cascade_id_rename(old_full_id, new_full_id)

            # Rebuild indexes since IDs changed
            self._rebuild_indexes()

            # Namespace changes cannot be expressed as simple appends (the
            # old full_id must vanish), so rewrite the entire file from
            # current state. Pass _reload=False because we already reloaded
            # under this very lock.
            self._save_locked(
                _reload=False, _rename_event_ids={old_full_id: new_full_id}
            )

        # Emit event after releasing the lock so the event-append path
        # (which also takes the lock) doesn't deadlock.
        self._emit_event(
            "updated",
            issue,
            {"namespace": {"old": old_full_id.split("-")[0], "new": new_namespace}},
            by=updated_by,
        )

        return issue

    def rename_namespace(
        self,
        old_namespace: str,
        new_namespace: str,
        updated_by: str | None = None,
    ) -> list[Issue]:
        """Rename all issues in a namespace, cascading all references.

        Performs a single file rewrite for the entire batch, unlike calling
        ``change_namespace`` per issue (which rewrites per call).

        Args:
            old_namespace: The namespace to rename from.
            new_namespace: The namespace to rename to.
            updated_by: Who is making the change.

        Returns:
            List of updated issues.

        Raises:
            ValueError: If old namespace has no issues, or any new ID
                would collide with an existing issue.
        """
        with self._file_lock():
            if self.path.exists():
                self._load()

            # Collect issues to rename
            targets = [i for i in self._issues.values() if i.namespace == old_namespace]
            if not targets:
                msg = f"No issues found in namespace '{old_namespace}'"
                raise ValueError(msg)

            # Pre-check for collisions
            for issue in targets:
                new_full_id = f"{new_namespace}-{issue.id}"
                if (
                    new_full_id in self._issues
                    and self._issues[new_full_id] is not issue
                ):
                    msg = f"Issue with ID {new_full_id} already exists"
                    raise ValueError(msg)

            # Build old→new mapping for all affected IDs
            id_map: dict[str, str] = {}
            for issue in targets:
                id_map[issue.full_id] = f"{new_namespace}-{issue.id}"

            now = datetime.now().astimezone()

            # Update the issues themselves and re-key
            for issue in targets:
                old_fid = issue.full_id
                issue.namespace = new_namespace
                issue.updated_at = now
                if updated_by:
                    issue.updated_by = updated_by
                del self._issues[old_fid]
                self._issues[issue.full_id] = issue

            # Cascade to references in *all* issues
            for other in self._issues.values():
                if other.parent and other.parent in id_map:
                    other.parent = id_map[other.parent]
                    other.updated_at = now
                if other.duplicate_of and other.duplicate_of in id_map:
                    other.duplicate_of = id_map[other.duplicate_of]
                    other.updated_at = now

            # Cascade to dependencies
            for dep in self._dependencies:
                if dep.issue_id in id_map:
                    dep.issue_id = id_map[dep.issue_id]
                if dep.depends_on_id in id_map:
                    dep.depends_on_id = id_map[dep.depends_on_id]

            # Cascade to links
            for link in self._links:
                if link.from_id in id_map:
                    link.from_id = id_map[link.from_id]
                if link.to_id in id_map:
                    link.to_id = id_map[link.to_id]

            self._rebuild_indexes()
            self._save_locked(_reload=False, _rename_event_ids=id_map)

        # Emit events outside the lock — _emit_event acquires the lock to
        # append, so doing it inside the with-block would deadlock.
        for issue in targets:
            self._emit_event(
                "updated",
                issue,
                {"namespace": {"old": old_namespace, "new": new_namespace}},
                by=updated_by,
            )

        return targets

    def close(
        self,
        issue_id: str,
        reason: str | None = None,
        closed_by: str | None = None,
    ) -> Issue:
        """Close an issue.

        Args:
            issue_id: The ID of the issue to close (supports partial IDs)
            reason: Optional reason for closing
            closed_by: Optional operator who closed the issue

        Returns:
            The closed issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self._resolve_or_raise(issue_id)

        issue = self._issues[resolved_id]
        # Refuse to resurrect a tombstoned issue. Without this guard, a
        # ``dcat delete`` followed by ``dcat close`` flips status back to
        # CLOSED but leaves ``deleted_at`` set — see reopen(), which has
        # always gated on Status.CLOSED. (dogcat-4g76)
        if issue.status == Status.TOMBSTONE:
            msg = (
                f"Issue {issue.full_id} is tombstoned; "
                f"cannot close a deleted issue. Use 'dcat reopen' first."
            )
            raise ValueError(msg)
        if issue.status == Status.CLOSED:
            return issue  # idempotent close

        old_status = issue.status.value

        now = datetime.now().astimezone()
        issue.status = Status.CLOSED
        issue.closed_at = now
        issue.updated_at = now
        if reason:
            issue.closed_reason = reason
        if closed_by:
            issue.closed_by = closed_by

        event_record = self._build_event_record(
            "closed",
            issue,
            {"status": {"old": old_status, "new": "closed"}},
            by=closed_by,
        )
        self._append_with_event([self._issue_record(issue)], event_record)

        return issue

    def reopen(
        self,
        issue_id: str,
        reason: str | None = None,
        reopened_by: str | None = None,
    ) -> Issue:
        """Reopen a closed issue.

        Args:
            issue_id: The ID of the issue to reopen (supports partial IDs)
            reason: Optional reason for reopening
            reopened_by: Optional operator who reopened the issue

        Returns:
            The reopened issue

        Raises:
            ValueError: If issue doesn't exist or is not closed
        """
        resolved_id = self._resolve_or_raise(issue_id)

        issue = self._issues[resolved_id]
        if issue.status != Status.CLOSED:
            msg = f"Issue {issue.full_id} is not closed (status: {issue.status.value})"
            raise ValueError(msg)

        old_status = issue.status.value

        now = datetime.now().astimezone()
        issue.status = Status.OPEN
        issue.updated_at = now
        issue.closed_at = None
        issue.closed_reason = None
        issue.closed_by = None
        if reopened_by:
            issue.updated_by = reopened_by

        changes: dict[str, dict[str, Any]] = {
            "status": {"old": old_status, "new": "open"},
        }
        if reason:
            changes["reopen_reason"] = {"old": None, "new": reason}
        event_record = self._build_event_record(
            "reopened", issue, changes, by=reopened_by
        )
        self._append_with_event([self._issue_record(issue)], event_record)

        return issue

    def delete(
        self,
        issue_id: str,
        reason: str | None = None,
        deleted_by: str | None = None,
    ) -> Issue:
        """Soft delete an issue (create tombstone).

        Args:
            issue_id: The ID of the issue to delete (supports partial IDs)
            reason: Optional reason for deletion
            deleted_by: Optional operator who deleted the issue

        Returns:
            The tombstoned issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self._resolve_or_raise(issue_id)

        issue = self._issues[resolved_id]
        # Idempotent delete: a second delete on a tombstone is a no-op so
        # the original deleted_at / deleted_reason / deleted_by are not
        # silently overwritten (forensic record loss). (dogcat-4g76)
        if issue.status == Status.TOMBSTONE:
            return issue

        old_status = issue.status.value

        now = datetime.now().astimezone()
        issue.status = Status.TOMBSTONE
        issue.deleted_at = now
        issue.updated_at = now
        issue.deleted_reason = reason
        issue.original_type = issue.issue_type
        if deleted_by:
            issue.deleted_by = deleted_by

        # Collect deps/links to remove (for append-only removal records)
        removed_deps = [
            d
            for d in self._dependencies
            if d.issue_id == resolved_id or d.depends_on_id == resolved_id
        ]
        removed_links = [
            link
            for link in self._links
            if link.from_id == resolved_id or link.to_id == resolved_id
        ]

        # Clean up in-memory state
        self._dependencies = [
            d
            for d in self._dependencies
            if d.issue_id != resolved_id and d.depends_on_id != resolved_id
        ]
        self._links = [
            link
            for link in self._links
            if link.from_id != resolved_id and link.to_id != resolved_id
        ]
        self._rebuild_indexes()

        # Append tombstone + removal records (instead of rewriting the file).
        # The delete event ships in the same locked append to halve the
        # write amplification (was issue+deps+links append, then a separate
        # event append).
        records: list[dict[str, Any]] = [issue_to_dict(issue)]
        records.extend(self._dep_record(d, op="remove") for d in removed_deps)
        records.extend(self._link_record(lnk, op="remove") for lnk in removed_links)
        event_record = self._build_event_record(
            "deleted",
            issue,
            {"status": {"old": old_status, "new": "tombstone"}},
            by=deleted_by,
        )
        self._append_with_event(records, event_record)

        return issue

    def add_dependency(
        self,
        issue_id: str,
        depends_on_id: str,
        dep_type: str,
        created_by: str | None = None,
    ) -> Dependency:
        """Add a dependency between issues.

        Args:
            issue_id: The issue with the dependency (supports partial IDs)
            depends_on_id: What it depends on (supports partial IDs)
            dep_type: Type of dependency
            created_by: Who created this dependency

        Returns:
            The created dependency

        Raises:
            ValueError: If either issue doesn't exist or if adding the dependency
                would create a circular dependency
        """
        # Validate dependency type first
        try:
            validated_dep_type = DependencyType(dep_type)
        except ValueError:
            valid_types = [t.value for t in DependencyType]
            msg = f"Invalid dependency type '{dep_type}'. Valid types: {valid_types}"
            raise ValueError(msg) from None

        resolved_issue_id = self._resolve_or_raise(issue_id)
        resolved_depends_on_id = self._resolve_or_raise(depends_on_id)

        # Check if dependency already exists (O(1) index lookup)
        for dep in self._deps_by_issue.get(resolved_issue_id, []):
            if (
                dep.depends_on_id == resolved_depends_on_id
                and dep.dep_type.value == dep_type
            ):
                return dep

        # Check for circular dependency
        from dogcat.deps import would_create_cycle

        if would_create_cycle(self, resolved_issue_id, resolved_depends_on_id):
            msg = (
                f"Cannot add dependency: {resolved_issue_id} -> "
                f"{resolved_depends_on_id} would create a circular dependency"
            )
            raise ValueError(msg)

        dependency = Dependency(
            issue_id=resolved_issue_id,
            depends_on_id=resolved_depends_on_id,
            dep_type=validated_dep_type,
            created_by=created_by,
        )
        self._dependencies.append(dependency)
        self._deps_by_issue.setdefault(resolved_issue_id, []).append(dependency)
        self._deps_by_depends_on.setdefault(resolved_depends_on_id, []).append(
            dependency,
        )
        self._append([self._dep_record(dependency)])
        return dependency

    def remove_dependency(self, issue_id: str, depends_on_id: str) -> None:
        """Remove a dependency.

        Args:
            issue_id: The issue with the dependency (supports partial IDs)
            depends_on_id: What it was depending on (supports partial IDs)

        Raises:
            ValueError: If either issue doesn't exist
        """
        resolved_issue_id = self._resolve_or_raise(issue_id)
        resolved_depends_on_id = self._resolve_or_raise(depends_on_id)

        # Collect removed deps for append-only removal records
        removed = [
            d
            for d in self._dependencies
            if d.issue_id == resolved_issue_id
            and d.depends_on_id == resolved_depends_on_id
        ]
        self._dependencies = [
            d
            for d in self._dependencies
            if not (
                d.issue_id == resolved_issue_id
                and d.depends_on_id == resolved_depends_on_id
            )
        ]
        self._rebuild_indexes()
        if removed:
            self._append([self._dep_record(d, op="remove") for d in removed])

    def get_dependencies(self, issue_id: str) -> list[Dependency]:
        """Get all dependencies of an issue.

        Args:
            issue_id: The issue to query (supports partial IDs)

        Returns:
            List of dependencies

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self._resolve_or_raise(issue_id)
        return list(self._deps_by_issue.get(resolved_id, []))

    def get_dependents(self, issue_id: str) -> list[Dependency]:
        """Get all issues that depend on this one.

        Args:
            issue_id: The issue to query (supports partial IDs)

        Returns:
            List of dependencies pointing to this issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self._resolve_or_raise(issue_id)
        return list(self._deps_by_depends_on.get(resolved_id, []))

    def add_link(
        self,
        from_id: str,
        to_id: str,
        link_type: LinkType | str = LinkType.RELATES_TO,
        created_by: str | None = None,
    ) -> Link:
        """Add a link between issues.

        Args:
            from_id: The source issue (supports partial IDs)
            to_id: The target issue (supports partial IDs)
            link_type: Type of link (default: relates_to)
            created_by: Who created this link

        Returns:
            The created link

        Raises:
            ValueError: If either issue doesn't exist or link already exists
        """
        resolved_from_id = self.resolve_id(from_id)
        if resolved_from_id is None:
            msg = f"Issue {from_id} not found"
            raise ValueError(msg)

        resolved_to_id = self.resolve_id(to_id)
        if resolved_to_id is None:
            msg = f"Issue {to_id} not found"
            raise ValueError(msg)

        # Check if link already exists (O(1) index lookup)
        link_type_str = link_type_value(link_type)
        for link in self._links_by_from.get(resolved_from_id, []):
            if (
                link.to_id == resolved_to_id
                and link_type_value(link.link_type) == link_type_str
            ):
                return link

        link = Link(
            from_id=resolved_from_id,
            to_id=resolved_to_id,
            link_type=link_type,
            created_by=created_by,
        )
        self._links.append(link)
        self._links_by_from.setdefault(resolved_from_id, []).append(link)
        self._links_by_to.setdefault(resolved_to_id, []).append(link)
        self._append([self._link_record(link)])
        return link

    def remove_link(self, from_id: str, to_id: str) -> None:
        """Remove a link between issues.

        Args:
            from_id: The source issue (supports partial IDs)
            to_id: The target issue (supports partial IDs)

        Raises:
            ValueError: If either issue doesn't exist
        """
        resolved_from_id = self.resolve_id(from_id)
        if resolved_from_id is None:
            msg = f"Issue {from_id} not found"
            raise ValueError(msg)

        resolved_to_id = self.resolve_id(to_id)
        if resolved_to_id is None:
            msg = f"Issue {to_id} not found"
            raise ValueError(msg)

        # Collect removed links for append-only removal records
        removed = [
            link
            for link in self._links
            if link.from_id == resolved_from_id and link.to_id == resolved_to_id
        ]
        self._links = [
            link
            for link in self._links
            if not (link.from_id == resolved_from_id and link.to_id == resolved_to_id)
        ]
        self._rebuild_indexes()
        if removed:
            self._append([self._link_record(lnk, op="remove") for lnk in removed])

    def get_links(self, issue_id: str) -> list[Link]:
        """Get all links from an issue.

        Args:
            issue_id: The issue to query (supports partial IDs)

        Returns:
            List of links originating from this issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self._resolve_or_raise(issue_id)
        return list(self._links_by_from.get(resolved_id, []))

    def get_incoming_links(self, issue_id: str) -> list[Link]:
        """Get all links pointing to an issue.

        Args:
            issue_id: The issue to query (supports partial IDs)

        Returns:
            List of links pointing to this issue

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self._resolve_or_raise(issue_id)
        return list(self._links_by_to.get(resolved_id, []))

    def get_children(self, issue_id: str) -> list[Issue]:
        """Get all child issues of an issue.

        Args:
            issue_id: The parent issue to query (supports partial IDs)

        Returns:
            List of issues that have this issue as their parent

        Raises:
            ValueError: If issue doesn't exist
        """
        resolved_id = self._resolve_or_raise(issue_id)
        return [
            self._issues[cid]
            for cid in self._children_by_parent.get(resolved_id, [])
            if cid in self._issues
        ]

    def get_issue_ids(self) -> set[str]:
        """Get all issue IDs in storage.

        Returns:
            Set of all issue IDs
        """
        return set(self._issues.keys())

    def reload(self) -> None:
        """Reload storage from disk.

        This re-reads the JSONL file and updates the in-memory state.
        """
        self._load()

    def remove_archived(self, archived_ids: set[str], remaining_lines: int) -> None:
        """Remove archived issues, dependencies, and links from in-memory state.

        Called after the archive command has already rewritten the JSONL files.
        Updates indexes and bookkeeping to reflect the new file contents.

        Args:
            archived_ids: Set of issue IDs that were archived.
            remaining_lines: Number of lines in the rewritten storage file.
        """
        for issue_id in archived_ids:
            self._issues.pop(issue_id, None)

        self._dependencies = [
            dep
            for dep in self._dependencies
            if dep.issue_id not in archived_ids or dep.depends_on_id not in archived_ids
        ]

        self._links = [
            link
            for link in self._links
            if link.from_id not in archived_ids or link.to_id not in archived_ids
        ]

        self._rebuild_indexes()
        self._base_lines = remaining_lines
        self._appended_lines = 0

    @property
    def all_dependencies(self) -> list[Dependency]:
        """Return all dependency records."""
        return list(self._dependencies)

    @property
    def all_links(self) -> list[Link]:
        """Return all link records."""
        return list(self._links)

    def check_id_uniqueness(self) -> bool:
        """Check the JSONL log for hash-colliding issue records.

        Two distinct issues with the same ``full_id`` would collapse into
        a single in-memory entry under last-write-wins replay, hiding the
        collision. We detect it by walking the raw log and verifying that
        every issue record sharing a ``full_id`` also shares a single
        ``created_at`` value.

        Returns:
            True when no collisions are found (or the file does not yet
            exist). False when at least one collision is detected.
        """
        if not self.path.exists():
            return True
        seen: dict[str, str] = {}
        try:
            with self.path.open("rb") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data = orjson.loads(line)
                    except (orjson.JSONDecodeError, ValueError):
                        continue
                    if classify_record(data) != "issue":
                        continue
                    namespace = data.get("namespace", "")
                    issue_id = data.get("id", "")
                    if not issue_id:
                        continue
                    full_id = f"{namespace}-{issue_id}" if namespace else issue_id
                    created_at = data.get("created_at", "")
                    prior = seen.get(full_id)
                    if prior is None:
                        seen[full_id] = created_at
                    elif prior != created_at:
                        return False
        except OSError:
            return False
        return True

    def find_dangling_dependencies(self) -> list[Dependency]:
        """Find dependencies that reference non-existent issues.

        Returns:
            List of dependencies where either issue_id or depends_on_id
            is not in storage.
        """
        return [
            dep
            for dep in self._dependencies
            if dep.issue_id not in self._issues or dep.depends_on_id not in self._issues
        ]

    def remove_dependencies(self, deps_to_remove: list[Dependency]) -> None:
        """Remove specific dependency records and rewrite storage.

        Args:
            deps_to_remove: Dependencies to remove.
        """
        remove_set = {(d.issue_id, d.depends_on_id, d.dep_type) for d in deps_to_remove}
        with self._file_lock():
            if self.path.exists():
                self._load()
            self._dependencies = [
                d
                for d in self._dependencies
                if (d.issue_id, d.depends_on_id, d.dep_type) not in remove_set
            ]
            self._rebuild_indexes()
            self._save_locked(_reload=False)

    def prune_tombstones(self) -> list[str]:
        """Permanently remove tombstoned issues and orphaned events from storage.

        Returns:
            List of pruned issue IDs
        """
        with self._file_lock():
            if self.path.exists():
                self._load()

            tombstone_ids = [
                issue_id
                for issue_id, issue in self._issues.items()
                if issue.status == Status.TOMBSTONE
            ]

            for issue_id in tombstone_ids:
                del self._issues[issue_id]

            # Collect IDs to prune: tombstones + any orphaned event references
            prune_ids = set(tombstone_ids)
            if self.path.exists():
                with self.path.open("rb") as src:
                    for raw_line in src:
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        try:
                            data = orjson.loads(raw_line)
                        except (orjson.JSONDecodeError, ValueError):
                            continue
                        if data.get("record_type") == "event":
                            eid = data.get("issue_id", "")
                            if eid and eid not in self._issues:
                                prune_ids.add(eid)

            if prune_ids:
                self._save_locked(_reload=False, _prune_event_ids=prune_ids)

        return tombstone_ids


@dataclasses.dataclass
class NamespaceCounts:
    """Counts for a single namespace."""

    issues: int = 0
    inbox: int = 0

    @property
    def total(self) -> int:
        """Total items across issues and inbox."""
        return self.issues + self.inbox


def get_namespaces(
    storage: JSONLStorage,
    *,
    dogcats_dir: str | Path | None = None,
    include_inbox: bool = True,
) -> dict[str, NamespaceCounts]:
    """Get namespace counts from issues and optionally inbox proposals.

    Namespaces listed in the ``pinned_namespaces`` config key are always
    included, even when they contain no issues or proposals.

    Args:
        storage: Issue storage instance.
        dogcats_dir: Path to .dogcats directory (needed for inbox).
                     Defaults to storage.dogcats_dir.
        include_inbox: Whether to include inbox proposals in counts.

    Returns:
        Dictionary mapping namespace names to counts.
    """
    ns_counts: dict[str, NamespaceCounts] = {}
    for issue in storage.list():
        if issue.is_tombstone():
            continue
        counts = ns_counts.setdefault(issue.namespace, NamespaceCounts())
        counts.issues += 1

    if include_inbox:
        try:
            from dogcat.inbox import InboxStorage

            resolved_dir = str(dogcats_dir) if dogcats_dir else str(storage.dogcats_dir)
            inbox = InboxStorage(dogcats_dir=resolved_dir)
            for p in inbox.list(include_tombstones=False):
                counts = ns_counts.setdefault(p.namespace, NamespaceCounts())
                counts.inbox += 1
        except (OSError, ValueError, RuntimeError):
            pass

    # Include pinned namespaces from config (always present even if empty)
    try:
        from dogcat.config import load_config

        resolved_dir = str(dogcats_dir) if dogcats_dir else str(storage.dogcats_dir)
        config = load_config(resolved_dir)
        pinned: list[str] = config.get("pinned_namespaces", [])
        for ns in pinned:
            ns_counts.setdefault(ns, NamespaceCounts())
    except (OSError, ValueError):
        pass

    return ns_counts
