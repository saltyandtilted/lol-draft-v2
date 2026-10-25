"""Backtest of model v2 on a newer patch than its aggregates, against simple baselines.

Usage (from backend/):
    .venv\\Scripts\\python -m model.backtest [--train-patch 16.20 --test-patch 16.21 --drafts 600]

Aggregates are computed in memory from the training patch only, so no test match leaks into
the model. The database is not modified. Only the draft part of the model is tested (A, B, C,
S, F with an empty player profile): the database has no player history, and today's mastery
would leak the future. Results go to docs/vysledky.md, charts to docs/img/.
"""

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app import db
from app.config import PROJECT_ROOT, Config
from pipeline import aggregate as pipeline_aggregate
from pipeline.aggregate import patch_key

from . import criteria, mcdm, metrics, regression, smaa
from .data import POSITIONS, Aggregates, Draft, Pick
from .v1_baseline import V1_CHAMPIONS, load_v1_champions, v1_rank
from .weights import GOAL_MATRIX, goal_weights

OUTPUT = PROJECT_ROOT / "docs" / "vysledky.md"
IMAGES = PROJECT_ROOT / "docs" / "img"
PHASES = (0, 2, 5)  # known enemies
KS = (1, 5, 10)
SMAA_DRAFTS = 100
BOOTSTRAP = 2000
# Alternative AHP judgments of W against E and F for the weight sensitivity check.
ALT_MATRICES = {
    "W slabší (3:1)": np.array([[1.0, 3.0, 3.0], [1 / 3, 1.0, 1.0], [1 / 3, 1.0, 1.0]]),
    "W silnější (9:1)": np.array([[1.0, 9.0, 9.0], [1 / 9, 1.0, 1.0], [1 / 9, 1.0, 1.0]]),
}
PRIOR_SCALES = (0.5, 2.0)


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


# --- Data split ---------------------------------------------------------------------------------


@dataclass
class Split:
    train_patch: str
    test_patch: str
    train_raw: pd.DataFrame  # participant rows for pipeline.aggregate.compute
    test_raw: pd.DataFrame
    parts: pd.DataFrame  # participant rows with blue_win for regression.match_features
    bans: pd.DataFrame
    names: dict = field(default_factory=dict)

    @property
    def train_ids(self) -> set:
        return set(self.train_raw["match_id"])

    @property
    def test_ids(self) -> set:
        return set(self.test_raw["match_id"])


def default_patches(patches) -> tuple[str, str]:
    ordered = sorted(set(patches), key=patch_key)
    if len(ordered) < 2:
        raise SystemExit("backtest needs matches from at least two patches")
    return ordered[-2], ordered[-1]


def split_by_patch(raw: pd.DataFrame, parts: pd.DataFrame, bans: pd.DataFrame,
                   train_patch: str, test_patch: str, names=None) -> Split:
    split = Split(train_patch, test_patch, raw[raw["patch"] == train_patch].copy(),
                  raw[raw["patch"] == test_patch].copy(), parts, bans, names or {})
    if split.train_raw.empty or split.test_raw.empty:
        raise SystemExit(f"no matches for patch {train_patch} or {test_patch}")
    leaked = split.train_ids & split.test_ids
    assert not leaked, f"{len(leaked)} matches in both train and test"
    return split


def load_split(conn, train_patch=None, test_patch=None) -> Split:
    raw = pipeline_aggregate.load_participants(conn)
    parts = regression.load_parts(conn)
    bans = pd.read_sql_query("SELECT match_id, champion_id FROM bans WHERE champion_id > 0", conn)
    names = dict(conn.execute("SELECT champion_id, name FROM champions").fetchall())
    default_train, default_test = default_patches(raw["patch"])
    return split_by_patch(raw, parts, bans, train_patch or default_train, test_patch or default_test, names)


def train_aggregates(split: Split, prior_scale: float = 1.0, test: bool = False) -> Aggregates:
    tables, meta = pipeline_aggregate.compute(split.test_raw if test else split.train_raw, prior_scale)
    return Aggregates.from_tables(tables, meta, split.names)


# --- Win prediction -----------------------------------------------------------------------------


