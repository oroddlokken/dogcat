# Dogcat - git-backed issue tracking for AI agents (and humans!)

Heavily inspired by [steveyegge/beads](https://github.com/steveyegge/beads).

Beads is great, but it is ever expanding and slowly getting more and more complicated as he is building Kubernetes for Agents.

Dogcat is a simpler, more minimal version that focuses on the core functionality. The goal is to feature freeze and keep the API stable.

It also avoids some complexity by not using a daemon and/or SQL database, and only relying on the `issues.jsonl` file.

## Installation

### Homebrew (macOS/Linux)

```bash
brew install oroddlokken/tap/dogcat
```

This installs `dcat` and handles Python and dependencies automatically via `uv`.

### From source

Install `uv`, then run `./dcat.py`.

## Usage

Run `dcat init` to initialize the program. Then you can run `dcat prime` to see the information an AI agent should use.  
For a guide more suited for humans, run `dcat guide`.

Alternatively, you can run `dcat init --use-existing-folder /home/me/project/.dogcats` to use a shared dogcat database.

**Command cheat sheet**:

| Command | Action |
| --- | --- |
| `dcat create "My first bug" -t bug -p 0` | Create a bug issue, with priority 0 |
| `dcat create b 0 "My first bug"` | Same as above, but using shorthands for type and priority |
| `dcat ready` | List tasks that is not blocked by other tasks |
| `dcat close $id` | Close a task |
| `dcat close $id -reason "Fixed the bug"` | Close a task with reason |
| `dcat show $id` | Show full details about an issue |
| `dcat new` | Interactive TUI for creating a new issue |
| `dcat edit [$id]` | Interactive TUI for editing an issue |

Also take a look at the `Issue tracking` section in [CLAUDE.MD] to see how to integrate this in your agentic workflow.

### Migrating from beads

If you already have a collection of issues in Beads, you can import them in dogcat. In a folder without a `.dogcats` folder run `dogcat import-beads /path/to/project/.beads/issues.jsonl`.

## Screenshots

Compact table view showing tasks with ID, Parent, Type, Priority, and Title columns:
![Table View](static/dcat-list_table.png)

Hierarchical tree view displaying parent-child task relationships:
![Tree View](static/dcat-list_tree.png)

Detailed list view with status indicators and full task information:
![List View](static/dcat-list.png)

Ready view showing unblocked tasks available for work:
![Ready Tasks](static/dcat-ready.png)

Detailed task view with description, acceptance criteria, and metadata:
![Task Details](static/dcat-show-issueid.png)

TUI for creating new issues (`dcat new`):
![New issue](static/dcat-new.png)

TUI for editing issues, select the one you want to edit (`dcat edit`):
![Select issue to edit](static/dcat-edit.png)

TUI for editing issues (`dcat edit $id`):
![Edit issue](static/dcat-edit-id.png)

## Tips & tricks

Personally, I use these aliases:

```bash
alias dcl="dcat list --tree"
alias dct="dcat list --table"

alias dcn="dcat new"
alias dce="dcat edit"
```

## Development

`dogcat` is now in a state where it can be dogfooded. Included is the issues.jsonl file containing the current issues.
