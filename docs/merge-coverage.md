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

A row that once shipped broken points at a numbered entry under
[History](#history) rather than telling the story in the cell.

## Issues (LWW by status finality, then `updated_at`)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Idempotent: merging a record set with itself returns the same set | `tests/test_merge_properties.py::TestMergeIdempotency::test_issue_idempotency` | green |
| Deterministic: fixed `ours`/`theirs` produce the same result | `tests/test_merge_driver.py::TestMergeJSONL::test_same_issue_latest_wins`, `tests/test_merge_driver.py::TestMergeJSONL::test_equal_timestamps_converge_across_argument_order` | green |
| Convergent across argument order, issues and proposals (the whole-file claim is the cross-cutting row below) | `tests/test_merge_properties.py::TestMergeConvergence::test_issue_convergence`, `tests/test_merge_driver.py::TestMergeJSONL::test_equal_timestamps_converge_across_argument_order`, `tests/test_merge_driver.py::TestMergeJSONL::test_equal_timestamp_proposals_converge_across_argument_order` | green (History 1) |
| Monotonic within a status rank: later edit wins, never resurrected (cross-rank finality covered by the two rows below) | `tests/test_merge_properties.py::TestMergeMonotonicityUpdatedAt::test_updated_at_monotonic_wins_later`, `tests/test_merge_properties.py::TestMergeMonotonicityUpdatedAt::test_updated_at_monotonic_ours_wins_later` | green |
| Issue tombstone is preserved even when the other side has a later open edit | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_tombstone_wins_over_later_open_edit` | green |
| Issue `closed` wins over a later `open` edit on the other side | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_closed_wins_over_later_open_edit` | green |
| Same status → falls back to `updated_at` | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_same_status_falls_back_to_updated_at` | green |
| Cross-timezone: absolute later timestamp wins | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_cross_timezone_picks_absolute_later`, `tests/test_merge_driver.py::TestMergeJSONL::test_issue_pdt_vs_utc_picks_absolute_later` | green |
| `Z` vs `+00:00` offsets treated equal | `tests/test_merge_driver.py::TestMergeJSONL::test_issue_z_vs_offset_zero_treated_equal` | green |
| `draft` ranks below every active status (`_ISSUE_STATUS_RANK` in `merge_driver.py`) | `tests/test_merge_driver.py::TestMergeJSONL::test_draft_loses_to_every_active_status` | green |
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
| The collapsed row is picked by canonical content, so concurrent adds differing only in `created_at`/`created_by` resolve the same way in both merge directions | `tests/test_merge_driver.py::TestDependencyLinkConvergence::test_dep_added_on_both_sides_keeps_the_same_record_either_way`, `tests/test_merge_driver.py::TestDependencyLinkConvergence::test_link_added_on_both_sides_keeps_the_same_record_either_way` | green (History 5) |
| Convergent across argument order (deps and links), compared as ordered file content rather than as a set | `tests/test_merge_driver.py::TestDependencyLinkConvergence::test_deps_converge_across_argument_order`, `tests/test_merge_driver.py::TestDependencyLinkConvergence::test_links_converge_across_argument_order`, `tests/test_merge_properties.py::TestMergeConvergence::test_dependency_convergence`, `tests/test_merge_properties.py::TestMergeConvergence::test_link_convergence` | green (History 5) |
| Output order is the sorted identity tuple, so the same inputs give byte-identical output from any process | `tests/test_merge_driver.py::TestDependencyLinkConvergence::test_dep_output_order_is_stable_across_processes`, `tests/test_merge_driver.py::TestDependencyLinkConvergence::test_dep_output_order_matches_sorted_identity_tuples` | green (History 5) |
| Sorting and the content tie-break leave the deletion rule and the unknown-kind passthrough alone | `tests/test_merge_driver.py::TestDependencyLinkConvergence::test_deletion_still_wins_over_silence_both_directions`, `tests/test_merge_driver.py::TestDependencyLinkConvergence::test_unknown_records_still_survive_a_dep_merge` | green |

## Events (union, deduplicated)

| Claim | Test(s) | Status |
| --- | --- | --- |
| Two events with the same identity tuple collapse to one | `tests/test_merge_driver.py::TestMergeJSONL::test_events_deduplicated`, `tests/test_merge_driver.py::TestEventDedupKey::test_identical_events_still_deduped` | green |
| Same timestamp + different changes are both kept | `tests/test_merge_driver.py::TestEventDedupKey::test_same_timestamp_different_changes_kept` | green |
| Strictly grow-only: events are never removed by merge | `tests/test_merge_driver.py::TestMergeJSONL::test_events_union` | green |
| Idempotent on the event log | `tests/test_merge_properties.py::TestMergeIdempotency::test_event_idempotency` | green |

## Unknown kinds (union, deduplicated by exact content)

| Claim | Test(s) | Status |
| --- | --- | --- |
| A record whose `record_type` this dcat does not know survives the merge, from either side | `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_record_from_theirs_survives`, `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_record_from_ours_survives`, `tests/test_merge_edge_cases.py::TestMergeEdgeCases::test_unknown_record_types_preserved` | green (History 3) |
| The same unknown record on both sides collapses to one row | `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_record_on_both_sides_appears_once` | green |
| Idempotent: a set containing an unknown record merged with itself is unchanged | `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_record_idempotent` | green |
| Convergent across argument order with unknown records on both sides | `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_records_converge_across_argument_order` | green |
| Never deleted: base is not consulted, so "in base, absent from one side" is not a deletion | `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_record_absent_from_one_side_is_not_deleted` | green |
| Output position: after the events, so the known kinds keep compaction order | `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_records_sort_last_after_events` | green |
| The five known kinds merge identically whether or not an unknown record is present | `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_records_do_not_perturb_known_kinds` | green |
| End-to-end: the record is still in the file both callers overwrite | `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_record_survives_the_merge_driver_command`, `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_record_survives_a_real_git_merge` | green |
| End-to-end: it also survives the *next local write* after the merge — the guarantee is only worth as much as the storage layer's half of it (`JSONLStorage._preserved`, `compact_snapshot(preserved=…)`) | `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_record_survives_merge_then_local_write`, `tests/test_storage.py::TestPreservedUnknownRecords` | green (History 3) |
| End-to-end through the *other* caller: `dcat git rebase` writes the merged list over the file too, so it has to carry the record as well | `tests/test_git_rebase.py::TestGitRebaseThreeWayBase::test_unknown_record_kinds_survive_the_resolve` | green |

## `dcat git rebase` (the second caller of `merge_jsonl`)

The command overwrites each conflicted file with `merge_jsonl`'s output, so
the rows above only hold end-to-end if it feeds the merger the same inputs
git would. What it can and cannot recover is a claim in its own right.

| Claim | Test(s) | Status |
| --- | --- | --- |
| The common ancestor is recovered from index stage 1, so a dependency deletion survives a rebase under git's *default* `merge.conflictStyle` (which writes no `\|\|\|\|\|\|\|` section) | `tests/test_git_rebase.py::TestGitRebaseThreeWayBase::test_dependency_removal_survives_a_real_rebase` | green (History 4) |
| With no ancestor reachable at all, the resolve is a union and says so per file instead of reporting a clean three-way merge | `tests/test_git_rebase.py::TestGitRebaseThreeWayBase::test_warns_when_no_base_is_reachable` | green |
| A `\|\|\|\|\|\|\|` section is still read when git writes one (`diff3`/`zdiff3`) | `tests/test_git_rebase.py::TestParseConflictedJsonl::test_diff3_conflict` | partial (unit-level: the parser is exercised directly, not through a repo configured with `merge.conflictStyle=diff3`) |
| The read-merge-rewrite runs under the store's advisory lock, so a concurrent `dcat` write is not overwritten | `tests/test_git_rebase.py::TestGitRebaseSafety::test_waits_for_the_store_lock` | green |
| A file that vanishes mid-scan is a per-file error, not a traceback that hides what was already staged | `tests/test_git_rebase.py::TestGitRebaseSafety::test_vanished_file_is_reported_not_fatal` | green |
| Exit 0 never coexists with a file still holding conflict markers | `tests/test_git_rebase.py::TestGitRebaseSafety::test_unparseable_conflict_is_reported_not_skipped` | green |

## Cross-cutting invariants

| Claim | Test(s) | Status |
| --- | --- | --- |
| No data loss for additive edits (issues) | `tests/test_merge_properties.py::TestNoDataLossForAdditive::test_additive_issue_preserved` | green |
| No data loss for additive edits (proposals) | `tests/test_merge_properties.py::TestNoDataLossForAdditive::test_additive_proposal_preserved` | green |
| Deletes win against silence (issues) | `tests/test_merge_properties.py::TestDeletionWinsOverSilence::test_delete_issue_wins_over_no_op` | green |
| Last-line-wins is bounded by base: concurrent dep/link adds and deletes resolve via the three-way comparison, not by timestamp | `tests/test_merge_driver.py::TestMergeJSONL::test_dep_deleted_by_theirs_stays_deleted`, `tests/test_merge_properties.py::TestReAddWinsOverDelete::test_readd_issue_wins_over_stale_delete` | partial (transitive — dep/link records have no timestamp tiebreak path) |
| Effectively a CRDT: every kind converges across argument order, so `merge(base, ours, theirs)` and `merge(base, theirs, ours)` agree | `tests/test_merge_properties.py::TestMergeConvergence::test_issue_convergence`, `tests/test_merge_properties.py::TestMergeConvergence::test_dependency_convergence`, `tests/test_merge_properties.py::TestMergeConvergence::test_link_convergence`, `tests/test_merge_driver.py::TestMergeJSONL::test_equal_timestamp_proposals_converge_across_argument_order`, `tests/test_merge_driver.py::TestUnknownRecordKinds::test_unknown_records_converge_across_argument_order` | green (History 1, History 5) |
| One dict reachable as both ours and theirs merges the same as two equal-content copies, which is what makes the per-call `id(record)` tie-break cache sound | `tests/test_merge_driver.py::TestTieBreakMemo::test_aliased_records_merge_like_equal_copies`, `tests/test_merge_driver.py::TestTieBreakMemo::test_cached_key_matches_the_uncached_one` | green |
| Empty inputs handled cleanly | `tests/test_merge_driver.py::TestMergeJSONL::test_empty_inputs`, `tests/test_merge_edge_cases.py` | green |
| Mixed record types in one merge invocation | `tests/test_merge_driver.py::TestMergeJSONL::test_mixed_records`, `tests/test_merge_driver.py::TestMergeDriverIntegration::test_mixed_record_types_resolve` | green |

## Scope notes (limitations)

| Limitation | Test(s) | Status |
| --- | --- | --- |
| Whole-record LWW: same-issue edits to different fields drop the older writer | `tests/test_validate.py::TestDetectConcurrentEdits::test_detects_field_level_loss_different_fields` | partial (the detector surfaces the loss; the merge itself still drops the older writer) |
| Doctor `--post-merge` names the affected fields in CLI output | `tests/test_validate.py::TestDoctorPostMerge::test_post_merge_detects_edits` | green |
| This module and the storage layer break an exact `updated_at` tie differently — canonical serialization here, file position in `JSONLStorage._parse_issue_record`. Documented in both docstrings rather than unified, because no observed producer writes two lines for one id at the same microsecond | `tests/test_merge_driver.py::TestMergeJSONL::test_equal_timestamps_converge_across_argument_order`, `tests/test_lazy_issues.py::TestLazyIssueMap::test_last_write_wins_replay` | partial (each rule is tested on its own; nothing exercises a store that would make them disagree, since nothing produces one) |
| Octopus merges are not supported (git's strategy bypasses per-file drivers) | `tests/test_git_workflows.py::TestMultipleMerges::test_octopus_merge_aborts_use_sequential` | green |
| `.dogcats/archive/*.jsonl` gets the merge driver | `tests/test_git_commands.py::TestGitSetup::test_setup_covers_archive_subdirectory`, `tests/test_git_commands.py::TestArchiveFileMerging::test_conflicted_archive_file_merges_without_markers`, `tests/test_git_commands.py::TestArchiveFileMerging::test_rebase_reaches_an_archive_file` | green (History 2) |
| A `.gitattributes` still carrying the pre-widening narrow pattern is reported by `dcat git check`, and `dcat git setup` replaces it rather than appending beside it | `tests/test_git_commands.py::TestGitCheck::test_check_flags_narrow_only_gitattributes`, `tests/test_git_commands.py::TestGitSetup::test_setup_replaces_narrow_entry_in_place`, `tests/test_git_commands.py::TestGitSetup::test_setup_collapses_an_already_duplicated_entry` | green (History 2) |

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

## History

Rows that shipped broken, kept because the failure mode explains why the
current rule is shaped the way it is.

1. **Convergence across argument order** was false until dogcat-1xgi. The
   `new_ts >= old_ts` tie-break resolved an equal-timestamp tie by arrival
   order, so two collaborators merging the same pair of branches in opposite
   directions got different content. Ties now break on a canonical
   serialization. The property test was vacuous here as well: its generator
   varied only `id` and `updated_at`, so a collision produced byte-identical
   records. It now varies `title`, and fails against the old rule.
2. **Archive files** merged with git's default text driver until dogcat-1xgi.
   The gitattributes pattern was `.dogcats/*.jsonl`, and a glob without `**`
   does not cross a directory separator. Widened to `.dogcats/**/*.jsonl`,
   with `dcat git rebase` switched to `rglob` to match. Neither half had an
   end-to-end test until dogcat-5tc1, and the upgrade path was broken in two
   more ways in between: `dcat git check` tested for the bare substring
   `merge=dcat-jsonl`, so a checkout still on the narrow pattern passed green
   (dogcat-3lnu), and `dcat git setup` guarded on the *new* string, so it
   appended a second entry instead of replacing the old one (dogcat-12v8).
   The check now asks `git check-attr merge` about an archive path, which
   tests the effect rather than the spelling.
3. **Unknown record kinds were erased, not preserved,** until dogcat-68ij.
   `merge_jsonl` assembled its result from the five known kinds only, and both
   callers overwrite the target file with that result — so merging a branch
   written by a newer dcat deleted every record of the new kind, with no
   warning and no conflict. Unknown records now pass through verbatim. Fixing
   the merger alone was not enough and shipped as one change with the storage
   half: `JSONLStorage._load` routed the same records to the issue parser,
   which raised on the missing `title`, so they landed in `_bad_lines`, set
   `_needs_compaction`, and the next `_append` rewrote the file without them.
   A merge-driver claim in this table is therefore only true as far as
   `_persistence.compact_snapshot` re-emits `_preserved`.
4. **`dcat git rebase` reverted dependency and link deletions** until
   dogcat-5cvm. It could only populate `base_records` from a `|||||||`
   section, which git writes under `merge.conflictStyle=diff3`/`zdiff3` and
   not under the default `merge`. On a default configuration the base
   arrived empty, `_merge_three_way` read every row as "added by one side",
   and a `dcat dep X remove --depends-on Y` on the rebased branch came back
   with no warning. The base now comes from index stage 1, which git
   populates for every conflicted path; the command falls back to a union
   *plus a per-file warning* only where no stage 1 exists.
5. **Dependencies and links were the one kind that did not converge** until
   dogcat-4ol3, and the "Convergent across argument order" row above was green
   through all of it because only issues were ever checked. Two defects:
   `_merge_three_way` iterated `set(base) | set(ours) | set(theirs)`, and
   Python randomizes string hashing per process, so the same merge laid the
   same rows out differently on every run — semantically identical stores whose
   merge commits differed byte-for-byte. And a key present on both sides
   resolved to `theirs`, so two branches that both ran `dcat dep A add
   --depends-on B` kept whichever counterparty's `created_at`/`created_by` the
   merge direction happened to favour — the same class of bug dogcat-1xgi fixed
   for issues via `_tie_break_key`, which deps and links never got. The union is
   now sorted and both-sides conflicts resolve on canonical content. The new
   property tests compare the dep/link block as an ordered list, not as a set:
   a set comparison passes against the unsorted union and sees only half the
   bug.

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
