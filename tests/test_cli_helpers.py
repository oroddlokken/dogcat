"""Direct tests for ``dogcat.cli._helpers``.

``apply_to_each`` powers every multi-id CLI op
(``dcat close A B C``, ``dcat reopen``, ``dcat inbox close/delete/reject``).
The error-aggregation contract — *continue on error, return True iff
any op raised, format messages as ``verb id: exc``* — is core behaviour
that previously had no regression test. (dogcat-4uez)

The remaining classes cover the cross-cutting helpers
(``apply_common_filters``, ``with_ns_shim``, ``require_resolved_id``,
``_make_alias``, ``check_*``) that previously only ran end-to-end via
``CliRunner``. (dogcat-2kw5)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from dogcat.cli._helpers import apply_to_each
from dogcat.cli._json_state import reset_json

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from dogcat.models import Issue


@pytest.fixture(autouse=True)
def _reset_json_state() -> Generator[None, None, None]:
    """Keep the global JSON flag isolated across tests.

    ``apply_to_each`` calls ``echo_error``, which checks the module-wide
    JSON flag. A leaked ``True`` from another test would change the
    error format (``{"error": ...}`` instead of ``Error: ...``) and
    make assertions on stderr brittle.
    """
    reset_json()
    yield
    reset_json()


class TestApplyToEach:
    """Cover the multi-id error-aggregation contract."""

    def test_all_success_returns_false(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No raises means returns False with no error output."""
        seen: list[str] = []

        def op(issue_id: str) -> None:
            seen.append(issue_id)

        assert apply_to_each(["a", "b", "c"], op, verb="close") is False
        assert seen == ["a", "b", "c"]
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_empty_id_list_returns_false_silently(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An empty ids list is a no-op: False, nothing printed."""
        called = {"n": 0}

        def op(_: str) -> None:
            called["n"] += 1

        assert apply_to_each([], op, verb="close") is False
        assert called["n"] == 0
        assert capsys.readouterr().err == ""

    def test_mid_list_failure_continues_to_remaining_ids(self) -> None:
        """A mid-list raise must not abort iteration.

        The whole point of ``apply_to_each`` is that closing 5 issues
        where #3 is broken still closes the other 4. Aborting on the
        first error would silently leave #4 and #5 untouched.
        """
        seen: list[str] = []

        def op(issue_id: str) -> None:
            seen.append(issue_id)
            if issue_id == "b":
                msg = "boom"
                raise ValueError(msg)

        result = apply_to_each(["a", "b", "c", "d"], op, verb="close")
        assert result is True
        # Iteration continued past the failure to ``c`` and ``d``.
        assert seen == ["a", "b", "c", "d"]

    def test_error_message_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Error format is ``Error: <verb> <id>: <exception>``."""

        def op(issue_id: str) -> None:
            msg = f"id was {issue_id}"
            raise ValueError(msg)

        apply_to_each(["xyz"], op, verb="reopen")
        err = capsys.readouterr().err
        # Plain mode prefix from echo_error + verb-prefixed apply_to_each shape.
        assert "Error: reopen xyz: id was xyz" in err

    def test_returns_true_iff_any_raised(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Return is True iff at least one op raised — not "all ops"."""

        def op(issue_id: str) -> None:
            if issue_id == "bad":
                msg = "nope"
                raise RuntimeError(msg)

        # Single failure in a long list still flips the return.
        assert apply_to_each(["ok1", "ok2", "bad", "ok3"], op, verb="x") is True

        capsys.readouterr()  # flush
        # All-success.
        assert apply_to_each(["ok1", "ok2"], op, verb="x") is False

    def test_aggregates_multiple_errors(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Every failing id produces its own ``echo_error`` line."""

        def op(issue_id: str) -> None:
            msg = f"failed {issue_id}"
            raise ValueError(msg)

        result = apply_to_each(["a", "b", "c"], op, verb="delete")
        assert result is True

        err_lines = [
            line for line in capsys.readouterr().err.splitlines() if line.strip()
        ]
        assert len(err_lines) == 3
        assert "delete a" in err_lines[0]
        assert "delete b" in err_lines[1]
        assert "delete c" in err_lines[2]


# ---------------------------------------------------------------------------
# apply_common_filters: one focused test per filter clause.
# ---------------------------------------------------------------------------


def _issue(
    issue_id: str = "abc",
    *,
    namespace: str = "test",
    issue_type: str = "task",
    priority: int = 2,
    status: str = "open",
    owner: str | None = None,
    labels: list[str] | None = None,
    parent: str | None = None,
    metadata: dict[str, object] | None = None,
    comments: list[object] | None = None,
) -> Issue:
    """Build an Issue suitable for apply_common_filters tests."""
    from dogcat.models import Comment, IssueType, Status
    from dogcat.models import Issue as IssueCls

    issue = IssueCls(
        id=issue_id,
        namespace=namespace,
        title=f"Issue {issue_id}",
        issue_type=IssueType(issue_type),
        priority=priority,
        status=Status(status),
        owner=owner,
        labels=labels or [],
        parent=parent,
        metadata=metadata or {},
    )
    if comments:
        # Each entry is a Comment dataclass; the helper just needs truthy.
        issue.comments = [
            c
            if isinstance(c, Comment)
            else Comment(
                id=str(idx),
                issue_id=issue.full_id,
                author="anyone",
                text="hello",
            )
            for idx, c in enumerate(comments)
        ]
    return issue


class TestApplyCommonFilters:
    """One focused test per filter clause in apply_common_filters."""

    def test_no_filters_returns_input_unchanged(self) -> None:
        """No filters returns input unchanged."""
        from dogcat.cli._helpers import apply_common_filters

        a = _issue("a")
        b = _issue("b")
        assert apply_common_filters([a, b]) == [a, b]

    def test_filter_by_issue_type(self) -> None:
        """Filter by issue type."""
        from dogcat.cli._helpers import apply_common_filters

        bug = _issue("a", issue_type="bug")
        task = _issue("b", issue_type="task")
        out = apply_common_filters([bug, task], issue_type="bug")
        assert out == [bug]

    def test_filter_by_priority(self) -> None:
        """Filter by priority."""
        from dogcat.cli._helpers import apply_common_filters

        crit = _issue("a", priority=0)
        med = _issue("b", priority=2)
        out = apply_common_filters([crit, med], priority=0)
        assert out == [crit]

    def test_filter_by_priority_zero_is_not_skipped(self) -> None:
        """``priority is not None`` — falsy 0 must still filter.

        Regression: ``if priority:`` would have silently treated p=0
        (Critical) as "no filter".
        """
        from dogcat.cli._helpers import apply_common_filters

        crit = _issue("a", priority=0)
        med = _issue("b", priority=2)
        out = apply_common_filters([crit, med], priority=0)
        assert out == [crit]

    def test_filter_by_label_single(self) -> None:
        """Filter by label single."""
        from dogcat.cli._helpers import apply_common_filters

        bug = _issue("a", labels=["bug", "ux"])
        chore = _issue("b", labels=["chore"])
        out = apply_common_filters([bug, chore], label="bug")
        assert out == [bug]

    def test_filter_by_label_multi_requires_all(self) -> None:
        """Multi-label filter is an AND, not an OR."""
        from dogcat.cli._helpers import apply_common_filters

        both = _issue("a", labels=["bug", "ux"])
        only_bug = _issue("b", labels=["bug"])
        out = apply_common_filters([both, only_bug], label="bug,ux")
        assert out == [both]

    def test_filter_by_owner(self) -> None:
        """Filter by owner."""
        from dogcat.cli._helpers import apply_common_filters

        alice = _issue("a", owner="alice@example.com")
        bob = _issue("b", owner="bob@example.com")
        out = apply_common_filters([alice, bob], owner="alice@example.com")
        assert out == [alice]

    def test_filter_no_parent(self) -> None:
        """Filter no parent."""
        from dogcat.cli._helpers import apply_common_filters

        rooted = _issue("a", parent=None)
        child = _issue("b", parent="test-a")
        out = apply_common_filters([rooted, child], no_parent=True)
        assert out == [rooted]

    def test_filter_agent_only_excludes_manual(self) -> None:
        """Filter agent only excludes manual."""
        from dogcat.cli._helpers import apply_common_filters

        manual = _issue("a", metadata={"manual": True})
        auto = _issue("b", metadata={})
        out = apply_common_filters([manual, auto], agent_only=True)
        assert out == [auto]

    def test_filter_agent_only_excludes_no_agent_too(self) -> None:
        """``no_agent=True`` is treated identically to ``manual=True``."""
        from dogcat.cli._helpers import apply_common_filters

        no_agent = _issue("a", metadata={"no_agent": True})
        auto = _issue("b", metadata={})
        out = apply_common_filters([no_agent, auto], agent_only=True)
        assert out == [auto]

    def test_filter_manual_only_keeps_manual(self) -> None:
        """Filter manual only keeps manual."""
        from dogcat.cli._helpers import apply_common_filters

        manual = _issue("a", metadata={"manual": True})
        auto = _issue("b", metadata={})
        out = apply_common_filters([manual, auto], manual_only=True)
        assert out == [manual]

    def test_filter_has_comments(self) -> None:
        """Filter has comments."""
        from dogcat.cli._helpers import apply_common_filters

        with_c = _issue("a", comments=["x"])
        without_c = _issue("b")
        out = apply_common_filters([with_c, without_c], has_comments=True)
        assert out == [with_c]

    def test_filter_without_comments(self) -> None:
        """Filter without comments."""
        from dogcat.cli._helpers import apply_common_filters

        with_c = _issue("a", comments=["x"])
        without_c = _issue("b")
        out = apply_common_filters([with_c, without_c], without_comments=True)
        assert out == [without_c]

    def test_agent_only_and_manual_only_are_mutually_exclusive(self) -> None:
        """Agent only and manual only are mutually exclusive."""
        import typer

        from dogcat.cli._helpers import apply_common_filters

        with pytest.raises(typer.BadParameter):
            apply_common_filters([], agent_only=True, manual_only=True)

    def test_has_and_without_comments_are_mutually_exclusive(self) -> None:
        """Has and without comments are mutually exclusive."""
        import typer

        from dogcat.cli._helpers import apply_common_filters

        with pytest.raises(typer.BadParameter):
            apply_common_filters([], has_comments=True, without_comments=True)

    def test_explicit_namespace_filters_to_one(self, tmp_path: Path) -> None:
        """Explicit namespace filters to one."""
        from dogcat.cli._helpers import apply_common_filters

        a = _issue("a", namespace="alpha")
        b = _issue("b", namespace="beta")
        dogcats = tmp_path / ".dogcats"
        dogcats.mkdir()
        out = apply_common_filters(
            [a, b],
            namespace="alpha",
            dogcats_dir=str(dogcats),
        )
        assert out == [a]

    def test_all_namespaces_skips_namespace_filter(self, tmp_path: Path) -> None:
        """All namespaces skips namespace filter."""
        from dogcat.cli._helpers import apply_common_filters

        a = _issue("a", namespace="alpha")
        b = _issue("b", namespace="beta")
        dogcats = tmp_path / ".dogcats"
        dogcats.mkdir()
        out = apply_common_filters(
            [a, b],
            namespace="alpha",
            all_namespaces=True,
            dogcats_dir=str(dogcats),
        )
        assert out == [a, b]

    def test_filter_by_parent_includes_parent_and_children(
        self, tmp_path: Path
    ) -> None:
        """``parent=X`` keeps X and any direct child of X."""
        from dogcat.cli._helpers import apply_common_filters
        from dogcat.models import Issue
        from dogcat.storage import JSONLStorage

        storage = JSONLStorage(
            str(tmp_path / ".dogcats" / "issues.jsonl"), create_dir=True
        )
        parent = storage.create(Issue(id="parent", namespace="t", title="Parent"))
        child = storage.create(
            Issue(
                id="child",
                namespace="t",
                title="Child",
                parent=parent.full_id,
            )
        )
        sibling = storage.create(Issue(id="sibling", namespace="t", title="Sibling"))

        out = apply_common_filters(
            [parent, child, sibling],
            parent=parent.full_id,
            storage=storage,
        )
        assert {i.full_id for i in out} == {parent.full_id, child.full_id}


# ---------------------------------------------------------------------------
# Smaller cross-cuts: the mutually-exclusive checks and apply_comment_filter.
# ---------------------------------------------------------------------------


class TestMutuallyExclusiveChecks:
    """Each check raises typer.BadParameter only on the disallowed combo."""

    def test_check_agent_manual_exclusive_raises_on_both(self) -> None:
        """Check agent manual exclusive raises on both."""
        import typer

        from dogcat.cli._helpers import check_agent_manual_exclusive

        with pytest.raises(typer.BadParameter, match="mutually exclusive"):
            check_agent_manual_exclusive(agent_only=True, manual_only=True)

    @pytest.mark.parametrize(
        ("agent", "manual"),
        [(True, False), (False, True), (False, False)],
    )
    def test_check_agent_manual_exclusive_accepts_singletons(
        self, agent: bool, manual: bool
    ) -> None:
        """Check agent manual exclusive accepts singletons."""
        from dogcat.cli._helpers import check_agent_manual_exclusive

        assert (
            check_agent_manual_exclusive(agent_only=agent, manual_only=manual) is None
        )

    def test_check_comments_exclusive_raises_on_both(self) -> None:
        """Check comments exclusive raises on both."""
        import typer

        from dogcat.cli._helpers import check_comments_exclusive

        with pytest.raises(typer.BadParameter, match="mutually exclusive"):
            check_comments_exclusive(has_comments=True, without_comments=True)

    @pytest.mark.parametrize(
        ("has_c", "without_c"),
        [(True, False), (False, True), (False, False)],
    )
    def test_check_comments_exclusive_accepts_singletons(
        self, has_c: bool, without_c: bool
    ) -> None:
        """Check comments exclusive accepts singletons."""
        from dogcat.cli._helpers import check_comments_exclusive

        assert (
            check_comments_exclusive(has_comments=has_c, without_comments=without_c)
            is None
        )


class TestApplyCommentFilter:
    """Comment-presence filter handles both directions plus the no-op default."""

    def test_no_flags_passes_through(self) -> None:
        """No flags passes through."""
        from dogcat.cli._helpers import apply_comment_filter

        a = _issue("a")
        b = _issue("b", comments=["x"])
        assert apply_comment_filter([a, b]) == [a, b]

    def test_has_comments_keeps_only_with(self) -> None:
        """Has comments keeps only with."""
        from dogcat.cli._helpers import apply_comment_filter

        a = _issue("a")
        b = _issue("b", comments=["x"])
        assert apply_comment_filter([a, b], has_comments=True) == [b]

    def test_without_comments_keeps_only_empty(self) -> None:
        """Without comments keeps only empty."""
        from dogcat.cli._helpers import apply_comment_filter

        a = _issue("a")
        b = _issue("b", comments=["x"])
        assert apply_comment_filter([a, b], without_comments=True) == [a]

    def test_both_flags_raise(self) -> None:
        """Both flags raise."""
        import typer

        from dogcat.cli._helpers import apply_comment_filter

        with pytest.raises(typer.BadParameter):
            apply_comment_filter([], has_comments=True, without_comments=True)


# ---------------------------------------------------------------------------
# require_resolved_id: resolve happy path + exit on missing.
# ---------------------------------------------------------------------------


class TestRequireResolvedId:
    """The two-line resolve-or-exit helper."""

    def test_returns_full_id_on_match(self, tmp_path: Path) -> None:
        """Returns full id on match."""
        from dogcat.cli._helpers import require_resolved_id
        from dogcat.models import Issue
        from dogcat.storage import JSONLStorage

        storage = JSONLStorage(
            str(tmp_path / ".dogcats" / "issues.jsonl"), create_dir=True
        )
        created = storage.create(Issue(id="abcd", namespace="t", title="x"))
        # Partial id resolves to the full id.
        assert require_resolved_id(storage, "abcd") == created.full_id

    def test_raises_typer_exit_on_missing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Raises typer exit on missing."""
        import typer

        from dogcat.cli._helpers import require_resolved_id
        from dogcat.storage import JSONLStorage

        storage = JSONLStorage(
            str(tmp_path / ".dogcats" / "issues.jsonl"), create_dir=True
        )
        with pytest.raises(typer.Exit) as exc:
            require_resolved_id(storage, "missing-id", label="Parent")
        assert exc.value.exit_code == 1
        # Label propagates into the error message.
        assert "Parent missing-id not found" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# with_ns_shim: signature is augmented and shim values are dropped on call.
# ---------------------------------------------------------------------------


class TestWithNsShim:
    """The decorator that lets per-command CLIs accept --namespace silently."""

    def test_adds_shim_params_to_signature(self) -> None:
        """Adds shim params to signature."""
        import inspect

        from dogcat.cli._helpers import with_ns_shim

        def cmd(*, x: int = 0) -> int:
            return x

        wrapped = with_ns_shim(cmd)
        params = inspect.signature(wrapped).parameters
        assert "namespace" in params
        assert "all_namespaces" in params
        assert "x" in params

    def test_shim_values_are_dropped(self) -> None:
        """Shim values are dropped."""
        from dogcat.cli._helpers import with_ns_shim

        captured: dict[str, object] = {}

        def cmd(*, x: int = 0) -> None:
            captured["x"] = x

        wrapped = with_ns_shim(cmd)
        wrapped(x=1, namespace="ns", all_namespaces=True)
        assert captured == {"x": 1}


# ---------------------------------------------------------------------------
# _make_alias: signature cloning, exclude_params, param_defaults.
# ---------------------------------------------------------------------------


class TestMakeAlias:
    """The signature-cloning helper used by command aliases."""

    def test_alias_clones_signature_and_passes_defaults(self) -> None:
        """Alias clones signature and passes defaults."""
        import inspect

        from dogcat.cli._helpers import _make_alias

        def base(*, a: int = 1, b: int = 2, c: int = 3) -> tuple[int, int, int]:
            return (a, b, c)

        alias = _make_alias(
            base,
            doc="alias doc",
            exclude_params=frozenset({"c"}),
            param_defaults={"c": 99},
        )
        # Excluded params do not appear on the alias signature.
        assert "c" not in inspect.signature(alias).parameters
        assert "a" in inspect.signature(alias).parameters
        assert alias.__doc__ == "alias doc"
        # Excluded param is force-set to the alias default at call time.
        assert alias(a=10, b=20) == (10, 20, 99)