def win_prediction(split: Split, agg: Aggregates) -> dict:
    """Probabilities of a blue win on test matches from three predictors."""
    features = {}
    for name, ids in (("train", split.train_ids), ("test", split.test_ids)):
        parts = split.parts[split.parts["match_id"].isin(ids)]
        features[name] = regression.match_features(parts, agg.champions, agg.matchups, agg.duos)
    train, test = features["train"], features["test"]
    x_cols = ["A", "B", "C"]
    beta = regression.fit_logistic(train[x_cols].to_numpy(), train["blue_win"].to_numpy())
    y = test["blue_win"].to_numpy()
    preds = {
        "konstanta (winrate modré strany)": np.full(len(test), train["blue_win"].mean()),
        "v2: jen A (síla hrdiny)": sigmoid(test["A"].to_numpy()),
        "v2: A+B+C (bez fitování)": sigmoid(test[x_cols].sum(axis=1).to_numpy()),
        "v2: logistická regrese na A, B, C": sigmoid(beta[0] + test[x_cols].to_numpy() @ beta[1:]),
    }
    rows = []
    for name, p in preds.items():
        rows.append({"model": name, "log_loss": metrics.log_loss(y, p), "brier": metrics.brier(y, p),
                     "auc": metrics.auc(y, p), "accuracy": metrics.accuracy(y, p)})
    base = preds["konstanta (winrate modré strany)"]
    best = preds["v2: A+B+C (bez fitování)"]
    diff_ci = bootstrap_ci(lambda idx: metrics.log_loss(y[idx], base[idx]) - metrics.log_loss(y[idx], best[idx]),
                           len(y))
    return {"table": pd.DataFrame(rows), "y": y, "preds": preds, "beta": beta, "matches": len(test),
            "train_matches": len(train), "logloss_gain_ci": diff_ci}


def bootstrap_ci(statistic, n: int, samples: int = BOOTSTRAP, seed: int = 0) -> tuple[float, float, float]:
    """Point estimate and 90 % percentile bootstrap interval of statistic(indices)."""
    rng = np.random.default_rng(seed)
    values = [statistic(rng.integers(0, n, n)) for _ in range(samples)]
    return float(statistic(np.arange(n))), float(np.percentile(values, 5)), float(np.percentile(values, 95))


# --- Recommendation -----------------------------------------------------------------------------


def sample_drafts(split: Split, count: int, seed: int = 0) -> list[dict]:
    """Drafts from test matches: one player's pick is hidden, a random part of the draft is known."""
    rng = np.random.default_rng(seed)
    test = split.test_raw
    match_ids = sorted(split.test_ids)
    bans = split.bans.groupby("match_id")["champion_id"].apply(list).to_dict()
    drafts = []
    for i in range(count):
        match_id = match_ids[rng.integers(len(match_ids))]
        players = test[test["match_id"] == match_id]
        team = int(rng.choice([100, 200]))
        position = str(rng.choice(POSITIONS))
        known = PHASES[i % len(PHASES)]
        me = players[(players["team_id"] == team) & (players["position"] == position)].iloc[0]
        allies = [Pick(int(p.champion_id), p.position) for p in players.itertuples()
                  if p.team_id == team and p.position != position]
        enemies = [Pick(int(p.champion_id), p.position) for p in players.itertuples() if p.team_id != team]
        allies = [allies[j] for j in sorted(rng.choice(len(allies), int(rng.integers(0, 5)), replace=False))]
        enemies = [enemies[j] for j in sorted(rng.choice(len(enemies), known, replace=False))]
        drafts.append({
            "match_id": match_id,
            "draft": Draft(position, allies=allies, enemies=enemies, bans=bans.get(match_id, [])),
            "actual": int(me["champion_id"]),
            "win": int(me["win"]),
            "known": known,
        })
    return drafts


def rank_v2(agg: Aggregates, draft: Draft, weights: dict) -> tuple[list[int], pd.DataFrame, pd.DataFrame, list]:
    """Full v2 order without SMAA (fast), plus criteria values, normalized goals and active goals."""
    values = criteria.compute(agg, draft)
    if values.empty:
        return [], values, values, []
    norm = mcdm.normalize(values[criteria.GOALS])
    active, _ = mcdm.active_criteria(norm, weights)
    active = active or ["W"]
    score = mcdm.topsis(norm, weights, active)
    return [int(c) for c in score.sort_values(ascending=False).index], values, norm, active


