# Merge Coverage Matrix

This doc maps every claim made in `src/dogcat/merge_driver.py` to the
test(s) that exercise it. It exists so the "works fine with git merges
and rebases" promise has a verifiable backing — if you change the merge
algebra, update both the docstring and this file.

The source of truth for claims is the module docstring at the top of
`src/dogcat/merge_driver.py`. New claims there require a corresponding
row here. Rows marked **gap** must link to an open issue tracking the
missing coverage.

## Issues (LWW by `updated_at`)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Idempotent: merging a record set with itself returns the same set | `tests/test_merge_properties.py::TestMergeIdempotency::test_issue_idempotency` | green |
| Deterministic: fixed `ours`/`theirs` produce the same result | `tests/test_merge_driver.py::TestMergeJSONL::test_same_issue_latest_wins` | green |
| Convergent across argument order (effectively-CRDT) | `tests/test_merge_properties.py::TestMergeConvergence::test_issue_convergence` | green |
| Monotonic in `updated_at`: later edit wins, never resurrected | `tests/test_merge_properties.py::TestMergeMonotonicityUpdatedAt::test_updated_at_monotonic_wins_later`, `test_updated_at_monotonic_ours_wins_later` | green |
| Issue tombstone is preserved even when the other side has a later open edit | `tests/test_merge_driver.py::test_issue_tombstone_wins_over_later_open_edit` | green |
| Issue `closed` wins over a later `open` edit on the other side | `tests/test_merge_driver.py::test_issue_closed_wins_over_later_open_edit` | green |
| Same status → falls back to `updated_at` | `tests/test_merge_driver.py::test_issue_same_status_falls_back_to_updated_at` | green |
| Cross-timezone: absolute later timestamp wins | `tests/test_merge_driver.py::test_issue_cross_timezone_picks_absolute_later`, `test_issue_pdt_vs_utc_picks_absolute_later` | green |
| `Z` vs `+00:00` offsets treated equal | `tests/test_merge_driver.py::test_issue_z_vs_offset_zero_treated_equal` | green |

## Proposals (LWW by status finality, then `updated_at`)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Status order: `open < closed < tombstone`; more final status wins | `tests/test_merge_driver.py::test_same_proposal_more_final_status_wins` | green |
| Tombstone is absorbing: cannot be undone by concurrent edit | `tests/test_merge_driver.py::test_same_proposal_tombstone_wins_over_closed`, `tests/test_inbox_merge.py::test_close_vs_delete_same_proposal` | green |
| Same status rank → falls back to `updated_at`, then `created_at` | `tests/test_merge_driver.py::test_same_proposal_same_status_later_created_at_wins` | green |
| Idempotent: same proposal set merged with itself stays unchanged | `tests/test_merge_properties.py::TestMergeIdempotency::test_proposal_idempotency` | green |
| Status finality monotonic across all status tuples | `tests/test_merge_properties.py::test_proposal_finality_monotonic` | green |
| Proposals are not silently dropped during merge | `tests/test_merge_driver.py::test_proposals_not_dropped_during_merge` | green |
| Concurrent close on both sides collapses to one closed record | `tests/test_inbox_merge.py::test_concurrent_close_same_proposal` | green |

## Dependencies and Links (three-way merge)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Delete on either side wins over no-op on the other (deps) | `tests/test_merge_driver.py::test_dep_deleted_by_theirs_stays_deleted`, `test_dep_deleted_by_ours_stays_deleted`, `test_dep_deleted_by_both_stays_deleted` | green |
| Delete on either side wins over no-op on the other (links) | `tests/test_merge_driver.py::test_link_deleted_by_theirs_stays_deleted` | green |
| Add by one side, not in base, is kept (deps) | `tests/test_merge_driver.py::test_dep_added_by_ours_not_in_base_kept` | green |
| Add by one side, not in base, is kept (links) | `tests/test_merge_driver.py::test_link_added_by_theirs_not_in_base_kept` | green |
| Re-add wins over a stale delete on the other side | `tests/test_merge_properties.py::TestReAddWinsOverDelete::test_readd_issue_wins_over_stale_delete` | green |
| Explicit `op=remove` records are honored (deps) | `tests/test_merge_driver.py::test_dep_with_remove_record_in_theirs` | green |
| Both sides agreeing on identity collapse to one row | `tests/test_merge_driver.py::test_deps_union`, `test_deps_deduplicated` | green |

