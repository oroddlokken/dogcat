# Releasing

Releasing is the user's call. Read this before running anything in it.

## `just release-prep` is irreversible past the PR merge

`just release-prep <version>` runs the lint and test suites, stamps `CHANGELOG.md`, resets an
existing `release/v<version>` branch to `main`, force-pushes it with lease, pushes a
`vX.Y.Z-rc.N` tag that fires `.github/workflows/release.yml`, and opens a pull request.

Merging that pull request fires `.github/workflows/publish.yml`: it tags `vX.Y.Z`, uploads the wheel
and sdist to PyPI, creates the GitHub release, and pushes a formula commit to the
`oroddlokken/homebrew-tap` repo. A PyPI version number can never be reused, so the merge cannot be
undone by reverting.

Run `just release-prep` only when the user names a version and asks for a release, and leave the
merge to the user. `just next` reports the candidate versions and changes nothing, so use it when
the user asks what would ship.

The branch name is load-bearing. `publish.yml` fires only for merged pull requests whose head branch
starts with `release/v`; landing the same commits any other way skips publishing entirely.

## Homebrew formula

`publish.yml` and `release.yml` rewrite the `url` and `sha256` fields in `Formula/dogcat.rb` and
`Formula/dogcatwindowbed.rb` in the tap repo and push the commit, so version bumps need no hand
edit and a manual one gets overwritten by the next release.

Hand edits cover only structural changes: a new runtime dependency, a changed entry point, or a
changed command structure. Wait for user confirmation before making one, and tell the user when a
CLI change requires it.

The formula lives in a separate repo. Confirm the path before editing rather than assuming a
sibling checkout exists — more than one nearby directory can look like the tap.
