---
name: new-patch
description: Steps after a new League of Legends patch is released - collect matches from the new patch, rebuild aggregates, rerun the backtest on the new split and update docs/vysledky.md. Use when the user says a new patch is out, asks to move the model to the latest patch, or the aggregation report warns about a low current patch share.
argument-hint: "[číslo nového patche, např. 16.22]"
---

# Move to a new patch

Talk to the user in Czech. Run commands from the project root (PowerShell).

## Rules

- Never read or print `.env`. 401/403 = expired development key: stop and ask the user to renew it.
- One collector at a time; long runs in the background, wait for the completion notice, do not poll.
- Do not change model or pipeline code here. Report problems and propose a fix.
- `data/` is not in git; only `docs/vysledky.md` and `docs/img/` change in the repository.

## 1. Check the state

```powershell
cd backend; .venv\Scripts\python -m pipeline.status; cd ..
```

Note the newest patch in the database and how many matches it has. If the patch from
`$ARGUMENTS` is already the newest with enough matches (several hundred), skip to step 3.

## 2. Collect matches from the new patch

Follow the `refresh-data` skill. Right after a patch, use a short window so old matches do not
dominate, e.g. `--days 3`; repeat on later days as more games appear. The collector refreshes
Data Dragon itself when its version changes (new champions); check the report for
`unknown_champion` in quarantine, which would mean Data Dragon is behind.

## 3. Rebuild aggregates

```powershell
cd backend; .venv\Scripts\python -m pipeline.aggregate; cd ..
```

Check the report: `current_patch` must be the new patch. `current_patch_share` under 0.5 shows a
warning: the model mixes in the old patch (weight 0.5). Then the recommendation is still usable,
but say that it is based mostly on the previous patch and suggest collecting more.

## 4. Rerun the backtest

The backtest trains on the second newest patch and tests on the newest one by default:

```powershell
cd backend; .venv\Scripts\python -m model.backtest; cd ..
```

Use `--train-patch` / `--test-patch` to choose explicitly. With under ~300 test matches, say the
results are noisy (wide bootstrap intervals). It rewrites `docs/vysledky.md` and `docs/img/`.

## 5. Answer the user

In Czech, briefly:

1. New patch, matches in the database for it, Data Dragon version, quarantine/warnings.
2. Aggregation summary: current patch share, low-data share of matchups and duos.
3. Backtest change against the previous `docs/vysledky.md` (`git diff docs/vysledky.md`):
   AUC and log-loss of A+B+C, hit@5 of v2 vs baselines, SMAA stability. Highlight changes larger
   than the bootstrap intervals; call smaller ones noise.
4. Suggest a commit of `docs/vysledky.md` and `docs/img/`, e.g.
   `Update backtest results for patch 16.22`.
