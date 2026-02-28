"""Issue distribution chart command for dogcat CLI."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import orjson
import typer
from rich.console import Console
from rich.text import Text

if TYPE_CHECKING:
    from dogcat.models import Issue
from dogcat.constants import (
    PRIORITY_COLORS,
    STATUS_COLORS,
    STATUS_OPTIONS,
    STATUS_SYMBOLS,
    TYPE_COLORS,
    TYPE_OPTIONS,
)

from ._completions import (
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_types,
)
from ._helpers import apply_common_filters, get_storage
from ._json_state import echo_error, is_json_output

# Ordered keys for each grouping dimension
_STATUS_ORDER = [v for _, v in STATUS_OPTIONS]
_TYPE_ORDER = [v for _, v in TYPE_OPTIONS]
_PRIORITY_ORDER = list(range(5))

_PRIORITY_LABELS: dict[int, str] = {
    0: "P0 Critical",
    1: "P1 High",
    2: "P2 Medium",
    3: "P3 Low",
    4: "P4 Minimal",
}

BLOCK = "\u2588"  # █


def _render_chart(
    counts: dict[str, int],
    order: list[str],
    colors: dict[str, str],
    symbols: dict[str, str] | None,
    total: int,
    title: str,
    *,
    console: Console | None = None,
) -> None:
    """Render horizontal bar chart to the terminal."""
    console = console or Console()

    # Filter to non-zero entries, preserve order
    entries = [(key, counts[key]) for key in order if counts.get(key, 0) > 0]

    if not entries:
        typer.echo(f"{title}: no issues")
        return

    max_count = max(count for _, count in entries)
    max_label = max(len(key) for key, _ in entries)
    max_digits = len(str(max_count))
    # Leave room for: symbol(3) + label + gap(2) + count + gap(1) + bar + gap(1) + pct
    bar_budget = console.width - 3 - max_label - 2 - max_digits - 1 - 1 - 5
    bar_width = max(10, min(bar_budget, 40))

    console.print(f"[bold]{title}[/bold] ({total} issue{'s' if total != 1 else ''})")

    for key, count in entries:
        pct = count / total * 100
        color = colors.get(key, "white")
        filled = max(1, round(count / max_count * bar_width))
        symbol = symbols.get(key, " ") if symbols else " "

        row = Text()
        row.append(f" {symbol} ", style=color)
        row.append(f"{key:<{max_label}}", style=color)
        row.append(f"  {count:>{max_digits}} ", style="bold")
        row.append(BLOCK * filled, style=color)
        row.append(f" {pct:.0f}%", style="dim")
        console.print(row)

    console.print()


_ALL_BY_VALUES = ("status", "type", "priority", "label")


def _chart_data(
    by: str,
    issues: list[Issue],
) -> tuple[dict[str, int], list[str], dict[str, str], dict[str, str] | None, str]:
    """Build chart data for a single grouping dimension."""
    if by == "status":
        counts: dict[str, int] = Counter(i.status.value for i in issues)
        order = [str(k) for k in _STATUS_ORDER]
        return counts, order, STATUS_COLORS, STATUS_SYMBOLS, "Status Distribution"
    if by == "type":
        counts = Counter(i.issue_type.value for i in issues)
        order = [str(k) for k in _TYPE_ORDER]
        return counts, order, TYPE_COLORS, None, "Type Distribution"
    if by == "label":
        label_counter: Counter[str] = Counter()
        for i in issues:
            for lbl in i.labels:
                label_counter[lbl] += 1
        counts = dict(label_counter)
        order = sorted(counts, key=lambda k: (-counts[k], k))
        colors = dict.fromkeys(order, "cyan")
        return counts, order, colors, None, "Label Distribution"
    # priority
    counts = Counter(str(i.priority) for i in issues)
    order = [str(k) for k in _PRIORITY_ORDER]
    colors = {str(k): v for k, v in PRIORITY_COLORS.items()}
    return counts, order, colors, None, "Priority Distribution"


def _complete_by_values(incomplete: str) -> list[tuple[str, str]]:
    """Complete --by values."""
    options = [
        ("status", "Group by issue status"),
        ("type", "Group by issue type"),
        ("priority", "Group by priority level"),
        ("label", "Group by label/tag"),
        ("all", "Show all categories"),
    ]
    return [(v, h) for v, h in options if v.startswith(incomplete)]


def register(app: typer.Typer) -> None:
    """Register chart command."""

    @app.command()
    def chart(
        by: str | None = typer.Option(
            None,
            "--by",
            "-b",
            help="Group by: status, type, priority, label, or all (default: all)",
            autocompletion=_complete_by_values,
        ),
        show_all: bool = typer.Option(
            False,
            "--all",
            "-a",
            help="Include closed and tombstone issues",
        ),
        issue_type: str | None = typer.Option(
            None,
            "--type",
            "-t",
            help="Filter by type",
            autocompletion=complete_types,
        ),
        priority: int | None = typer.Option(
            None,
            "--priority",
            "-p",
            help="Filter by priority",
            autocompletion=complete_priorities,
        ),
        label: str | None = typer.Option(
            None,
            "--label",
            "-l",
            help="Filter by label",
            autocompletion=complete_labels,
        ),
        owner: str | None = typer.Option(
            None,
            "--owner",
            "-o",
            help="Filter by owner",
            autocompletion=complete_owners,
        ),
        namespace: str | None = typer.Option(
            None,
            "--namespace",
            help="Filter by namespace",
            autocompletion=complete_namespaces,
        ),
        all_namespaces: bool = typer.Option(
            False,
            "--all-namespaces",
            "--all-ns",
            "-A",
            help="Show issues from all namespaces",
        ),
        agent_only: bool = typer.Option(
            False,
            "--agent-only",
            help="Only show issues available for agents",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Show issue distribution as a bar chart.

        Displays horizontal bar charts of issues grouped by category.
        With no --by flag, shows all four categories (status, type,
        priority, label). Use --by to show a single category.

        Examples:
            dcat chart                # all four distributions
            dcat chart --by status    # status only
            dcat chart --by type      # type only
            dcat chart --by priority  # priority only
            dcat chart --by label     # label/tag only
            dcat chart --all          # include closed issues
        """
        try:
            categories = _ALL_BY_VALUES if by is None or by == "all" else (by,)

            if by is not None and by != "all" and by not in _ALL_BY_VALUES:
                echo_error(
                    f"Invalid --by value '{by}'. "
                    f"Choose: {', '.join(_ALL_BY_VALUES)}, or all"
                )
                raise typer.Exit(1)

            storage = get_storage(dogcats_dir)
            issues = storage.list()

            if not show_all:
                issues = [
                    i for i in issues if i.status.value not in ("closed", "tombstone")
                ]

            issues = apply_common_filters(
                issues,
                issue_type=issue_type,
                priority=priority,
                label=label,
                owner=owner,
                namespace=namespace,
                all_namespaces=all_namespaces,
                agent_only=agent_only,
                dogcats_dir=str(storage.dogcats_dir),
                storage=storage,
            )

            total = len(issues)

            if is_json_output(json_output):
                results: dict[str, dict[str, int]] = {}
                for cat in categories:
                    counts, order, _, _, _ = _chart_data(cat, issues)
                    results[cat] = {
                        k: counts.get(k, 0) for k in order if counts.get(k, 0) > 0
                    }
                output: dict[str, object] = {
                    "group_by": by or "all",
                    "total": total,
                }
                if len(categories) == 1:
                    output["counts"] = results[categories[0]]
                else:
                    output["counts"] = results
                typer.echo(orjson.dumps(output).decode())
                return

            console = Console()
            for cat in categories:
                counts, order, colors, symbols, title = _chart_data(cat, issues)
                if cat == "priority":
                    display_counts: dict[str, int] = {}
                    display_colors: dict[str, str] = {}
                    display_order: list[str] = []
                    for k in order:
                        if counts.get(k, 0) > 0:
                            label_str = _PRIORITY_LABELS.get(int(k), k)
                            display_counts[label_str] = counts[k]
                            display_colors[label_str] = colors[k]
                            display_order.append(label_str)
                    _render_chart(
                        display_counts,
                        display_order,
                        display_colors,
                        None,
                        total,
                        title,
                        console=console,
                    )
                else:
                    _render_chart(
                        counts, order, colors, symbols, total, title, console=console
                    )

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
