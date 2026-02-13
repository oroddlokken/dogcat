"""Tests for display and formatting functions."""

from dogcat.cli._formatting import (
    format_issue_brief,
    format_issue_full,
    format_issue_table,
    format_issue_tree,
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
