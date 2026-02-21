"""Dependency graph visualization command for dogcat CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import typer

from ._completions import (
    complete_issue_ids,
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_types,
)
from ._formatting import format_issue_brief
from ._helpers import apply_common_filters, get_storage
from ._json_state import echo_error, is_json_output

if TYPE_CHECKING:
    from dogcat.models import Issue
    from dogcat.storage import JSONLStorage


def _collect_subgraph(storage: JSONLStorage, start_id: str) -> set[str]:
    """Collect all issue IDs reachable from *start_id* via deps and parent-child."""
    visited: set[str] = set()
    queue = [start_id]
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)

        issue = storage.get(current)
        if issue is None:
            continue

        # Parent / children
        if issue.parent:
            queue.append(issue.parent)
        queue.extend(child.full_id for child in storage.get_children(current))

        # Blocking deps (both directions)
        queue.extend(dep.depends_on_id for dep in storage.get_dependencies(current))
        queue.extend(dep.issue_id for dep in storage.get_dependents(current))

    return visited


def _render_graph(
    storage: JSONLStorage,
    issues: list[Issue],
) -> str:
    """Render an ASCII dependency graph for the given issues.

    Parent-child edges use ``├── `` / ``└── `` (cyan).
    Blocking edges use ``├─▶ `` / ``└─▶ `` (red).
    Already-visited nodes are shown as ``(ref: <id>)`` to avoid cycles.
    """
    issue_ids = {i.full_id for i in issues}

    # Build adjacency from storage, restricted to the visible set.
    children_map: dict[str, list[str]] = {}  # parent -> children
    blocks_map: dict[str, list[str]] = {}  # blocker -> blocked issues

    for issue in issues:
        # Parent-child
        child_ids = [
            c.full_id
            for c in storage.get_children(issue.full_id)
            if c.full_id in issue_ids
        ]
        if child_ids:
            children_map[issue.full_id] = sorted(child_ids)

        # What this issue blocks (dependents whose dep_type is blocks)
        dependents = storage.get_dependents(issue.full_id)
        blocked_ids = [d.issue_id for d in dependents if d.issue_id in issue_ids]
        if blocked_ids:
            blocks_map[issue.full_id] = sorted(blocked_ids)

    # Identify roots: no incoming blocks edge AND no parent in the visible set.
    has_incoming_block: set[str] = set()
    for blocked_list in blocks_map.values():
        has_incoming_block.update(blocked_list)

    has_parent_in_set: set[str] = set()
    for child_list in children_map.values():
        has_parent_in_set.update(child_list)

    roots = sorted(
        [
            i
            for i in issues
            if i.full_id not in has_incoming_block
            and i.full_id not in has_parent_in_set
        ],
        key=lambda i: (i.priority, i.full_id),
    )

    # If no clear roots (cycle-only graph), fall back to all issues as roots.
    if not roots:
        roots = sorted(issues, key=lambda i: (i.priority, i.full_id))

    issue_by_id = {i.full_id: i for i in issues}
    visited: set[str] = set()
    lines: list[str] = []

    def _walk(node_id: str, prefix: str, connector: str) -> None:
        """DFS walk emitting lines with box-drawing prefixes."""
        line = prefix + connector + format_issue_brief(issue_by_id[node_id])

        if node_id in visited:
            ref = typer.style(f"(ref: {node_id})", fg="bright_black")
            lines.append(prefix + connector + ref)
            return

        lines.append(line)
        visited.add(node_id)

        # Gather child edges and blocking edges from this node.
        child_ids = children_map.get(node_id, [])
        blocked_ids = blocks_map.get(node_id, [])

        edges: list[tuple[str, str]] = [(cid, "child") for cid in child_ids]
        edges.extend((bid, "blocks") for bid in blocked_ids)

        for idx, (target_id, edge_type) in enumerate(edges):
            is_last = idx == len(edges) - 1
            if is_last:
                if edge_type == "blocks":
                    conn = typer.style("└─▶ ", fg="red")
                else:
                    conn = typer.style("└── ", fg="cyan")
                new_prefix = prefix + "    "
            else:
                if edge_type == "blocks":
                    conn = typer.style("├─▶ ", fg="red")
                else:
                    conn = typer.style("├── ", fg="cyan")
                new_prefix = prefix + typer.style("│   ", fg="bright_black")

            _walk(target_id, new_prefix, conn)

    for root in roots:
        if root.full_id in visited:
            continue
        _walk(root.full_id, "", "")

    return "\n".join(lines)


def register(app: typer.Typer) -> None:
    """Register the graph command."""

    @app.command()
    def graph(
        issue_id: str | None = typer.Argument(
            None,
            help="Issue ID to show subgraph for (omit for full graph)",
            autocompletion=complete_issue_ids,
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
        """Show dependency graph as an ASCII diagram."""
        try:
            from dogcat.models import Status, issue_to_dict

            storage = get_storage(dogcats_dir)

            # When a specific issue is requested, scope to its subgraph.
            if issue_id:
                resolved = storage.resolve_id(issue_id)
                if not resolved:
                    echo_error(f"Issue not found: {issue_id}")
                    raise typer.Exit(1)
                subgraph_ids = _collect_subgraph(storage, resolved)
                all_issues = [
                    storage.get(sid)
                    for sid in subgraph_ids
                    if storage.get(sid) is not None
                ]
            else:
                all_issues = storage.list()

            # Exclude tombstones and closed.
            all_issues = [
                i
                for i in all_issues
                if i is not None and i.status not in (Status.TOMBSTONE, Status.CLOSED)
            ]

            # Apply common filters.
            filtered = apply_common_filters(
                all_issues,
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

            # Only keep issues that participate in a relationship.
            filtered_ids = {i.full_id for i in filtered}
            has_relationship: set[str] = set()
            for issue in filtered:
                fid = issue.full_id
                # Has children?
                children = storage.get_children(fid)
                if any(c.full_id in filtered_ids for c in children):
                    has_relationship.add(fid)
                    for c in children:
                        if c.full_id in filtered_ids:
                            has_relationship.add(c.full_id)
                # Has parent in set?
                if issue.parent and issue.parent in filtered_ids:
                    has_relationship.add(fid)
                    has_relationship.add(issue.parent)
                # Has blocking dep?
                for dep in storage.get_dependencies(fid):
                    if dep.depends_on_id in filtered_ids:
                        has_relationship.add(fid)
                        has_relationship.add(dep.depends_on_id)
                for dep in storage.get_dependents(fid):
                    if dep.issue_id in filtered_ids:
                        has_relationship.add(fid)
                        has_relationship.add(dep.issue_id)

            graph_issues = [i for i in filtered if i.full_id in has_relationship]

            if is_json_output(json_output):
                nodes = [issue_to_dict(i) for i in graph_issues]
                edges: list[dict[str, str]] = []
                seen_edges: set[tuple[str, str, str]] = set()
                for issue in graph_issues:
                    fid = issue.full_id
                    for dep in storage.get_dependents(fid):
                        if dep.issue_id in filtered_ids:
                            key = (fid, dep.issue_id, "blocks")
                            if key not in seen_edges:
                                seen_edges.add(key)
                                edges.append(
                                    {
                                        "from": fid,
                                        "to": dep.issue_id,
                                        "type": "blocks",
                                    }
                                )
                    children = storage.get_children(fid)
                    for child in children:
                        if child.full_id in filtered_ids:
                            key = (fid, child.full_id, "parent-child")
                            if key not in seen_edges:
                                seen_edges.add(key)
                                edges.append(
                                    {
                                        "from": fid,
                                        "to": child.full_id,
                                        "type": "parent-child",
                                    }
                                )
                typer.echo(
                    orjson.dumps(
                        {"nodes": nodes, "edges": edges},
                    ).decode()
                )
            elif not graph_issues:
                typer.echo("No dependency graph to display")
            else:
                output = _render_graph(storage, graph_issues)
                typer.echo(output)

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
