# Releasing

Releasing is the user's call. Read this before running anything in it.

## `just release-prep` is irreversible past the PR merge

`just release-prep <version>` runs the lint and test suites, stamps `CHANGELOG.md`, resets an
existing `release/v<version>` branch to `main`, force-pushes it with lease, pushes a
`vX.Y.Z-rc.N` tag that fires `.github/workflows/release.yml`, and opens a pull request. An existing
branch counts whether or not the clone has it — a remote-only branch is fetched, because branching
off `main` instead forks a sibling commit no push can fast-forward.

The tag goes out only after the branch push lands, and a rejected push deletes the local tag and
stops. Both are there because one `push --tags` published `v0.14.2-rc.2` on a commit no branch
reached (dogcat-43d6).

Merging that pull request fires `.github/workflows/publish.yml`: it tags `vX.Y.Z`, uploads the wheel
and sdist to PyPI, creates the GitHub release, and pushes a formula commit to the
`oroddlokken/homebrew-tap` repo. A PyPI version number can never be reused, so the merge cannot be
undone by reverting.

Run `just release-prep` only when the user names a version and asks for a release, and leave the
merge to the user. `just next` reports the candidate versions and changes nothing, so use it when
the user asks what would ship.

The branch name is load-bearing. `publish.yml` fires only for merged pull requests whose head branch
starts with `release/v`; landing the same commits any other way skips publishing entirely.

`publish.yml` and `ci.yml` both run `just lint-all`, and each sets up its own toolchain — uv, Python,
pnpm and the node deps. A step added to one has to be added to the other, or the failure surfaces
only at release time, when the merge has already landed on `main` (dogcat-11yx).

## `just check-sdist` guards what reaches PyPI

`scripts/check-sdist` fails when the source distribution exceeds 1 MiB or holds a top-level entry
outside its allowlist. `pyproject.toml`'s `[tool.hatch.build.targets.sdist]` include-list is what
keeps the tarball to `src/`, `docs/` and four files; the script is the alarm for that section being
loosened, which nothing else catches until the release is already published (dogcat-sin0).

The entry check earns its place beside the size one. hatchling reads the root `.gitignore` alone, so
a directory a tool gitignores from inside itself stays invisible to `git status` and still ships —
`.hypothesis/` rode along in 21 releases that way, and `.pytest_cache/` caches identically. When the
script rejects a directory that belongs in the sdist, add it to the include-list and to `ALLOWED` in the
script; when it rejects a cache, gitignore it at the repo root, which is the copy hatchling reads.

It runs three times, and the placements are deliberate. `ci.yml` runs it on every pull request, which
is where a loosened include-list should be caught. `publish.yml` runs it **before** the tag push,
because that push is the first irreversible step and a guard firing after it would strand `vX.Y.Z` on
origin with no release behind it. `publish-pypi` runs it once more against its own build, which is
the only check standing over the exact bytes PyPI receives.

## Homebrew formula

`publish.yml` and `release.yml` rewrite the `url` and `sha256` fields in `Formula/dogcat.rb` and
`Formula/dogcatwindowbed.rb` in the tap repo and push the commit, so version bumps need no hand
edit and a manual one gets overwritten by the next release.

Hand edits cover only structural changes: a new runtime dependency, a changed entry point, or a
changed command structure. Wait for user confirmation before making one, and tell the user when a
CLI change requires it.

The formula lives in a separate repo. Confirm the path before editing rather than assuming a
sibling checkout exists — more than one nearby directory can look like the tap.
