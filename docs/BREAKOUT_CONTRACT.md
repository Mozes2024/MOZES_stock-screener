# Breakout / VCP producer contract

`score_buy_signal` intentionally produces **raw 0–125** scores. The feed exports
them unchanged as `breakout_score`; `breakout_score_max: 125` is additive metadata.
Do not normalize by 1.25, clip to 100, or change scoring components/thresholds.

The detector's `is_vcp` decision is preserved as a strict boolean
`details.vcp_data.confirmed` in both the confirmed and partial scoring branches.
The exporter sets `vcp_confirmed` and the compatible `has_vcp` field to true only
when that stored confirmation is exactly `True`. `vcp_quality` and `vcp_desc`
remain diagnostics. A nonempty dictionary, high quality, or description never
supplies confirmation. Missing evidence (including old structured pickle scans)
is unknown/unconfirmed and exports false.

## Rollout and rollback

1. Review and merge producer support first, then the matching Ranker consumer PR.
2. Existing structured scans lack confirmation. Confirmed VCP stays disabled
   until a **newly computed full scan**, separately authorized by the owner.
   Re-exporting an old pickle cannot restore it. Do not dispatch scans or publish
   datasets as part of this code change.
3. Ranker accepts finite raw 0–125 scores, requires explicit confirmation plus
   consistent quality, and uses `sp500_data.json` as its only stock-row source.
   Its optional scanner banner is informational and cannot enrich stock rows.
4. Roll back the consumer first if necessary; keep producer confirmation fields
   (older readers ignore additive fields). Reverting the producer confirmation
   would restore false VCP flags in older consumers and should be avoided.

No ranking weights, recognition algorithms, schedules, caches or data snapshots
are changed. Scores above 100 now qualify for the already-defined downstream
breakout bonus; unverified VCP bonuses disappear until fresh confirmation.

## Offline checks

```sh
python -m pytest tests/test_breakout_contract.py tests/test_scheduling.py -q
python -m pytest tests --ignore=tests/test_email_full.py -q
```

The excluded email script performs live fetches and notification actions at
import time. Existing deterministic suite baseline: `test_fetcher.py` expects a
`Date` column although `fetch_price_history` deliberately preserves its date
index. That unrelated failure also reproduces on main `a7d4327`.

`tests/fixtures/breakout_contract.json` is shared byte-for-byte with the Ranker
tests. The producer checks its expected JSON against the real exporter; the
consumer checks JSON → merge → signals → canonical export → browser offline.
The PR-only workflow runs deterministic contract/scheduling tests with read-only
permissions. It does not scan, commit data or dispatch another workflow.
