"""Comment command for dogcat CLI."""

from __future__ import annotations

import orjson
import typer

from ._helpers import get_default_operator, get_storage
from ._json_state import echo_error, is_json_output


def register(app: typer.Typer) -> None:
    """Register comment commands."""

    @app.command()
    def comment(
        issue_id: str = typer.Argument(..., help="Issue ID"),
        action: str = typer.Argument(..., help="Action: add, list, or delete"),
        text: str = typer.Option(None, "--text", "-t", help="Comment text (for add)"),
        comment_id: str = typer.Option(
            None,
            "--comment-id",
            "-c",
            help="Comment ID (for delete)",
        ),
        author: str = typer.Option(None, "--by", help="Comment author name"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        dogcats_dir: str = typer.Option(".dogcats", help="Path to .dogcats directory"),
    ) -> None:
        """Manage issue comments.

        Actions:
        - add: Add a comment to an issue
        - list: List all comments for an issue
        - delete: Delete a comment
        """
        try:
            from dogcat.models import Comment

            storage = get_storage(dogcats_dir)
            issue = storage.get(issue_id)

            if not issue:
                echo_error(f"Issue {issue_id} not found")
                raise typer.Exit(1)

            if action == "add":
                if not text:
                    echo_error("--text is required for add action")
                    raise typer.Exit(1)

                # Generate comment ID
                comment_counter = len(issue.comments) + 1
                new_comment_id = f"{issue_id}-c{comment_counter}"

                new_comment = Comment(
                    id=new_comment_id,
                    issue_id=issue.full_id,
                    author=author or get_default_operator(),
                    text=text,
                )

                issue.comments.append(new_comment)
                storage.update(issue_id, {"comments": issue.comments})

                if is_json_output(json_output):
                    from dogcat.models import issue_to_dict

                    typer.echo(orjson.dumps(issue_to_dict(issue)).decode())
                else:
                    typer.echo(f"✓ Added comment {new_comment_id}")

            elif action == "list":
                if is_json_output(json_output):
                    output = [
                        {
                            "id": c.id,
                            "author": c.author,
                            "text": c.text,
                            "created_at": c.created_at.isoformat(),
                        }
                        for c in issue.comments
                    ]
                    typer.echo(orjson.dumps(output).decode())
                else:
                    if not issue.comments:
                        typer.echo("No comments")
                    else:
                        for comment in issue.comments:
                            ts = comment.created_at.isoformat()
                            typer.echo(f"[{comment.id}] {comment.author} ({ts})")
                            typer.echo(f"  {comment.text}")

            elif action == "delete":
                if not comment_id:
                    echo_error("--comment-id is required for delete action")
                    raise typer.Exit(1)

                comment_to_delete = None
                for c in issue.comments:
                    if c.id == comment_id:
                        comment_to_delete = c
                        break

                if not comment_to_delete:
                    echo_error(f"Comment {comment_id} not found")
                    raise typer.Exit(1)

                issue.comments.remove(comment_to_delete)
                storage.update(issue_id, {"comments": issue.comments})

                typer.echo(f"✓ Deleted comment {comment_id}")

            else:
                echo_error(f"Unknown action '{action}'")
                typer.echo("Valid actions: add, list, delete", err=True)
                raise typer.Exit(1)

        except typer.Exit:
            raise
        except Exception as e:
            echo_error(str(e))
            raise typer.Exit(1)