def rankings(agg: Aggregates, item: dict, weights: dict, v1_champions) -> tuple[dict, pd.DataFrame]:
    draft = item["draft"]
    v2, values, _, _ = rank_v2(agg, draft, weights)
    out = {"v2": v2}
    if not values.empty:
        out["nejvyšší vyhlazený winrate"] = [int(c) for c in values["posterior_mean"].sort_values(
            ascending=False, kind="stable").index]
        out["nejhranější v roli"] = [int(c) for c in values["games"].sort_values(
            ascending=False, kind="stable").index]
    else:
        out["nejvyšší vyhlazený winrate"] = out["nejhranější v roli"] = []
    if v1_champions is not None:
        out["v1 (diplomka)"] = v1_rank(v1_champions, draft.position, [p.champion_id for p in draft.allies],
                                       [p.champion_id for p in draft.enemies], draft.bans, top_n=500)
    return out, values


def reference_strength(ref: Aggregates) -> pd.Series:
    """Champion strength (A, log-odds) measured on the test patch: did the pick hold up?"""
    return ref.champions.set_index(["champion_id", "position"])["dev_logodds"]


def evaluate_recommendations(agg: Aggregates, ref: Aggregates, drafts: list[dict], v1_champions) -> dict:
    weights, _ = goal_weights()
    strength = reference_strength(ref)
    records = []
    for item in drafts:
        ranked, _ = rankings(agg, item, weights, v1_champions)
        position = item["draft"].position
        for method, order in ranked.items():
            top5 = order[:5]
            records.append({
                "method": method,
                "known": item["known"],
                "rank": metrics.rank_of(order, item["actual"]),
                "win": item["win"],
                "ref_top1": strength.get((order[0], position), np.nan) if order else np.nan,
                "ref_top5": np.nanmean([strength.get((c, position), np.nan) for c in top5]) if top5 else np.nan,
                "ref_actual": strength.get((item["actual"], position), np.nan),
            })
    return {"records": pd.DataFrame(records)}


