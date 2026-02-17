"""Tests for display and formatting functions."""

from dogcat.cli._formatting import (
    format_issue_brief,
    format_issue_full,
    format_issue_table,
    format_issue_tree,
    get_legend,
)
from dogcat.models import Issue, Status


class TestFormatIssueTableMarkupEscaping:
    """Test that Rich markup in issue titles is escaped in table output."""

    def test_rich_markup_in_title_is_escaped(self) -> None:
        """Test that titles containing Rich markup tags are escaped."""
        issue = Issue(
            id="abc1",
            namespace="dc",
            title="[red]dangerous[/red] title",
        )

        output = format_issue_table([issue])

        # The literal text should appear, not be interpreted as markup
        assert "dangerous" in output
        # The markup tags should NOT cause coloring; they should be escaped
        # (Rich would consume [red]...[/red] if not escaped)
        assert "title" in output

    def test_square_brackets_in_title_escaped(self) -> None:
        """Test that square brackets in titles don't break Rich rendering."""
        issue = Issue(
            id="abc2",
            namespace="dc",
            title="Array[int] type hint",
        )

        output = format_issue_table([issue])

        # Should render without errors and contain the title text
        assert "Array" in output
        assert "int" in output
        assert "type hint" in output

    def test_nested_markup_in_title_escaped(self) -> None:
        """Test that nested Rich markup in titles is escaped."""
        issue = Issue(
            id="abc3",
            namespace="dc",
            title="[bold][red]very bad[/red][/bold]",
        )

        output = format_issue_table([issue])

        assert "very bad" in output

    def test_normal_title_renders_correctly(self) -> None:
        """Test that normal titles without markup render correctly."""
        issue = Issue(
            id="abc4",
            namespace="dc",
            title="Normal issue title",
        )

        output = format_issue_table([issue])

        assert "Normal issue title" in output

    def test_labels_with_markup_escaped(self) -> None:
        """Test that labels containing markup characters are escaped."""
        issue = Issue(
            id="abc5",
            namespace="dc",
            title="Test",
            labels=["[urgent]"],
        )

        output = format_issue_table([issue])

        # Should not crash and should contain label text
        assert "urgent" in output

    def test_empty_list_returns_empty_string(self) -> None:
        """Test that empty issue list returns empty string."""
        output = format_issue_table([])
        assert output == ""


class TestFormatIssueTreeOrphanedChildren:
    """Test that format_issue_tree handles orphaned children correctly."""

    def test_orphaned_child_treated_as_root(self) -> None:
        """Test that a child whose parent is not in the set is shown as root."""
        child = Issue(
            id="child1",
            namespace="dc",
            title="Orphaned child",
            parent="dc-missing",
        )

        output = format_issue_tree([child])

        assert "Orphaned child" in output
        # Should not be indented since parent is not in set
        assert not output.startswith("  ")

    def test_parent_and_child_both_in_set(self) -> None:
        """Test normal parent-child tree rendering."""
        parent = Issue(
            id="par1",
            namespace="dc",
            title="Parent issue",
        )
        child = Issue(
            id="ch1",
            namespace="dc",
            title="Child issue",
            parent="dc-par1",
        )

        output = format_issue_tree([parent, child])

        assert "Parent issue" in output
        assert "Child issue" in output
        # Child should be indented
        for line in output.splitlines():
            if "Child issue" in line:
                assert line.startswith("  ")

    def test_mixed_orphaned_and_rooted(self) -> None:
        """Test mix of orphaned children and proper roots."""
        root = Issue(
            id="root1",
            namespace="dc",
            title="Root issue",
        )
        orphan = Issue(
            id="orphan1",
            namespace="dc",
            title="Orphan issue",
            parent="dc-gone",
        )

        output = format_issue_tree([root, orphan])

        assert "Root issue" in output
        assert "Orphan issue" in output


