# Merge Coverage Matrix

This doc maps every claim made in `src/dogcat/merge_driver.py` to the
test(s) that exercise it. It exists so the "works fine with git merges
and rebases" promise has a verifiable backing. The source of truth for
claims is the module docstring at the top of `merge_driver.py`; see
[Maintaining this doc](#maintaining-this-doc) before editing either.

Status is one of three values:

- `green` — the claim is fully covered by the listed test(s).
- `partial` — covered with a stated caveat, spelled out in the cell.
- `gap` — not covered. A `gap` row must carry the id of an open issue.

## Issues (LWW by status finality, then `updated_at`)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Idempotent: merging a record set with itself returns the same set | `tests/test_merge_properties.py::TestMergeIdempotency::test_issue_idempotency` | green |
| Deterministic: fixed `ours`/`theirs` produce the same result | `tests/test_merge_driver.py::TestMergeJSONL::test_same_issue_latest_wins`, `tests/test_merge_driver.py::TestMergeJSONL::test_equal_timestamps_converge_across_argument_order` | green |
| Convergent across argument order (effectively-CRDT) | `tests/test_merge_properties.py::TestMergeConvergence::test_issue_convergence`, `tests/test_merge_driver.py::TestMergeJSONL::test_equal_timestamps_converge_across_argument_order`, `tests/test_merge_driver.py::TestMergeJSONL::test_equal_timestamp_proposals_converge_across_argument_order` | green — the claim was false until dogcat-1xgi: the `new_ts >= old_ts` tie-break resolved an equal-timestamp tie by arrival order, so the two argument orders disagreed. It now breaks ties on a canonical serialization of the records. The property test was vacuous here too — its generator varied only `id` and `updated_at`, so a collision produced byte-identical records; it now varies `title` and fails against the old rule |
| Monotonic within a status rank: later edit wins, never resurrected (cross-rank finality covered by the two rows below) | `tests/test_merge_properties.py::TestMergeMonotonicityUpdatedAt::test_updated_at_monotonic_wins_later`, `tests/test_merge_properties.py::TestMergeMonotonicityUpdatedAt::test_updated_at_monotonic_ours_wins_later` | green |
| Issue tombstone is preserved even when the other side has a later open edit | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_tombstone_wins_over_later_open_edit` | green |
| Issue `closed` wins over a later `open` edit on the other side | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_closed_wins_over_later_open_edit` | green |
| Same status → falls back to `updated_at` | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_same_status_falls_back_to_updated_at` | green |
| Cross-timezone: absolute later timestamp wins | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_cross_timezone_picks_absolute_later`, `tests/test_merge_driver.py::TestMergeJSONL::test_issue_pdt_vs_utc_picks_absolute_later` | green |
| `Z` vs `+00:00` offsets treated equal | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_z_vs_offset_zero_treated_equal` | green |
| `draft` ranks below every active status (`_ISSUE_STATUS_RANK`, `merge_driver.py:309-318`) | `tests/test_merge_driver.py::TestMergeJSONL::test_draft_loses_to_every_active_status` | green |
| The five active statuses (`open`, `in_progress`, `in_review`, `blocked`, `deferred`) share rank 1, so any two of them fall through to `updated_at` | `tests/test_merge_driver.py::TestMergeJSONL::test_active_statuses_share_a_rank_and_fall_through_to_timestamp` | green |

## Proposals (LWW by status finality, then `updated_at`)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Status order: `open < closed < tombstone`; more final status wins | `tests/test_merge_driver.py::TestMergeJSONL::test_same_proposal_more_final_status_wins` | green |
| Tombstone is absorbing: cannot be undone by concurrent edit | `tests/test_merge_driver.py::TestMergeJSONL::test_same_proposal_tombstone_wins_over_closed`, `tests/test_inbox_merge.py::TestInboxMergeEdgeCases::test_close_vs_delete_same_proposal` | green |
| Same status rank → falls back to `updated_at`, then `created_at` | `tests/test_merge_driver.py::TestMergeJSONL::test_same_proposal_same_status_later_created_at_wins` | green |
| Idempotent: same proposal set merged with itself stays unchanged | `tests/test_merge_properties.py::TestMergeIdempotency::test_proposal_idempotency` | green |
| Status finality monotonic across all status tuples | `tests/test_merge_properties.py::TestProposalStatusFinality::test_proposal_finality_monotonic` | green |
| Proposals are not silently dropped during merge | `tests/test_merge_driver.py::TestMergeJSONL::test_proposals_not_dropped_during_merge` | green |
| Concurrent close on both sides collapses to one closed record | `tests/test_inbox_merge.py::TestInboxMergeEdgeCases::test_concurrent_close_same_proposal` | green |

## Dependencies and Links (three-way merge)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Delete on either side wins over no-op on the other (deps) | `tests/test_merge_driver.py::TestMergeJSONL::test_dep_deleted_by_theirs_stays_deleted`, `tests/test_merge_driver.py::TestMergeJSONL::test_dep_deleted_by_ours_stays_deleted`, `tests/test_merge_driver.py::TestMergeJSONL::test_dep_deleted_by_both_stays_deleted` | green |
| Delete on either side wins over no-op on the other (links) | `tests/test_merge_driver.py::TestMergeJSONL::test_link_deleted_by_theirs_stays_deleted` | green |
| Add by one side, not in base, is kept (deps) | `tests/test_merge_driver.py::TestMergeJSONL::test_dep_added_by_ours_not_in_base_kept` | green |
| Add by one side, not in base, is kept (links) | `tests/test_merge_driver.py::TestMergeJSONL::test_link_added_by_theirs_not_in_base_kept` | green |
| Re-add wins over a stale delete on the other side | `tests/test_merge_properties.py::TestReAddWinsOverDelete::test_readd_issue_wins_over_stale_delete` | green |
| Explicit `op=remove` records are honored (deps) | `tests/test_merge_driver.py::TestMergeJSONL::test_dep_with_remove_record_in_theirs` | green |
| Both sides agreeing on identity collapse to one row | `tests/test_merge_driver.py::TestMergeJSONL::test_deps_union`, `tests/test_merge_driver.py::TestMergeJSONL::test_deps_deduplicated` | green |

## Events (union, deduplicated)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Two events with the same identity tuple collapse to one | `tests/test_merge_driver.py::TestMergeJSONL::test_events_deduplicated`, `tests/test_merge_driver.py::TestEventDedupKey::test_identical_events_still_deduped` | green |
| Same timestamp + different changes are both kept | `tests/test_merge_driver.py::TestEventDedupKey::test_same_timestamp_different_changes_kept` | green |
| Strictly grow-only: events are never removed by merge | `tests/test_merge_driver.py::TestMergeJSONL::test_events_union` | green |
| Idempotent on the event log | `tests/test_merge_properties.py::TestMergeIdempotency::test_event_idempotency` | green |

## Cross-cutting invariants

| Claim | Test(s) | Status |
| --- | --- | --- |
| No data loss for additive edits (issues) | `tests/test_merge_properties.py::TestNoDataLossForAdditive::test_additive_issue_preserved` | green |
| No data loss for additive edits (proposals) | `tests/test_merge_properties.py::TestNoDataLossForAdditive::test_additive_proposal_preserved` | green |
| Deletes win against silence (issues) | `tests/test_merge_properties.py::TestDeletionWinsOverSilence::test_delete_issue_wins_over_no_op` | green |
| Last-line-wins is bounded by base: concurrent dep/link adds and deletes resolve via the three-way comparison, not by timestamp | `tests/test_merge_driver.py::TestMergeJSONL::test_dep_deleted_by_theirs_stays_deleted`, `tests/test_merge_properties.py::TestReAddWinsOverDelete::test_readd_issue_wins_over_stale_delete` | partial (transitive — dep/link records have no timestamp tiebreak path) |
| Empty inputs handled cleanly | `tests/test_merge_driver.py::TestMergeJSONL::test_empty_inputs`, `tests/test_merge_edge_cases.py` | green |
| Mixed record types in one merge invocation | `tests/test_merge_driver.py::TestMergeJSONL::test_mixed_records`, `tests/test_merge_driver.py::TestMergeDriverIntegration::test_mixed_record_types_resolve` | green |

## Scope notes (limitations)

| Limitation | Test(s) | Status |
| --- | --- | --- |
| Whole-record LWW: same-issue edits to different fields drop the older writer | `tests/test_validate.py::TestDetectConcurrentEdits::test_detects_field_level_loss_different_fields` | partial (the detector surfaces the loss; the merge itself still drops the older writer) |
| Doctor `--post-merge` names the affected fields in CLI output | `tests/test_validate.py::TestDoctorPostMerge::test_post_merge_detects_edits` | green |
| Octopus merges are not supported (git's strategy bypasses per-file drivers) | `tests/test_git_workflows.py::TestMultipleMerges::test_octopus_merge_aborts_use_sequential` | green |
| `.dogcats/archive/*.jsonl` gets the merge driver | `tests/test_git_commands.py::TestGitSetup::test_setup_covers_archive_subdirectory` | green — the pattern was `.dogcats/*.jsonl`, and a gitattributes glob without `**` does not cross a directory separator, so archive files merged with git's default text driver. Widened to `.dogcats/**/*.jsonl`; `dcat git rebase` now uses `rglob` to match (dogcat-1xgi) |

## End-to-end git workflow coverage

| Scenario | Test(s) | Status |
| --- | --- | --- |
| Standard 3-way merge via the driver | `tests/test_merge_driver.py::TestMergeDriverIntegration::test_non_overlapping_adds_resolve`, `tests/test_merge_driver.py::TestMergeDriverIntegration::test_same_issue_edits_resolve` | green |
| Sequential merge of three branches | `tests/test_git_workflows.py::TestMultipleMerges::test_sequential_merges_three_branches` | green |
| Cherry-pick of an issue-creating commit | `tests/test_git_workflows.py::TestCherryPick::test_cherry_pick_single_issue_create` | green |
| Squash merge with multiple edits | `tests/test_git_workflows.py::TestSquashMerge::test_squash_merge_multiple_edits` | green |
| Revert of a merge commit (`git revert -m 1`) | `tests/test_git_workflows.py::TestRevertMerge::test_revert_merge_creates_revert_commit`, `tests/test_git_workflows.py::TestRevertMerge::test_revert_then_remerge_with_new_commits`, `tests/test_git_workflows.py::TestRevertMerge::test_revert_fast_forward_merge` | green |
| Pull/rebase variants | `tests/test_pull_variants.py` | green |
| Force-push + collaborator pull-rebase recovery | `tests/test_git_force_push.py` | green |
| GitHub server-side merge strategies (squash, rebase, merge commit) | `tests/test_git_server_merge_strategies.py` | green |
| Multi-developer simulation | `tests/test_multidev_workflows.py` | green |
| Manual conflict resolution + doctor detection | `tests/test_manual_conflict_recovery.py` | green |
| Edge cases: unrelated histories, empty files, only-shared records | `tests/test_merge_edge_cases.py` | green |
| Long-divergence and scale stress | `tests/test_merge_scale.py` | green |
| Concurrent compaction race | `tests/test_compaction_merge.py` | green |
| Shallow / sparse / partial clones | `tests/test_git_clones.py` | green |
| Fresh clone without merge driver: `dcat git check` names fix | `tests/test_git_clones.py::TestFreshCloneWithoutMergeDriver` | green |
| `git stash` / `pop` / `apply` with pending .dogcats changes | `tests/test_git_stash.py` | green |
| `git bisect`: detached HEAD and rapid checkouts | `tests/test_git_bisect.py` | green |
| Linked worktree scenarios | `tests/test_git_worktrees.py::TestLinkedWorktrees::test_worktree_main_and_branch_share_dogcats`, `tests/test_git_worktrees.py::TestLinkedWorktrees::test_worktree_detached_head` | green |
| Inbox proposal merge edge cases (local) | `tests/test_inbox_merge.py` | partial — local close/delete/create merge paths; accept/reject need a configured remote inbox and are out of scope here (covered by `tests/test_cmd_inbox.py`, `tests/test_merge_driver.py`) |

## Maintaining this doc

When you edit the module docstring in `src/dogcat/merge_driver.py`, or add a
merge-driver test, do all three in the same change:

1. Add or update the row naming the claim and the test node ids that exercise it.
   A new test for an existing claim belongs in that claim's Test(s) cell — the
   matrix maps claims *and* their tests.
2. If a row would be **gap**, ask the user whether to file an issue (AGENTS.md
   requires that confirmation before any `dcat create`), then put the id in the
   Status column. A **gap** row with no id reads as coverage that does not exist.
3. Run every node id you touched and confirm it passes:
   `uv run pytest "<node id>"`. Node ids here must be class-qualified, because
   nearly every test is a method on a `Test*` class and a bare
   `file.py::test_name` fails to collect. Paste the ids into
   `uv run pytest --collect-only -q` to confirm they resolve.

Mark a row **green** because you ran the test, not because the named test exists.

If the docstring and the tests disagree, the docstring states intent and the
tests record behavior. Report both readings to the user and ask which to change
before editing either: the mismatch is a merge-algebra bug when the tests are
wrong and a stale promise when the docstring is, and the two fixes are not
interchangeable.