## Events (union, deduplicated)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Two events with the same identity tuple collapse to one | `tests/test_merge_driver.py::test_events_deduplicated`, `test_identical_events_still_deduped` | green |
| Same timestamp + different changes are both kept | `tests/test_merge_driver.py::TestEventDedupKey::test_same_timestamp_different_changes_kept` | green |
| Strictly grow-only: events are never removed by merge | `tests/test_merge_driver.py::test_events_union` | green |
| Idempotent on the event log | `tests/test_merge_properties.py::test_event_idempotency` | green |

## Cross-cutting invariants

| Claim | Test(s) | Status |
| --- | --- | --- |
| No data loss for additive edits (issues) | `tests/test_merge_properties.py::TestNoDataLossForAdditive::test_additive_issue_preserved` | green |
| No data loss for additive edits (proposals) | `tests/test_merge_properties.py::TestNoDataLossForAdditive::test_additive_proposal_preserved` | green |
| Deletes win against silence (issues) | `tests/test_merge_properties.py::TestDeletionWinsOverSilence::test_delete_issue_wins_over_no_op` | green |
| Empty inputs handled cleanly | `tests/test_merge_driver.py::test_empty_inputs`, `tests/test_merge_edge_cases.py` | green |
| Mixed record types in one merge invocation | `tests/test_merge_driver.py::test_mixed_records`, `test_mixed_record_types_resolve` | green |

## Scope notes (limitations)

| Limitation | Test(s) | Status |
| --- | --- | --- |
| Whole-record LWW: same-issue edits to different fields drop the older writer | `tests/test_validate.py::TestDetectConcurrentEdits::test_detects_field_level_loss_different_fields` | green (detector surfaces it) |
| Doctor `--post-merge` names the affected fields in CLI output | `tests/test_validate.py::TestDoctorPostMerge::test_post_merge_detects_edits` | green |
| Octopus merges are not supported (git's strategy bypasses per-file drivers) | `tests/test_git_workflows.py::TestMultipleMerges::test_octopus_merge_aborts_use_sequential` | green |

## End-to-end git workflow coverage

| Scenario | Test(s) | Status |
| --- | --- | --- |
| Standard 3-way merge via the driver | `tests/test_merge_driver.py::TestMergeDriverIntegration::test_non_overlapping_adds_resolve`, `test_same_issue_edits_resolve` | green |
| Sequential merge of three branches | `tests/test_git_workflows.py::test_sequential_merges_three_branches` | green |
| Cherry-pick of an issue-creating commit | `tests/test_git_workflows.py::TestCherryPick::test_cherry_pick_single_issue_create` | green |
| Squash merge with multiple edits | `tests/test_git_workflows.py::TestSquashMerge::test_squash_merge_multiple_edits` | green |
| Revert of a merge commit (`git revert -m 1`) | `tests/test_git_workflows.py::TestRevertMerge::test_revert_merge_creates_revert_commit`, `test_revert_then_remerge_with_new_commits`, `test_revert_fast_forward_merge` | green |
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
| Linked worktree scenarios | `tests/test_git_worktrees.py` | partial — `test_worktree_branch_isolation` does not actually exercise worktrees; tracked under dogcat-row5 |
| Inbox proposal merge edge cases (local) | `tests/test_inbox_merge.py` | partial — accept/reject scenarios from dogcat-4xu9 require a configured remote inbox; covered as local close/delete/create instead, see dogcat-2832 notes |

## Maintaining this doc

When you change `src/dogcat/merge_driver.py`'s module docstring:

1. Add or update the matching row here.
2. If a row would be **gap**, file an issue and link it in the Status column.
3. Run the linked test to confirm green before pushing.

This doc is the agreement between the merge-driver module docstring
and the test suite. If they ever drift, the docstring is authoritative
for *intent* and the tests are authoritative for *actual behavior* —
fix the gap rather than letting them disagree silently.