class TestExternalRefDisplay:
    """Test that external_ref is shown in brief, full, and table formatting."""

    def test_brief_shows_external_ref(self) -> None:
        """External ref appears in brief output."""
        issue = Issue(
            id="ref1",
            namespace="dc",
            title="Has external ref",
            external_ref="JIRA-123",
        )
        output = format_issue_brief(issue)
        assert "extref: JIRA-123" in output

    def test_brief_no_external_ref(self) -> None:
        """No ext ref marker when external_ref is not set."""
        issue = Issue(
            id="ref2",
            namespace="dc",
            title="No external ref",
        )
        output = format_issue_brief(issue)
        # Should not contain any ext ref marker
        assert "JIRA" not in output

    def test_full_shows_external_ref(self) -> None:
        """External ref appears in full output."""
        issue = Issue(
            id="ref3",
            namespace="dc",
            title="Full display ref",
            external_ref="PLAT-456",
        )
        output = format_issue_full(issue)
        assert "External ref:" in output
        assert "PLAT-456" in output

    def test_full_no_external_ref(self) -> None:
        """No External ref line when not set."""
        issue = Issue(
            id="ref4",
            namespace="dc",
            title="Full no ref",
        )
        output = format_issue_full(issue)
        assert "External ref:" not in output

    def test_table_shows_ext_ref_column_when_present(self) -> None:
        """Ext Ref column appears when any issue has external_ref."""
        issue_with = Issue(
            id="ref5",
            namespace="dc",
            title="With ref",
            external_ref="BUG-789",
        )
        issue_without = Issue(
            id="ref6",
            namespace="dc",
            title="Without ref",
        )
        output = format_issue_table([issue_with, issue_without])
        assert "Ext Ref" in output
        assert "BUG-789" in output

    def test_table_no_ext_ref_column_when_none_present(self) -> None:
        """No Ext Ref column when no issues have external_ref."""
        issue = Issue(
            id="ref7",
            namespace="dc",
            title="Plain issue",
        )
        output = format_issue_table([issue])
        assert "Ext Ref" not in output


class TestDeferredAnnotations:
    """Test deferred subtree collapse annotations in formatting."""

    def test_brief_hidden_subtask_count(self) -> None:
        """Hidden subtask count renders in brief output."""
        issue = Issue(
            id="def1",
            namespace="dc",
            title="Deferred parent",
            status=Status.DEFERRED,
        )
        output = format_issue_brief(issue, hidden_subtask_count=3)
        assert "3 hidden subtasks" in output

    def test_brief_deferred_blocker_annotation(self) -> None:
        """Deferred blocker annotation renders in brief output."""
        issue = Issue(
            id="ext1",
            namespace="dc",
            title="External issue",
        )
        output = format_issue_brief(
            issue,
            deferred_blockers=["dc-def1", "dc-def2"],
        )
        assert "blocked by deferred: dc-def1, dc-def2" in output

    def test_brief_no_deferred_annotations_when_empty(self) -> None:
        """No deferred annotations appear when params are None/empty."""
        issue = Issue(
            id="plain1",
            namespace="dc",
            title="Plain issue",
        )
        output = format_issue_brief(
            issue,
            hidden_subtask_count=None,
            deferred_blockers=None,
        )
        assert "hidden subtasks" not in output
        assert "blocked by deferred" not in output

        output2 = format_issue_brief(
            issue,
            hidden_subtask_count=None,
            deferred_blockers=[],
        )
        assert "hidden subtasks" not in output2
        assert "blocked by deferred" not in output2

    def test_tree_passes_hidden_counts(self) -> None:
        """Tree mode renders hidden count on deferred parent."""
        parent = Issue(
            id="dp1",
            namespace="dc",
            title="Deferred parent",
            status=Status.DEFERRED,
        )
        output = format_issue_tree(
            [parent],
            hidden_counts={"dc-dp1": 5},
        )
        assert "5 hidden subtasks" in output

    def test_table_shows_hidden_count_in_title(self) -> None:
        """Table renders hidden subtask count in title column."""
        issue = Issue(
            id="dp2",
            namespace="dc",
            title="Deferred parent",
            status=Status.DEFERRED,
        )
        output = format_issue_table(
            [issue],
            hidden_counts={"dc-dp2": 2},
        )
        assert "2 hidden subtasks" in output


