---
name: explain-recommendation
description: Explain why model v2 recommends (or does not recommend) champions for a concrete League of Legends draft, criterion by criterion (A strength, B counter, C synergy, S blind safety, F team balance) with uncertainty. Use when the user describes a draft and asks for picks, asks "why X and not Y", "proč mi to doporučuje", or wants a recommendation from the app explained.
argument-hint: "[role, spoluhráči, nepřátelé, bany, případně hrdina k vysvětlení]"
---

# Explain a recommendation

Turn a draft described in words into a call of `backend/model/explain.py`, then explain the
JSON result in Czech. Talk to the user in Czech; champion names stay in English as in the game.

## Rules

- Read only: do not change model code or the database in this skill. If the result looks wrong,
  say so and propose where to look (`backend/model/criteria.py`, `recommend.py`, aggregates).
- No Riot API call: D (personal form) and E (comfort) are neutral. Say this once if the user
  asked about their own champions or mastery; the web app (`/api/recommend`) includes them.
- Never invent numbers. Every number you mention must come from the JSON.

## 1. Build the command

From `$ARGUMENTS` or the conversation, find:

| Input | Flag | Note |
| --- | --- | --- |
| user's role | `--position TOP` | TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY (mid = MIDDLE, adc/bot = BOTTOM, support = UTILITY) |
| each ally | `--ally "Lee Sin:JUNGLE"` | repeat the flag; the role is required |
| each enemy | `--enemy "Darius:TOP"` | repeat; guess the usual role if the user omits it and say you guessed |
| each ban | `--ban Garen` | repeat |
| champion asked about | `--champion Sett` | for "why X?" or "why not X?" |

If the user's role is missing, ask for it. Everything else is optional.

```powershell
cd backend; .venv\Scripts\python -m model.explain --position TOP --ally "Lee Sin:JUNGLE" --enemy "Darius:TOP" --champion Sett; cd ..
```

Errors: `unknown champion ... Did you mean` → retry with the suggested name if it is clearly the
same champion, otherwise ask. `invalid draft` → explain the conflict (two allies in one role,
a banned champion picked) and ask. `aggregates missing` → suggest `/refresh-data`.

## 2. Read the JSON

- `meta`: patch, `data_computed_at`, `matches_used`, `known_enemies`, AHP weights (W win, E comfort,
  F balance), `dropped_criteria` (zero variance, e.g. E without a profile, F without allies),
  `spearman` agreement of PROMETHEE II and VIKOR with TOPSIS.
- `top[]` (rank 1-5) and `focus` (the asked champion), each with:
  - `criteria_pp`: A, B, C, D as percentage points of win chance; `criteria.S` is blind-pick
    safety (log-odds, closer to 0 = safer), `criteria.F` is team balance gain (-0.3 to 0.3).
  - `win_estimate`: estimated win chance from A+B+C+D.
  - `why`: the model's own short reasons (English); translate them.
  - `games`, `interval_pp` (90 % interval width of the win rate), `low_data` flags per A/B/C.
  - `top5_probability`: share of weight simulations (SMAA) keeping it in the top 5.
  - `promethee_rank`, `vikor_rank`: rank by the check methods.
- `focus.gap_to_first_pp`: per-criterion difference against #1 (negative = worse than #1).
- `focus.available: false` with `reason`: banned/picked, or not played in this role (`role_share`).

## 3. Answer the user

In Czech, short and concrete:

1. **Top 5** as a list: name, odhad výhry (%), the one or two criteria that drive it.
2. **Proč #1** (or the asked champion): the largest contributions in pp, e.g.
   „síla na patchi +0,7 pb, matchup proti Dariusovi +1,1 pb, vyváženost týmu lepší (F +0,02)“.
   For "why not X": its rank and the criteria in `gap_to_first_pp` where it loses most.
3. **Nejistota:** mention `low_data` (málo dat), wide `interval_pp` (over ~6 pb), SMAA
   stability under ~80 %, and a check-method rank far from the TOPSIS rank. If none applies,
   say the recommendation is stable.
4. **Kontext:** one line with patch, data date and number of matches. Remind that differences
   of tenths of a percentage point are small: draft explains only a few percent of the result.
