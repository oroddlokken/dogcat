"""The ``--branch`` option: run a mutating command against another branch's store.

``with_branch`` adds ``--branch <name>`` to a command. When given, the command
body runs inside :func:`dogcat.branch_store.branch_store`, so ``get_storage``
hands it a scratch copy of the target branch's issues, and whatever it writes
is committed onto that branch afterwards (dogcat-1fvb).
"""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any, get_type_hints

import typer

from ._completions import complete_branches
from ._helpers import find_dogcats_dir, resolve_dogcats_dir
from ._json_state import echo_error

if TYPE_CHECKING:
    from collections.abc import Callable

_BRANCH_HELP = (
    "Write to this local branch's issues instead of the current checkout's,"
    " as a new commit on that branch. Nothing is pushed."
)


def with_branch(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate a Typer command with a ``--branch`` option.

    The decorated command must take ``dogcats_dir`` and get its storage from
    ``get_storage``. Apply it below ``with_ns_shim``; it builds its signature
    the same way, for the reason given there.
    """
    sig = inspect.signature(func, eval_str=True)
    branch_param = inspect.Parameter(
        "branch",
        inspect.Parameter.KEYWORD_ONLY,
        default=typer.Option(
            None,
            "--branch",
            help=_BRANCH_HELP,
            autocompletion=complete_branches,
        ),
        annotation="str | None",
    )
    # Typer fills a typer.Context parameter itself; it carries the invoked
    # name (create / c / add) for the commit subject. click's own
    # get_current_context can't see it: Typer runs on a vendored click.
    ctx_param = inspect.Parameter(
        "branch_ctx", inspect.Parameter.KEYWORD_ONLY, annotation=typer.Context
    )

    @functools.wraps(func)
    def wrapper(**kwargs: Any) -> Any:
        branch = kwargs.pop("branch", None)
        # Absent when one command calls another directly (remove -> delete).
        ctx: typer.Context | None = kwargs.pop("branch_ctx", None)
        if branch is None:
            return func(**kwargs)

        from dogcat.branch_store import BranchWriteError, branch_store

        dogcats_dir = kwargs.get("dogcats_dir", ".dogcats")
        resolved = (
            find_dogcats_dir()
            if dogcats_dir == ".dogcats"
            else resolve_dogcats_dir(dogcats_dir)
        )
        command = (ctx.info_name if ctx is not None else None) or func.__name__
        try:
            with branch_store(resolved, branch, command=command) as write:
                # Config reads (namespace, for one) follow dogcats_dir, so
                # point it at the scratch copy: the issue is minted as the
                # target branch would mint it.
                if "dogcats_dir" in kwargs:
                    kwargs["dogcats_dir"] = str(write.storage.dogcats_dir)
                result = func(**kwargs)
        except BranchWriteError as e:
            echo_error(str(e))
            raise typer.Exit(1) from e
        if write.commit is not None:
            typer.echo(
                f"✓ Committed to {branch} as {write.commit[:12]} (not pushed)",
                err=True,
            )
        else:
            typer.echo(f"Nothing changed on {branch}; no commit made", err=True)
        return result

    wrapper.__signature__ = sig.replace(  # type: ignore[attr-defined]
        parameters=[*sig.parameters.values(), branch_param, ctx_param]
    )
    wrapper.__annotations__ = {
        **get_type_hints(func, include_extras=True),
        "branch": "str | None",
        "branch_ctx": typer.Context,
    }
    return wrapper