def summarize_hits(records: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for method, g in records.groupby("method", sort=False):
        ranks = [None if pd.isna(r) else int(r) for r in g["rank"]]
        row = {"method": method, "drafts": len(g), "coverage": float(np.mean([r is not None for r in ranks]))}
        row.update({f"hit@{k}": metrics.hit_at_k(ranks, k) for k in KS})
        row["mrr"] = metrics.mean_reciprocal_rank(ranks)
        row["ref_top1_pp"] = pp(g["ref_top1"].mean())
        row["ref_top5_pp"] = pp(g["ref_top5"].mean())
        rows.append(row)
    return pd.DataFrame(rows)


def hits_by_phase(records: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    def hit(g):
        return metrics.hit_at_k([None if pd.isna(r) else int(r) for r in g["rank"]], k)
    return records.groupby(["method", "known"], sort=False).apply(hit, include_groups=False).unstack("known")


def paired_hit_ci(records: pd.DataFrame, a: str, b: str, k: int = 5) -> tuple[float, float, float]:
    """Difference in hit@k between methods a and b on the same drafts, with a bootstrap interval."""
    def hits(method):
        r = records[records["method"] == method]["rank"].to_numpy(dtype=float)
        return (~np.isnan(r)) & (np.nan_to_num(r, nan=np.inf) <= k)
    ha, hb = hits(a), hits(b)
    return bootstrap_ci(lambda idx: float(ha[idx].mean() - hb[idx].mean()), len(ha))


def pp(logodds: float) -> float:
    """Log-odds shift around 50 % in percentage points."""
    return float((sigmoid(logodds) - 0.5) * 100) if pd.notna(logodds) else float("nan")


def ref_gain_ci(records: pd.DataFrame, method: str) -> tuple[float, float, float]:
    """Reference strength of the method's #1 minus the actual pick, in percentage points."""
    g = records[records["method"] == method].dropna(subset=["ref_top1", "ref_actual"])
    diff = (g["ref_top1"] - g["ref_actual"]).to_numpy()
    return bootstrap_ci(lambda idx: pp(diff[idx].mean()), len(diff))


# --- Sensitivity --------------------------------------------------------------------------------


def smaa_stability(agg: Aggregates, drafts: list[dict]) -> dict:
    weights, _ = goal_weights()
    probs, rho_p, rho_v = [], [], []
    for item in drafts:
        order, values, norm, active = rank_v2(agg, item["draft"], weights)
        if len(order) < 6:
            continue
        stability = smaa.top_k_probability(norm, weights, active, samples=500)
        probs += [float(stability[c]) for c in order[:5]]
        score = mcdm.topsis(norm, weights, active)
        rho_p.append(mcdm.spearman(score, mcdm.promethee_ii(norm, weights, active)))
        rho_v.append(mcdm.spearman(score, -mcdm.vikor(norm, weights, active)))
    probs = np.array(probs)
    if not rho_p:  # every draft had too few candidates
        return {"probs": probs, "mean": np.nan, "share_80": np.nan, "rho_promethee": np.nan,
                "rho_vikor": np.nan, "drafts": 0}
    return {"probs": probs, "mean": float(probs.mean()), "share_80": float((probs >= 0.8).mean()),
            "rho_promethee": float(np.nanmean(rho_p)), "rho_vikor": float(np.nanmean(rho_v)),
            "drafts": len(rho_p)}


def weight_sensitivity(agg: Aggregates, drafts: list[dict]) -> pd.DataFrame:
    base_weights, base_cr = goal_weights()
    base = {i: rank_v2(agg, d["draft"], base_weights)[0] for i, d in enumerate(drafts)}
    rows = [{"variant": "výchozí AHP (7:1, 6:1)", "weights": base_weights, "cr": base_cr,
             "top5_overlap": 5.0, "same_top1": 1.0,
             "hit@5": metrics.hit_at_k([metrics.rank_of(base[i], d["actual"]) for i, d in enumerate(drafts)], 5)}]
    for name, matrix in ALT_MATRICES.items():
        weights, cr = goal_weights(matrix)
        orders = {i: rank_v2(agg, d["draft"], weights)[0] for i, d in enumerate(drafts)}
        rows.append({
            "variant": name, "weights": weights, "cr": cr,
            "top5_overlap": float(np.mean([len(set(orders[i][:5]) & set(base[i][:5])) for i in base])),
            "same_top1": float(np.mean([orders[i][:1] == base[i][:1] for i in base])),
            "hit@5": metrics.hit_at_k([metrics.rank_of(orders[i], d["actual"]) for i, d in enumerate(drafts)], 5),
        })
    return pd.DataFrame(rows)


def prior_sensitivity(split: Split, drafts: list[dict]) -> pd.DataFrame:
    weights, _ = goal_weights()
    rows = []
    for scale in (1.0, *PRIOR_SCALES):
        agg = train_aggregates(split, prior_scale=scale)
        wp = win_prediction(split, agg)["table"].set_index("model")
        ranks = [metrics.rank_of(rank_v2(agg, d["draft"], weights)[0], d["actual"]) for d in drafts]
        rows.append({"prior_scale": scale,
                     "log_loss": wp.loc["v2: A+B+C (bez fitování)", "log_loss"],
                     "auc": wp.loc["v2: A+B+C (bez fitování)", "auc"],
                     "hit@5": metrics.hit_at_k(ranks, 5)})
    return pd.DataFrame(rows)


# --- Charts -------------------------------------------------------------------------------------


def charts(win: dict, records: pd.DataFrame, stability: dict, out_dir: Path) -> dict:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0.3, 0.7], [0.3, 0.7], color="#999", linestyle="--", linewidth=1, label="dokonalá kalibrace")
    for name, color in (("v2: A+B+C (bez fitování)", "#2a6fdb"), ("v2: logistická regrese na A, B, C", "#e07b00")):
        bins = metrics.reliability_bins(win["y"], win["preds"][name], bins=8)
        ax.plot(bins["predicted"], bins["observed"], marker="o", color=color, label=name)
    ax.set_xlim(0.3, 0.7)
    ax.set_ylim(0.2, 0.8)
    ax.set_xlabel("předpovězená pravděpodobnost výhry modré strany")
    ax.set_ylabel("skutečný podíl výher")
    ax.set_title("Kalibrace (test patch, 8 košů se stejným počtem zápasů)", fontsize=9)
    ax.legend(fontsize=8)
    files["reliability"] = _save(fig, out_dir / "kalibrace.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    ks = np.arange(1, 21)
    for method, g in records.groupby("method", sort=False):
        ranks = [None if pd.isna(r) else int(r) for r in g["rank"]]
        ax.plot(ks, [metrics.hit_at_k(ranks, k) for k in ks], marker=".", label=method)
    ax.set_xlabel("k")
    ax.set_ylabel("hit@k (skutečný pick v top k)")
    ax.set_xticks([1, 5, 10, 15, 20])
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    files["hits"] = _save(fig, out_dir / "hit-at-k.png")

    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.hist(stability["probs"], bins=np.linspace(0, 1, 21), color="#2a6fdb", edgecolor="white")
    ax.set_xlabel("podíl simulací vah (SMAA), ve kterých hrdina zůstal v top 5")
    ax.set_ylabel("počet doporučení")
    files["smaa"] = _save(fig, out_dir / "smaa-stabilita.png")
    return files


def _save(fig, path: Path) -> str:
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    import matplotlib.pyplot as plt

    plt.close(fig)
    return path.name


# --- Report -------------------------------------------------------------------------------------


def fmt(x, digits=3):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{digits}f}"


