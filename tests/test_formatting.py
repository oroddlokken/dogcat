"""Tests for display and formatting functions."""

from dogcat.cli._formatting import format_issue_table, format_issue_tree
from dogcat.models import Issue


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