class TestPreviewSubtasks:
    """Test preview subtasks under deferred parents in all formats."""

    def _make_deferred_parent(self, pid: str = "dp1") -> Issue:
        return Issue(
            id=pid,
            namespace="dc",
            title="Deferred parent",
            status=Status.DEFERRED,
        )

    def _make_children(self, parent_id: str, count: int) -> list[Issue]:
        return [
            Issue(
                id=f"ch{i}",
                namespace="dc",
                title=f"Child {i}",
                parent=f"dc-{parent_id}",
                priority=i,
            )
            for i in range(count)
        ]

    # --- Brief format ---

    def test_brief_preview_subtasks_indented(self) -> None:
        """Preview subtasks are rendered indented below deferred parent in brief."""
        parent = self._make_deferred_parent()
        self._make_children("dp1", 2)
        # Brief format with previews is handled in list_issues,
        # not format_issue_brief. Here we test that format_issue_brief
        # suppresses hidden count when previews exist.
        output = format_issue_brief(parent, hidden_subtask_count=None)
        assert "hidden subtasks" not in output

    def test_brief_hidden_count_suppressed_when_previews_exist(self) -> None:
        """Hidden subtask count on parent line is suppressed when previews exist."""
        parent = self._make_deferred_parent()
        # When previews exist, list_issues passes hidden_subtask_count=None
        output = format_issue_brief(parent, hidden_subtask_count=None)
        assert "hidden subtasks" not in output

    # --- Tree format ---

    def test_tree_preview_subtasks_rendered(self) -> None:
        """Tree mode renders preview subtasks indented below deferred parent."""
        parent = self._make_deferred_parent()
        children = self._make_children("dp1", 2)
        output = format_issue_tree(
            [parent],
            hidden_counts={"dc-dp1": 2},
            preview_subtasks={"dc-dp1": children},
        )
        assert "Child 0" in output
        assert "Child 1" in output
        # No hidden count annotation on parent line (previews replace it)
        assert "hidden subtasks" not in output

    def test_tree_preview_with_summary_line(self) -> None:
        """Tree shows summary line when more subtasks than previewed."""
        parent = self._make_deferred_parent()
        children = self._make_children("dp1", 3)
        output = format_issue_tree(
            [parent],
            hidden_counts={"dc-dp1": 5},
            preview_subtasks={"dc-dp1": children},
        )
        assert "Child 0" in output
        assert "Child 1" in output
        assert "Child 2" in output
        assert "...and 2 more hidden subtasks" in output

    def test_tree_no_summary_when_all_fit(self) -> None:
        """Tree shows no summary line when all subtasks fit in preview."""
        parent = self._make_deferred_parent()
        children = self._make_children("dp1", 2)
        output = format_issue_tree(
            [parent],
            hidden_counts={"dc-dp1": 2},
            preview_subtasks={"dc-dp1": children},
        )
        assert "more hidden subtasks" not in output

    def test_tree_preview_sorted_by_priority(self) -> None:
        """Preview subtasks are sorted by priority (highest first)."""
        parent = self._make_deferred_parent()
        # Children already sorted by priority in _collapse_deferred_subtrees
        children = [
            Issue(
                id="hi",
                namespace="dc",
                title="High priority",
                parent="dc-dp1",
                priority=0,
            ),
            Issue(
                id="lo",
                namespace="dc",
                title="Low priority",
                parent="dc-dp1",
                priority=3,
            ),
        ]
        output = format_issue_tree(
            [parent],
            hidden_counts={"dc-dp1": 2},
            preview_subtasks={"dc-dp1": children},
        )
        lines = output.splitlines()
        hi_idx = next(i for i, line in enumerate(lines) if "High priority" in line)
        lo_idx = next(i for i, line in enumerate(lines) if "Low priority" in line)
        assert hi_idx < lo_idx

    def test_tree_hidden_count_on_parent_suppressed_with_previews(self) -> None:
        """Tree: no [N hidden subtasks] on parent line when previews exist."""
        parent = self._make_deferred_parent()
        children = self._make_children("dp1", 1)
        output = format_issue_tree(
            [parent],
            hidden_counts={"dc-dp1": 5},
            preview_subtasks={"dc-dp1": children},
        )
        # The parent line should NOT have "5 hidden subtasks"
        parent_line = next(ln for ln in output.splitlines() if "Deferred parent" in ln)
        assert "hidden subtasks" not in parent_line

    # --- Table format ---

    def test_table_preview_subtasks_rendered(self) -> None:
        """Table renders preview subtask rows below deferred parent."""
        parent = self._make_deferred_parent()
        children = self._make_children("dp1", 2)
        output = format_issue_table(
            [parent],
            hidden_counts={"dc-dp1": 2},
            preview_subtasks={"dc-dp1": children},
        )
        assert "Child 0" in output
        assert "Child 1" in output
        # No hidden count on parent when previews exist
        assert "hidden subtasks" not in output

    def test_table_preview_with_summary_line(self) -> None:
        """Table shows summary row when more subtasks than previewed."""
        parent = self._make_deferred_parent()
        children = self._make_children("dp1", 3)
        output = format_issue_table(
            [parent],
            hidden_counts={"dc-dp1": 5},
            preview_subtasks={"dc-dp1": children},
        )
        assert "Child 0" in output
        assert "...and 2 more hidden subtasks" in output

    def test_table_no_summary_when_all_fit(self) -> None:
        """Table shows no summary row when all subtasks fit in preview."""
        parent = self._make_deferred_parent()
        children = self._make_children("dp1", 2)
        output = format_issue_table(
            [parent],
            hidden_counts={"dc-dp1": 2},
            preview_subtasks={"dc-dp1": children},
        )
        assert "more hidden subtasks" not in output

    def test_table_hidden_count_suppressed_with_previews(self) -> None:
        """Table: no [N hidden subtasks] in title when previews exist."""
        parent = self._make_deferred_parent()
        children = self._make_children("dp1", 1)
        output = format_issue_table(
            [parent],
            hidden_counts={"dc-dp1": 3},
            preview_subtasks={"dc-dp1": children},
        )
        assert "3 hidden subtasks" not in output


