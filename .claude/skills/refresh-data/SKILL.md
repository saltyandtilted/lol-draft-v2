---
name: refresh-data
description: Download new ranked solo matches from the Riot API into data/lol_draft.db and review the data quality report. Use when the user wants fresh match data, more matches, a data refresh, or asks whether the collected data is OK.
argument-hint: "[small | large | --max-matches N ...]"
---

# Refresh match data

Collect new ranked solo (queue 420) matches with `backend/pipeline/collect.py` and review
the quality report it writes. Talk to the user in Czech.

## Rules

- Never read, print or check the contents of `.env`. The collector loads the key itself.
- Run one collector at a time. Two runs would share the rate limit and hit 429.
- 401/403 in the output means the development key expired: stop and ask the user to renew it
  at developer.riotgames.com and update `.env`. Do not retry.
- Do not change pipeline code in this skill. If the report shows a bug, describe it and propose a fix.

## 1. Pick the run size

From `$ARGUMENTS`:

| Argument | Flags | Duration |
| --- | --- | --- |
| `small` or empty | `--max-matches 20 --players-per-tier 2` | under a minute |
| `large` | `--max-matches 1500 --players-per-tier 15 --matches-per-player 8` | 10 to 40 min |
| explicit flags | pass them through | depends |

Other flags: `--tiers GOLD PLATINUM ...` (sample only some tiers), `--days N` (default 14).
`--players-per-tier` counts players not processed yet, so every run samples new players by itself.
If the last report showed thin tiers, suggest a run with `--tiers` limited to them.

## 2. Check the current state

```powershell
cd backend; .venv\Scripts\python -m pipeline.status; cd ..
```

It prints runs marked `running`, match counts, players per tier (total / pending) and the
latest report. A `running` run with no live collector process is a crashed run and can be
ignored. If a collector is really running, wait for it instead of starting another.

## 3. Run the collector

From the project root:

```powershell
cd backend; .venv\Scripts\python -m pipeline.collect <flags>; cd ..
```

Run `large` runs in the background and wait for the completion notice; do not poll.
The run is safe to interrupt: already stored matches stay, and the next run skips them.

Then rebuild the aggregates the model reads:

```powershell
cd backend; .venv\Scripts\python -m pipeline.aggregate; cd ..
```

If its report warns about participant rows without stats, run `python -m pipeline.backfill`
and aggregate again.

## 4. Review the report

The collector prints the report and saves it as `data/reports/run_NNNN.md` (the newest file).
Check:

- **Warnings section:** report each warning.
- **Quarantine share:** quarantined / downloaded. Up to about 5 % (mostly `early_surrender`)
  is normal. More, or any `schema_error` / `unknown_champion`, needs explanation
  (API change, new champion missing from Data Dragon).
- **429 responses:** a few are fine. Many mean another process uses the same key.
- **Patch mix:** the current patch should hold most matches. Right after a new patch,
  suggest waiting or using `--days` so aggregates in milestone 4 are not built from the old one.
- **Tier balance:** list tiers with under about 50 matches as too thin for per-rank aggregates.
- **Champions seen vs known:** many unseen champions means the sample is too small.

## 5. Answer the user

In Czech, briefly:

1. What ran (flags, duration) and the result (downloaded / stored / quarantined, total in the database),
   plus the aggregation summary (matches used, share of low-data matchups and duos).
2. Problems found in step 4, or "bez varování".
3. One recommendation for the next run, if any.

Data in `data/` is not in git, so a refresh needs no commit.
