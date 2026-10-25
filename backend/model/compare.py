"""Compare v1 and v2 rankings on the same drafts and write docs/srovnani-v1-v2.md.

Usage (from backend/):
    .venv\\Scripts\\python -m model.compare

Drafts come from the most recent stored matches (one pick hidden) plus three hand-made
scenarios. This is a side-by-side comparison, not a validation: the aggregates were computed
from the same matches (data leakage), so the rank of the actual pick is optimistic.
The out-of-sample backtest is model.backtest (docs/vysledky.md).
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app import db
from app.config import PROJECT_ROOT, Config

from . import mcdm, regression
from .data import POSITIONS, Aggregates, Draft, Pick
from .recommend import recommend
from .v1_baseline import V1_CHAMPIONS, load_v1_champions, v1_rank

OUTPUT = PROJECT_ROOT / "docs" / "srovnani-v1-v2.md"
ALL = 500  # "top n" large enough to get the full ranking
PHASES = [5, 2, 0]  # known enemies, cycled over the match drafts

EXPLANATION = """\
## Proč se pořadí liší

1. **Counter.** v1 počítala `WeakAgainst` kandidáta jako přínos, takže doporučovala hrdiny,
   kteří proti nepříteli prohrávají. v2 bere matchupové odchylky z vlastních zápasů
   se správným znaménkem. Všechny matchupy a dua mají zatím málo her, takže je realistické
   priory (lajnový matchup ±0,15, ostatní páry ±0,05 až 0,07 log-odds) drží blízko nuly
   a v2 se řídí hlavně silou hrdiny (A) a vyváženosti (F). S daty jejich vliv poroste.
2. **Ideály TOPSIS.** v1 brala ideál z aktuální nabídky, takže ban hrdiny, který určoval
   ideál některého kritéria, mohl přeházet pořadí ostatních (počty v sekci o banu).
   v2 má fixní hranice kritérií, pořadí ostatních se banem nemění nikdy.
3. **Role.** v1 měla jednu roli na hrdinu, v2 bere hrdiny s aspoň 5 % her v roli
   (flex picky).
4. **Winrate a mastery.** v1 měla statický winrate z LeagueOfGraphs a mastery s vahou 0,391.
   v2 má vyhlazený winrate z aktuálního patche a mastery jen jako komfort
   v hodnotě zhruba 3 až 4 procentních bodů. Ve srovnání se mastery nepoužívá (prázdný profil),
   aby šlo porovnat jen draftovou část.
5. **Vyváženost.** Ve v1 vycházela pro všechny kandidáty stejně, ve v2 se liší podle toho,
   co kandidát přidá týmu (podíl fyzického poškození, frontline, CC).
6. **Celková shoda je nízká** (ρ celého pořadí kolem 0, v top 5 obvykle 0 až 2 shodní).
   Je to očekávané: v1 stojí na statických scrapovaných datech a ručních seznamech, v2 na
   zápasech z aktuálního patche. Která verze doporučuje lépe, ukazuje backtest v docs/vysledky.md.