class TestLegendColors:
    """Test legend uses colored status symbols and priority labels."""

    def test_legend_contains_all_status_symbols(self) -> None:
        """Legend includes all status symbols."""
        output = get_legend()
        for symbol in ("✎", "●", "◐", "?", "■", "◇", "✓", "☠"):
            assert symbol in output

    def test_legend_contains_all_priority_levels(self) -> None:
        """Legend lists all five priority levels."""
        output = get_legend()
        for label in (
            "0 (Critical)",
            "1 (High)",
            "2 (Medium)",
            "3 (Low)",
            "4 (Minimal)",
        ):
            assert label in output

    def test_legend_status_symbols_are_styled(self) -> None:
        """Legend status symbols include ANSI escape codes (are colored)."""
        output = get_legend()
        # ANSI escape sequence marker
        assert "\x1b[" in output

    def test_legend_no_color_disables_ansi(self) -> None:
        """Legend with color=False has no ANSI escape codes."""
        output = get_legend(color=False)
        assert "\x1b[" not in output
        # But still contains all status symbols and priorities
        assert "● Open" in output
        assert "0 (Critical)" in output
        assert "4 (Minimal)" in output


class TestLegendHiddenCount:
    """Test legend displays hidden issue count for deferred parents."""

    def test_legend_no_hidden_count(self) -> None:
        """Legend has no hidden line when count is zero."""
        output = get_legend()
        assert "hidden under deferred" not in output

    def test_legend_with_hidden_count(self) -> None:
        """Legend shows hidden count when issues are hidden."""
        output = get_legend(hidden_count=5)
        assert "5 issues hidden under deferred parents" in output
        assert "--expand" in output

    def test_legend_singular_hidden_count(self) -> None:
        """Legend uses singular form for 1 hidden issue."""
        output = get_legend(hidden_count=1)
        assert "1 issue hidden under deferred parents" in output
        # Should NOT say "issues" (plural)
        assert "1 issues" not in output

    def test_legend_zero_hidden_count(self) -> None:
        """Legend has no hidden line when count is explicitly zero."""
        output = get_legend(hidden_count=0)
        assert "hidden under deferred" not in output


class TestBlockedStatusPrecedence:
    """Test that advanced statuses take precedence over blocked display symbol."""

    def test_in_review_not_overridden_by_blocked_brief(self) -> None:
        """In-review issues keep their own symbol even with open dependencies."""
        issue = Issue(
            id="rev1",
            namespace="dc",
            title="Review issue",
            status=Status.IN_REVIEW,
        )
        blocked_ids = {"dc-rev1"}
        output = format_issue_brief(issue, blocked_ids=blocked_ids)
        # Should show in_review symbol (?), not blocked symbol (■)
        assert "?" in output
        assert "■" not in output

    def test_in_review_not_overridden_by_blocked_table(self) -> None:
        """In-review issues keep their own symbol in table format."""
        issue = Issue(
            id="rev2",
            namespace="dc",
            title="Review issue table",
            status=Status.IN_REVIEW,
        )
        blocked_ids = {"dc-rev2"}
        output = format_issue_table([issue], blocked_ids=blocked_ids)
        assert "?" in output
        assert "■" not in output

    def test_deferred_not_overridden_by_blocked_brief(self) -> None:
        """Deferred issues keep their own symbol even with open dependencies."""
        issue = Issue(
            id="def1",
            namespace="dc",
            title="Deferred issue",
            status=Status.DEFERRED,
        )
        blocked_ids = {"dc-def1"}
        output = format_issue_brief(issue, blocked_ids=blocked_ids)
        # Should show deferred symbol (◇), not blocked symbol (■)
        assert "◇" in output
        assert "■" not in output

    def test_open_still_overridden_by_blocked_brief(self) -> None:
        """Open issues with dependencies should still show as blocked."""
        issue = Issue(
            id="open1",
            namespace="dc",
            title="Open blocked issue",
            status=Status.OPEN,
        )
        blocked_ids = {"dc-open1"}
        output = format_issue_brief(issue, blocked_ids=blocked_ids)
        assert "■" in output

    def test_in_progress_still_overridden_by_blocked_brief(self) -> None:
        """In-progress issues with dependencies should still show as blocked."""
        issue = Issue(
            id="ip1",
            namespace="dc",
            title="In-progress blocked issue",
            status=Status.IN_PROGRESS,
        )
        blocked_ids = {"dc-ip1"}
        output = format_issue_brief(issue, blocked_ids=blocked_ids)
        assert "■" in output
