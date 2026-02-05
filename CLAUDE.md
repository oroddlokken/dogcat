# Agent Instructions

## Issue tracking

This project uses **dcat** for issue tracking and **git** for version control. You MUST run `dcat prime` for instructions.
Then run `dcat list` to see the list of issues. Generally we work on bugs first, and always on high priority issues first.

ALWAYS run `dcat update --status in_progress $issueId` when you start working on an issue.

When picking up a child issue, consider whether it can truly be started before the parent is done. Parent-child is organizational, not blocking. If the child genuinely needs the parent to complete first, add an explicit dependency with `dcat dep <child_id> add --depends-on <parent_id>`.

It is okay to work on multiple issues at the same time - just mark all of them as in_progress, and ask the user which one to prioritize if there is a conflict.

If the user brings up a new bug, feature or anything else that warrants changes to the code, first ask if we should create an issue for it before you start working on the code.

### Issue Status Workflow

Status progression: `open` → `in_progress` → `in_review` → `closed`

When starting work:

```bash
dcat show $issueId                         # Read full issue details first
dcat update --status in_progress $issueId  # Then mark as in progress
```

When work is complete and ready for user review:

```bash
dcat update --status in_review $issueId
```

If changes are needed after review, set back to in_progress:

```bash
dcat update --status in_progress $issueId
```

### Closing Issues - IMPORTANT

NEVER close issues without explicit user approval. When work is complete:

1. Set status to `in_review`: `dcat update --status in_review $issueId`
2. Ask the user to test
3. Ask if we can close it: "Can I close issue [id] '[title]'?"
4. Only run `dcat close` after user confirms

## Constants

`src/dogcat/constants.py` is the single source of truth for shared values used by dogcat (CLI):

Import from this module rather than hardcoding values in multiple places.

## Development

Remember to run "$PROJECT_FOLDER/.venv/bin/activate &&" before running any commands that runs Python. This is to ensure the virtual environment is loaded and all dependencies are installed.

Run `just fmt-all` every now and then to format all the files

Always write tests for new features or when change functionality

## Rules

**NEVER** run any git operations on the .dogcats folder.