"""


def match_drafts(conn, agg: Aggregates, count: int = 10) -> list[dict]:
    patch = agg.meta["current_patch"]
    matches = [r[0] for r in conn.execute(
        "SELECT match_id FROM matches WHERE patch = ? ORDER BY game_creation DESC LIMIT ?", (patch, count))]
    drafts = []
    for i, match_id in enumerate(matches):
        players = conn.execute(
            "SELECT team_id, position, champion_id FROM participants WHERE match_id = ?", (match_id,)
        ).fetchall()
        bans = [r[0] for r in conn.execute(
            "SELECT champion_id FROM bans WHERE match_id = ? AND champion_id > 0", (match_id,))]
        team = 100 if i % 2 == 0 else 200
        position = POSITIONS[i % 5]
        known = PHASES[i % len(PHASES)]
        actual = next(p[2] for p in players if p[0] == team and p[1] == position)
        allies = [Pick(p[2], p[1]) for p in players if p[0] == team and p[1] != position]
        enemies = sorted((Pick(p[2], p[1]) for p in players if p[0] != team),
                         key=lambda p: POSITIONS.index(p.position))[:known]
        drafts.append({
            "label": f"{match_id} ({position}, {known} enemies)",
            "draft": Draft(position, allies=allies, enemies=enemies, bans=bans),
            "actual": actual,
        })
    return drafts


def handmade_drafts(agg: Aggregates) -> list[dict]:
    by_name = {name: cid for cid, name in agg.names.items()}

    def picks(*pairs):
        return [Pick(by_name[n], pos) for n, pos in pairs if n in by_name]

    return [
        {"label": "first pick TOP (nothing known)", "draft": Draft("TOP"), "actual": None},
        {"label": "mid draft MIDDLE (2 allies, 2 enemies)",
         "draft": Draft("MIDDLE", allies=picks(("Lee Sin", "JUNGLE"), ("Jinx", "BOTTOM")),
                        enemies=picks(("Ahri", "MIDDLE"), ("Thresh", "UTILITY"))),
         "actual": None},
        {"label": "last pick TOP vs. Darius, all-AD team",
         "draft": Draft("TOP", allies=picks(("Lee Sin", "JUNGLE"), ("Zed", "MIDDLE"),
                                            ("Caitlyn", "BOTTOM"), ("Pyke", "UTILITY")),
                        enemies=picks(("Darius", "TOP"), ("Elise", "JUNGLE"), ("Syndra", "MIDDLE"),
                                      ("Ezreal", "BOTTOM"), ("Leona", "UTILITY"))),
         "actual": None},
    ]


def _v1(v1_champions, draft: Draft, n: int) -> list[int]:
    return v1_rank(v1_champions, draft.position, [p.champion_id for p in draft.allies],
                   [p.champion_id for p in draft.enemies], draft.bans, top_n=n)


def compare_one(agg, v1_champions, item) -> dict:
    draft = item["draft"]
    v2_full = [c["champion_id"] for c in recommend(agg, draft, top_n=ALL, smaa_samples=200).candidates]
    top = recommend(agg, draft)
    v1_full = _v1(v1_champions, draft, ALL)
    common = [c for c in v2_full if c in v1_full]
    rho = mcdm.spearman(pd.Series([v2_full.index(c) for c in common]),
                        pd.Series([v1_full.index(c) for c in common]))
    actual = item["actual"]
    return {
        "label": item["label"],
        "v1": v1_full[:5],
        "v2": [c["champion_id"] for c in top.candidates],
        "stability": [c["top5_probability"] for c in top.candidates],
        "why": top.candidates[0]["why"] if top.candidates else [],
        "overlap": len(set(v1_full[:5]) & {c["champion_id"] for c in top.candidates}),
        "rho": rho,
        "actual": actual,
        "actual_rank_v2": v2_full.index(actual) + 1 if actual in v2_full else None,
        "actual_rank_v1": v1_full.index(actual) + 1 if actual in v1_full else None,
        "candidates_v2": len(v2_full),
        "candidates_v1": len(v1_full),
        "spearman_checks": top.meta["spearman"],
    }


def ban_check(agg, v1_champions, draft: Draft) -> dict:
    v2 = [c["champion_id"] for c in recommend(agg, draft, top_n=6, smaa_samples=100).candidates]
    v1 = _v1(v1_champions, draft, 6)
    v2_banned = [c["champion_id"] for c in recommend(
        agg, Draft(draft.position, draft.allies, draft.enemies, draft.bans + [v2[0]]),
        top_n=5, smaa_samples=100).candidates]
    v1_banned = _v1(v1_champions, Draft(draft.position, draft.allies, draft.enemies, draft.bans + [v1[0]]), 5)
    return {"v2_before": v2, "v2_after": v2_banned, "v2_stable": v2_banned == v2[1:6],
            "v1_before": v1, "v1_after": v1_banned, "v1_stable": v1_banned == v1[1:6]}


def to_markdown(agg, results, ban, ban_counts, diag) -> str:
    name = lambda cid: agg.names.get(cid, str(cid)) if cid is not None else "-"  # noqa: E731
    names = lambda ids: ", ".join(name(c) for c in ids) or "-"  # noqa: E731
    meta = agg.meta
    lines = [
        "# Srovnání pořadí v1 a v2",
        "",
        f"Vygenerováno {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC příkazem `python -m model.compare`.",
        f"Data: patch {meta['current_patch']} (váhy patchů {meta['patches_used']}), "
        f"{meta['matches_used']} zápasů, agregace z {meta['computed_at']}.",
        "",
        "Nejde o validaci: agregace jsou ze stejných zápasů, ze kterých jsou drafty, takže pořadí",
        "skutečného picku je optimistické. Backtest na novějším patchi je v docs/vysledky.md.",
        "",
        "## Top 5 na stejných draftech",
        "",
        "| Draft | v1 top 5 | v2 top 5 | shoda | ρ (celé pořadí) | skutečný pick | pořadí v1 / v2 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        rho = "-" if pd.isna(r["rho"]) else f"{r['rho']:.2f}"
        ranks = (f"{r['actual_rank_v1'] or 'není'} / {r['actual_rank_v2'] or 'není'}"
                 if r["actual"] is not None else "-")
        lines.append(f"| {r['label']} | {names(r['v1'])} | {names(r['v2'])} | {r['overlap']}/5 | {rho} "
                     f"| {name(r['actual'])} | {ranks} |")
    lines += ["", "„není“ = skutečný pick není mezi kandidáty dané verze (jiná role ve v1, "
              "pod 5 % her v roli ve v2).", ""]

    lines += ["## Stabilita a kontrolní metody v2", "",
              "| Draft | podíl simulací v top 5 (SMAA) | ρ PROMETHEE II | ρ VIKOR | proč #1 |",
              "| --- | --- | --- | --- | --- |"]
    for r in results:
        stab = ", ".join(f"{s:.0%}" for s in r["stability"])
        sp = r["spearman_checks"]
        lines.append(f"| {r['label']} | {stab} | {sp.get('promethee_ii', '-')} | {sp.get('vikor', '-')} "
                     f"| {'; '.join(r['why'])} |")

    lines += ["", "## Ban nejlepšího kandidáta (first pick TOP)", "",
              "| Verze | před banem (1 až 6) | po banu #1 (top 5) | zbytek ve stejném pořadí |",
              "| --- | --- | --- | --- |",
              f"| v1 | {names(ban['v1_before'])} | {names(ban['v1_after'])} | {'ano' if ban['v1_stable'] else 'ne'} |",
              f"| v2 | {names(ban['v2_before'])} | {names(ban['v2_after'])} | {'ano' if ban['v2_stable'] else 'ne'} |",
              "",
              f"Ban nejlepšího kandidáta na všech {ban_counts['drafts']} draftech: pořadí ostatních zůstalo "
              f"ve v1 v {ban_counts['v1_stable']} případech, ve v2 v {ban_counts['v2_stable']} případech.",
              "", "## Diagnostika: logistická regrese výhry na A, B, C (in-sample)", "",
              f"Zápasů: {diag['matches']}. Koeficienty: A {diag['coef_A']}, B {diag['coef_B']}, "
              f"C {diag['coef_C']}, intercept {diag['intercept']}.",
              "Koeficient 1 by znamenal, že kritérium je v log-odds přesně škálované. Hodnoty nad 1 jsou",
              "tu očekávané ze dvou důvodů: vyhlazení odhady záměrně zmenšuje a regrese běží na stejných",
              "zápasech, ze kterých jsou agregace (únik dat). Proto je to jen diagnostika; váhy A až D",
              "zůstávají stejné; regrese na odložených datech je v docs/vysledky.md.",
              "", EXPLANATION]
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Compare v1 and v2 rankings.")
    parser.add_argument("--db", default=Config.DATABASE_PATH)
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(argv)
    if not V1_CHAMPIONS.exists():
        raise SystemExit(f"v1 data not found at {V1_CHAMPIONS}")
    conn = db.connect(args.db)
    agg = Aggregates.from_db(conn)
    v1_champions = load_v1_champions()
    items = match_drafts(conn, agg) + handmade_drafts(agg)
    results = [compare_one(agg, v1_champions, item) for item in items]
    ban = ban_check(agg, v1_champions, Draft("TOP"))
    checks = [ban_check(agg, v1_champions, item["draft"]) for item in items]
    ban_counts = {"drafts": len(checks), "v1_stable": sum(c["v1_stable"] for c in checks),
                  "v2_stable": sum(c["v2_stable"] for c in checks)}
    diag = regression.diagnostic(conn, agg.champions, agg.matchups, agg.duos)
    conn.close()
    text = to_markdown(agg, results, ban, ban_counts, diag)
    Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
