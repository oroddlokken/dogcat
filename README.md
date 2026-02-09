# Dogcat - lightweight, file-based issue tracking and memory upgrade for AI agents (and humans!)

`dogcat` is a memory upgrade for AI agents. You no longer need to keep track of Markdown files when developing new features or letting the agent waste precious context on progress. With a simple command line utility (and some TUI niceties!) you can create, edit, manage and display issues.

- [Installation](#installation)
- [Usage](#usage)
  - [Telling your agent to use dogcat](#telling-your-agent-to-use-dogcat)
  - [Command cheat sheet](#command-cheat-sheet)
- [Screenshots](#screenshots)
- [Tips & tricks](#tips--tricks)
- [FAQ](#faq)

## Relation to Beads

Heavily inspired by [steveyegge/beads](https://github.com/steveyegge/beads).

Beads is great, but it is ever expanding and slowly getting more and more complicated as he is building Kubernetes for Agents.

Dogcat is a simpler, more minimal version that focuses on the core functionality. The goal is to keep it simple and not chase orchestration of tens of agents running at the same time.

It also avoids some complexity by not using a daemon and/or SQL database, and only relying on the `issues.jsonl` file.

## Installation

### Homebrew (macOS)

```bash
brew install oroddlokken/tap/dogcat
```

This installs `dcat`/`dogcat` and handles Python and dependencies automatically via `uv`.

### From source

Install `uv`, then run `./dcat.py`.

### Using uvx

By installing [uv](https://docs.astral.sh/uv/) and adding `alias dcat="uvx -p 3.13 --from git+https://github.com/oroddlokken/dogcat dcat"` to your `~/.zshrc` or `~/.bashrc` you can run it without installing it.

### Other platforms

I hope to have something better in place soon that doesnt require on uv!

## Usage

Run `dcat init` to initialize the program. Then you can run `dcat prime` to see the information an AI agent should use.  
For a guide more suited for humans, run `dcat guide`.

Alternatively, you can run `dcat init --use-existing-folder /home/me/project/.dogcats` to use a shared dogcat database.

### Telling your agent to use dogcat

In your `AGENTS.md`/`CLAUDE.md` file, add something like the following:

``````text
# Agent Instructions

## Issue tracking

This project uses **dcat** for issue tracking and **git** for version control. You MUST run `dcat prime` for instructions.
Then run `dcat list --agent-only` to see the list of issues. Generally we work on bugs first, and always on high priority issues first.

ALWAYS run `dcat update --status in_progress $issueId` when you start working on an issue.

It is okay to work on multiple issues at the same time - just mark all of them as in_progress, and ask the user which one to prioritize if there is a conflict.

If the user brings up a new bug, feature or anything else that warrants changes to the code, ALWAYS ask if we should create an issue for it before you start working on the code.

### Closing Issues - IMPORTANT

NEVER close issues without explicit user approval. When work is complete:

1. Set status to `in_review`: `dcat update --status in_review $issueId`
2. Ask the user to test
3. Ask if we can close it: "Can I close issue [id] '[title]'?"
4. Only run `dcat close` after user confirms
``````

This is only a starting point and how I use it, it's up to you to decide how dogcat fits best in your workflow!  
There is also a `--no-agent` option that can be passed to `dcat list` that will make your agent skip issues marked as requiring manual intervention.

### Command cheat sheet

| Command | Action |
| --- | --- |
| `dcat create "My first bug" -t bug -p 0` | Create a bug issue, with priority 0 |
| `dcat create b 0 "My first bug"` | Same as above, but using shorthands for type and priority |
| `dcat create "Turn off the lights" --manual` | Indicate to the agent that this is a manual issue, and should be done by the user, not the agent |
| `dcat ready` | List issues that is not blocked by other issues |
| `dcat close $id` | Close an issue |
| `dcat close $id -reason "Fixed the bug"` | Close an issue with reason |
| `dcat show $id` | Show full details about an issue |
| `dcat new` | Interactive TUI for creating a new issue |
| `dcat edit [$id]` | Interactive TUI for editing an issue |
| `dcat in-progress` | List issues currently in progress |
| `dcat in-review` | List issues currently in review |
| `dcat pr` | List issues currently in progress and in progress |
| `dcat recently-added` | List recently added issues |

## Screenshots

Compact table view showing tasissuesks with ID, Parent, Type, Priority, and Title columns:  
![Table View](static/dcat-list_table.png)

Hierarchical tree view displaying parent-child issue relationships:  
![Tree View](static/dcat-list_tree.png)

Detailed list view with status indicators and full issue information:  
![List View](static/dcat-list.png)

Ready view showing unblocked issues available for work:  
![Ready issues](static/dcat-ready.png)

Detailed issue view with description, acceptance criteria, and metadata:  
![Issue Details](static/dcat-show-issueid.png)

TUI for creating new issues (`dcat new`):  
![New issue](static/dcat-new.png)

TUI for editing issues, select the one you want to edit (`dcat edit`):  
![Select issue to edit](static/dcat-edit.png)

TUI for editing issues (`dcat edit $id`):  
![Edit issue](static/dcat-edit-id.png)

List issues in progress:  
![Issues in progress](static/dcat-in-progress.png)

List issues in review:  
![Issues in review](static/dcat-in-review.png)

## Tips & tricks

Personally, I use these aliases:

```bash
alias dcl="dcat list --tree"
alias dct="dcat list --table"

alias dcn="dcat new"
alias dce="dcat edit"
```

## FAQ

**What's a dogcat?**  
¯\_(ツ)_/¯ Some cats are dog-like, and some dogs are cat-like.

**Why a new project and just not use or fork beads?**  
Dogcat started out as some tooling on top of beads, that quickly grew into its own separate project. I found it tricky to integrate against beads, and instead of trying to keep up with changes in beads, it was more fun to just build my own.

**Why Python?**  
I wanted to use [Textual](https://textual.textualize.io/), which is awesome for making TUIs with. It's also the language I am the most familiar with.

## Migrating from beads

If you already have a collection of issues in Beads, you can import them in dogcat. In a folder without a `.dogcats` folder run `dogcat import-beads /path/to/project/.beads/issues.jsonl`.

## Development

`dogcat` is now in a state where it can be dogfooded. Included is the issues.jsonl file containing the current issues.