def pct(x):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.1%}"


def ci_text(ci, unit="", digits=1, scale=1.0):
    point, low, high = (v * scale for v in ci)
    return f"{point:+.{digits}f}{unit} (90% interval {low:+.{digits}f} až {high:+.{digits}f}{unit})"


def to_markdown(split: Split, agg: Aggregates, win: dict, hits: pd.DataFrame, phases: pd.DataFrame,
                hit_cis: dict, ref_cis: dict, records: pd.DataFrame, stability: dict,
                weights_table: pd.DataFrame, priors: pd.DataFrame, images: dict) -> str:
    meta = agg.meta
    lines = [
        "# Výsledky backtestu modelu v2",
        "",
        f"Vygenerováno {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC příkazem `python -m model.backtest`.",
        f"Agregace jen z patche **{split.train_patch}** ({win['train_matches']} zápasů), test na patchi "
        f"**{split.test_patch}** ({win['matches']} zápasů). Testovací zápasy do agregací nevstoupily "
        "(kontrola v kódu i v testu).",
        f"Testuje se jen draftová část modelu (A, B, C, S, F); osobní kritéria D a E a baseline „nejvyšší "
        "mastery“ ne, protože databáze nemá historii hráčů a dnešní mastery by do testu pustilo budoucnost.",
        "",
        "## Shrnutí",
        "",
    ]
    lines += verdict(win, hits, hit_cis, ref_cis)
    lines += [
        "",
        "## 1. Predikce výhry z draftu",
        "",
        "| Model | log-loss | Brier | AUC | přesnost |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in win["table"].itertuples():
        lines.append(f"| {r.model} | {fmt(r.log_loss, 4)} | {fmt(r.brier, 4)} | {fmt(r.auc)} | {pct(r.accuracy)} |")
    b = win["beta"]
    lines += [
        "",
        "Nižší log-loss a Brier jsou lepší, AUC 0,5 je náhoda. Plán čeká přesnost jen 52 až 60 %.",
        f"Zlepšení log-loss A+B+C proti konstantě: {ci_text(win['logloss_gain_ci'], digits=4)}; "
        "kladné = v2 je lepší.",
        f"Koeficienty regrese fitované na tréninkovém patchi: A {b[1]:.2f}, B {b[2]:.2f}, C {b[3]:.2f}, "
        f"intercept {b[0]:.3f} (koeficient 1 = kritérium je škálované přesně).",
        "",
        f"![Kalibrace](img/{images['reliability']})",
        "",
        "## 2. Doporučení: byl skutečný pick mezi doporučenými?",
        "",
        f"{len(records) // max(records['method'].nunique(), 1)} draftů z testovacích zápasů: jeden hráč, "
        "náhodná část spoluhráčů, 0, 2 nebo 5 známých nepřátel, skutečné bany.",
        "",
        "| Metoda | pokrytí | hit@1 | hit@5 | hit@10 | MRR | síla #1 na novém patchi | síla top 5 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in hits.itertuples():
        lines.append(f"| {r.method} | {pct(r.coverage)} | {pct(r._4)} | {pct(r._5)} | {pct(r._6)} | "
                     f"{fmt(r.mrr)} | {r.ref_top1_pp:+.2f} pb | {r.ref_top5_pp:+.2f} pb |")
    lines += [
        "",
        "- **Pokrytí:** skutečný pick je mezi kandidáty metody (v2 a obě baseline mají stejný pool: hrdinové "
        "s aspoň 5 % her v roli na tréninkovém patchi; v1 má vlastní seznam rolí).",
        "- **hit@k** měří shodu s tím, co hráči opravdu vybrali, ne optimalitu (survivorship bias).",
        "- **Síla na novém patchi:** vyhlazený winrate hrdiny v roli spočítaný z testovacího patche "
        "(v procentních bodech proti průměru role). Ukazuje, jestli doporučený hrdina byl silný i v datech, "
        "která model neviděl.",
        "",
        "Rozdíly hit@5 proti v2 (párově na stejných draftech, bootstrap):",
        "",
    ]
    for method, ci in hit_cis.items():
        lines.append(f"- v2 − {method}: {ci_text(ci, ' pb', scale=100)}")
    lines += ["", "Síla #1 na novém patchi minus síla skutečného picku:", ""]
    for method, ci in ref_cis.items():
        lines.append(f"- {method}: {ci_text(ci, ' pb', digits=2)}")
    lines += [
        "",
        f"![hit@k](img/{images['hits']})",
        "",
        "hit@5 podle počtu známých nepřátel:",
        "",
        "| Metoda | " + " | ".join(f"{k} nepřátel" for k in phases.columns) + " |",
        "| --- |" + " --- |" * len(phases.columns),
    ]
    for method, row in phases.iterrows():
        lines.append(f"| {method} | " + " | ".join(pct(v) for v in row) + " |")
    v2 = records[records["method"] == "v2"]
    in_top5 = v2[v2["rank"].fillna(999) <= 5]["win"]
    rest = v2[v2["rank"].fillna(999) > 5]["win"]
    lines += [
        "",
        f"Winrate hráčů, jejichž pick byl v top 5 v2: {pct(in_top5.mean())} ({len(in_top5)} draftů), "
        f"ostatní: {pct(rest.mean())} ({len(rest)}). Je to korelace, ne kauzální efekt.",
        "",
        "## 3. Citlivost",
        "",
        f"**Nejistota vah (SMAA, {stability['drafts']} draftů):** hrdina z top 5 v ní zůstal průměrně "
        f"v {pct(stability['mean'])} simulací, {pct(stability['share_80'])} doporučení má stabilitu aspoň 80 %.",
        f"**Kontrolní metody:** průměrné Spearmanovo ρ s TOPSIS: PROMETHEE II {fmt(stability['rho_promethee'], 2)}, "
        f"VIKOR {fmt(stability['rho_vikor'], 2)}.",
        "",
        f"![SMAA](img/{images['smaa']})",
        "",
        "**Jiné AHP matice** (E má s prázdným profilem nulový rozptyl a vypadne, rozhoduje poměr W a F):",
        "",
        "| Varianta | váhy W / E / F | CR | průměrná shoda top 5 | stejná #1 | hit@5 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in weights_table.itertuples():
        w = r.weights
        lines.append(f"| {r.variant} | {w['W']:.2f} / {w['E']:.2f} / {w['F']:.2f} | {r.cr:.3f} | "
                     f"{r.top5_overlap:.1f} z 5 | {pct(r.same_top1)} | {pct(r._6)} |")
    lines += [
        "",
        "**Síla priorů matchupů a du** (násobek `PRIOR_SD`; 0,5 = víc shrinkage, 2 = méně):",
        "",
        "| Násobek | log-loss A+B+C | AUC | hit@5 v2 |",
        "| --- | --- | --- | --- |",
    ]
    for r in priors.itertuples():
        lines.append(f"| {r.prior_scale:g} | {fmt(r.log_loss, 4)} | {fmt(r.auc)} | {pct(r._4)} |")
    lines += ["", LIMITS]
    return "\n".join(lines) + "\n"


def verdict(win: dict, hits: pd.DataFrame, hit_cis: dict, ref_cis: dict) -> list[str]:
    def significant(ci):
        return ci[1] > 0 or ci[2] < 0

    out = []
    gain = win["logloss_gain_ci"]
    auc_v2 = win["table"].set_index("model").loc["v2: A+B+C (bez fitování)", "auc"]
    if gain[1] > 0:
        out.append(f"- **Predikce výhry:** v2 je lepší než konstanta (AUC {auc_v2:.3f}, zlepšení log-loss "
                   "s intervalem nad nulou).")
    elif gain[2] < 0:
        out.append(f"- **Predikce výhry:** v2 je horší než konstanta (AUC {auc_v2:.3f}); součet kritérií "
                   "je na novém patchi přestřelený nebo šum.")
    else:
        out.append(f"- **Predikce výhry:** od konstanty se neliší průkazně (AUC {auc_v2:.3f}, interval "
                   "zlepšení log-loss obsahuje nulu).")
    for method, ci in hit_cis.items():
        word = (("v2 je průkazně lepší" if ci[0] > 0 else "v2 je průkazně horší") if significant(ci)
                else "rozdíl není průkazný")
        out.append(f"- **Shoda s picky hráčů proti „{method}“:** {word} (hit@5 v2 minus baseline "
                   f"{ci[0] * 100:+.1f} pb).")
    v2_ref = ref_cis.get("v2")
    if v2_ref:
        word = (("průkazně silnější než" if v2_ref[0] > 0 else "průkazně slabší než") if significant(v2_ref)
                else "zhruba stejně silný (rozdíl není průkazný) jako")
        out.append(f"- **Kvalita doporučení:** #1 od v2 byl na novém patchi {word} skutečný pick "
                   f"({v2_ref[0]:+.2f} pb).")
    return out


LIMITS = """## Omezení

- Malý vzorek: tréninkový patch má jen stovky zápasů, většina matchupů a du je pod prahem 30 her,
  takže kritéria B a C drží priory blízko nuly. S víc daty se výsledky mohou změnit.
- hit@k měří shodu s chováním hráčů (survivorship bias), ne to, jestli byl pick nejlepší.
- „Síla na novém patchi“ používá jen kritérium A z testovacích dat; je to rozumná, ale ne úplná
  reference (neobsahuje matchupy ani synergie). Vyhlazení navíc méně stahuje k nule často hrané
  hrdiny, takže reference mírně zvýhodňuje baseline „nejhranější v roli“.
- D (osobní forma) a E (komfort) nejsou testované; jejich váhy zůstávají expertní (AHP).
- Pořadí picků v ranked datech není, drafty jsou rekonstruované náhodným výběrem známých hrdinů.
"""


# --- Orchestration ------------------------------------------------------------------------------


def run(conn, train_patch=None, test_patch=None, draft_count=600, seed=0, use_v1=True,
        output: Path | None = OUTPUT, images: Path = IMAGES) -> dict:
    split = load_split(conn, train_patch, test_patch)
    agg = train_aggregates(split)
    ref = train_aggregates(split, test=True)
    win = win_prediction(split, agg)
    drafts = sample_drafts(split, draft_count, seed)
    v1_champions = load_v1_champions() if use_v1 and V1_CHAMPIONS.exists() else None
    records = evaluate_recommendations(agg, ref, drafts, v1_champions)["records"]
    hits = summarize_hits(records)
    phases = hits_by_phase(records)
    others = [m for m in records["method"].unique() if m != "v2"]
    hit_cis = {m: paired_hit_ci(records, "v2", m) for m in others}
    ref_cis = {m: ref_gain_ci(records, m) for m in records["method"].unique()}
    stability = smaa_stability(agg, drafts[:SMAA_DRAFTS])
    weights_table = weight_sensitivity(agg, drafts)
    priors = prior_sensitivity(split, drafts)
    result = {"split": split, "win": win, "hits": hits, "phases": phases, "hit_cis": hit_cis,
              "ref_cis": ref_cis, "stability": stability, "weights": weights_table, "priors": priors}
    if output is not None:
        image_files = charts(win, records, stability, images)
        text = to_markdown(split, agg, win, hits, phases, hit_cis, ref_cis, records, stability,
                           weights_table, priors, image_files)
        Path(output).write_text(text, encoding="utf-8")
        result["text"] = text
    return result


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Backtest model v2 on a newer patch.")
    parser.add_argument("--db", default=Config.DATABASE_PATH)
    parser.add_argument("--train-patch")
    parser.add_argument("--test-patch")
    parser.add_argument("--drafts", type=int, default=600)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-v1", action="store_true", help="skip the v1 comparison")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(argv)
    conn = db.connect(args.db)
    result = run(conn, args.train_patch, args.test_patch, args.drafts, args.seed, not args.no_v1,
                 Path(args.output), Path(args.output).parent / "img")
    conn.close()
    print(result["text"])
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
