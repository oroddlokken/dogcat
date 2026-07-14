"""Shared Typer option aliases for the list-view commands.

The list-style commands (``ready``, ``blocked``, ``open``, ``in-review``,
``in-progress``, ``deferred``, ``snoozed``, ``manual``, ``recently-*``, ``pr``,
and ``list``) repeat the same block of filter and display options across their
signatures. Declaring each one here once — as a :data:`typing.Annotated` alias
carrying the flag names, help text, and autocompletion callback — means adding
or changing a shared filter is a single edit instead of one per command.

Typer resolves these aliases through ``get_type_hints(..., include_extras=True)``
just like an inline ``typer.Option``, so signature introspection, ``--help``
output, and shell completion are unchanged. Callers supply the *default* on the
parameter (``= None`` / ``= False`` / ``= []``); per Typer's Annotated rules the
default must not live inside the ``typer.Option`` call. (dogcat-5bhv)
"""

from __future__ import annotations

from typing import Annotated

import typer

from ._completions import (
    complete_issue_ids,
    complete_labels,
    complete_namespaces,
    complete_owners,
    complete_priorities,
    complete_types,
)

# -- Filters ---------------------------------------------------------------
IssueTypeFilterOpt = Annotated[
    str | None,
    typer.Option("--type", "-t", help="Filter by type", autocompletion=complete_types),
]
ExcludeTypeFilterOpt = Annotated[
    list[str],
    typer.Option(
        "--exclude-type",
        help="Exclude issues of this type (repeatable)",
        autocompletion=complete_types,
    ),
]
PriorityFilterOpt = Annotated[
    int | None,
    typer.Option(
        "--priority",
        "-p",
        help="Filter by priority",
        autocompletion=complete_priorities,
    ),
]
LabelFilterOpt = Annotated[
    str | None,
    typer.Option(
        "--label", "-l", help="Filter by label", autocompletion=complete_labels
    ),
]
OwnerFilterOpt = Annotated[
    str | None,
    typer.Option(
        "--owner", "-o", help="Filter by owner", autocompletion=complete_owners
    ),
]
ParentFilterOpt = Annotated[
    str | None,
    typer.Option(
        "--parent",
        help="Filter by parent issue ID",
        autocompletion=complete_issue_ids,
    ),
]
NoParentOpt = Annotated[
    bool,
    typer.Option("--no-parent", help="Show only top-level issues (no parent)"),
]
NamespaceFilterOpt = Annotated[
    str | None,
    typer.Option(
        "--namespace", help="Filter by namespace", autocompletion=complete_namespaces
    ),
]
AllNamespacesOpt = Annotated[
    bool,
    typer.Option(
        "--all-namespaces", "--all-ns", "-A", help="Show issues from all namespaces"
    ),
]
AgentOnlyOpt = Annotated[
    bool,
    typer.Option("--agent-only", help="Only show issues available for agents"),
]
ManualFilterOpt = Annotated[
    bool,
    typer.Option("--manual", help="Only show issues marked as manual"),
]
HasCommentsOpt = Annotated[
    bool,
    typer.Option(
        "--has-comments", help="Only show issues that have at least one comment"
    ),
]
WithoutCommentsOpt = Annotated[
    bool,
    typer.Option("--without-comments", help="Only show issues that have no comments"),
]

# -- Display ---------------------------------------------------------------
TreeOpt = Annotated[bool, typer.Option("--tree", help="Display as tree")]
TableOpt = Annotated[bool, typer.Option("--table", help="Display in columns")]
