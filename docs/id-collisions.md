# ID collision math

Background for `ID_LENGTH_THRESHOLDS` in `src/dogcat/constants.py` and the length-scaling in
`src/dogcat/idgen.py`. Read this before re-tuning a threshold; nothing here is needed to use the
generator.

## Address space

IDs are base36 strings (alphabet `0-9a-z`), so the space for length L is `N = 36^L`:

| Length L | Address space N |
| --- | --- |
| 4 | 1,679,616 |
| 5 | 60,466,176 |
| 6 | 2,176,782,336 |
| 7 | 78,364,164,096 |

## The two probabilities

Per-generation — the chance a freshly generated hash collides with one of the `k` existing IDs of
the same length. Exact for uniform sampling while `k << N`:

    p_step(k, L) ≈ k / N

Cumulative (birthday paradox) — the chance that *any* collision has been hit over the life of a
database holding `k` IDs, i.e. that at least one `IDGenerator.generate_id` call has retried:

    p_all(k, L) ≈ 1 - exp(-k² / 2N)

`collision_probability` and `cumulative_collision_probability` in `idgen.py` implement these two
formulas respectively.

## Why the thresholds sit where they do

Each band's upper bound was picked to hold `p_all` to a few percent:

| Boundary | L | p_step | p_all |
| --- | --- | --- | --- |
| k ≤ 500 | 4 | ≤ 0.0298% | ≤ 7.17% |
| k ≤ 1500 | 5 | ≤ 0.00248% | ≤ 1.85% |
| k ≤ 5000 | 6 | ≤ 0.000230% | ≤ 0.572% |
| k > 5000 | 7 | decreases | decreases |

The boundaries are empirical, not derived: each transition tightens `p_all` by roughly an order of
magnitude. Re-tuning is safe as long as both adjacent bands keep `p_all` under the target at the
boundary (5% is the working figure).

`dcat doctor --check-id-distribution` reports live `p_step` and `p_all` for the current database.
Use it rather than these tables when judging whether a real store has drifted.
