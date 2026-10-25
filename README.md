# LoL draft doporučovač (v2)

Lokální prototyp, který během draftu v League of Legends doporučí 5 hrdinů pro tvoji roli.
Zadáš Riot ID, region, roli a stav draftu (spoluhráči, nepřátelé, bany) a dostaneš top 5
se zdůvodněním, odhadem šance na výhru a údajem o nejistotě.

Je to nová verze projektu z diplomové práce (TOPSIS + AHP), postavená od nuly na vlastních
datech z Riot API. Běží jen lokálně na jednom PC (Flask + SQLite + React).

## Jak to funguje

1. **Datová pipeline** stáhne ranked solo zápasy (queue 420) z Riot API do SQLite, zkontroluje
   jejich kvalitu (vadné zápasy jdou do karantény s důvodem) a spočítá agregace.
2. **Model v2** hodnotí každého hrdinu životaschopného v roli podle kritérií:

   | Kritérium | Co měří |
   | --- | --- |
   | A síla | winrate hrdiny v roli na aktuálním patchi, vyhlazený (empirical Bayes) |
   | B counter | matchupy proti známým nepřátelům, hlavně proti lajnovému soupeři |
   | C synergie | dvojice se známými spoluhráči |
   | D osobní forma | tvůj winrate na hrdinovi s časovým útlumem (z Riot API) |
   | E komfort | mastery a jak nedávno jsi hrdinu hrál |
   | F vyváženost | o kolik hrdina zlepší tým (poměr AD/AP, frontline, CC) |

   A až D jsou posuny šance na výhru, takže jejich součet je odhad výhry. Pořadí skládá TOPSIS
   s vahami z AHP (konzistence CR < 0,1); PROMETHEE II a VIKOR slouží jako kontrola a simulace
   vah (SMAA) říká, jak stabilní je místo v top 5.
3. **API a UI** čtou jen předpočítané agregace, profil hráče se z Riot API načte jednou
   a 15 minut drží v cache.

Podrobnosti: [docs/plan.md](docs/plan.md) (model, data, validace), výsledky backtestu
v [docs/vysledky.md](docs/vysledky.md).

## Požadavky

- Windows a PowerShell (příkazy níže jsou pro něj; jinde stačí upravit cesty k `.venv`).
- Python 3.13 nebo novější (vyvíjeno na 3.15).
- Node.js 20.19 nebo novější (Vite 8).
- Riot API klíč z [developer.riotgames.com](https://developer.riotgames.com). Development key
  platí 24 hodin, pak ho tam obnov.

## Instalace

Všechny příkazy spouštěj z kořene projektu.

```powershell
git clone <adresa-repozitáře> lol-draft-v2
cd lol-draft-v2

py -3 -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
npm --prefix frontend install

Copy-Item .env.example .env
notepad .env   # vlož svůj RIOT_API_KEY
```

`.env` je v `.gitignore`, do repozitáře se nikdy nedostane.

Kontrola instalace (nepotřebuje klíč ani data):

```powershell
cd backend; .venv\Scripts\python -m pytest; cd ..
```

## První data

Databáze `data/lol_draft.db` není v gitu, je potřeba ji naplnit. Nejdřív malý zkušební běh:

```powershell
cd backend; .venv\Scripts\python -m pipeline.collect --max-matches 20; cd ..
```

Pak větší běh (10 až 40 minut kvůli rate limitu klíče, jde přerušit Ctrl+C a spustit znovu
bez duplicit):

```powershell
cd backend; .venv\Scripts\python -m pipeline.collect --max-matches 1500 --players-per-tier 15 --matches-per-player 8; cd ..
```

Po každém sběru přepočítej agregace, ze kterých čte model:

```powershell
cd backend; .venv\Scripts\python -m pipeline.aggregate; cd ..
```

Reporty kvality dat (`run_NNNN.md`, `aggregate_*.md`) se ukládají do `data/reports/`.
Odpověď 401 nebo 403 znamená, že klíč vypršel.

## Spuštění aplikace

Backend a frontend běží každý ve svém terminálu:

```powershell
backend\.venv\Scripts\python backend\run.py      # http://127.0.0.1:5001
```

```powershell
npm --prefix frontend run dev                    # http://localhost:5173
```

Otevři http://localhost:5173, vyplň Riot ID (např. `Jméno#EUNE`), region a roli, naklikej
známé hrdiny a bany a klikni na doporučení. Bez Riot ID nebo s vypršelým klíčem aplikace
doporučuje dál, jen osobní kritéria D a E jsou neutrální.

## Další příkazy

| Příkaz (z kořene, `cd backend; ...; cd ..`) | K čemu |
| --- | --- |
| `.venv\Scripts\python -m pipeline.status` | stav dat: běžící sběry, hráči podle tieru, poslední report |
| `.venv\Scripts\python -m model.backtest` | backtest na novějším patchi proti baseline → `docs/vysledky.md` |
| `.venv\Scripts\python -m model.compare` | srovnání pořadí v1 a v2 → `docs/srovnani-v1-v2.md` (potřebuje data v1) |
| `.venv\Scripts\python -m model.explain --position TOP --enemy "Darius:TOP" --champion Sett` | rozpad doporučení jako JSON |
| `.venv\Scripts\python -m pipeline.backfill` | jednorázové doplnění statistik u starých zápasů |

Lint frontendu: `npm --prefix frontend run lint`.

Pro práci s Claude Code jsou v `.claude/skills/` připravené skills `/refresh-data` (sběr
a kontrola dat), `/explain-recommendation` (vysvětlení doporučení) a `/new-patch`
(postup po novém patchi).

## Struktura

```
backend/
  app/        Flask API (/api/health, /api/meta, /api/champions, POST /api/recommend)
  pipeline/   sběr z Riot API, kontroly kvality, karanténa, agregace, reporty
  model/      kritéria A až F, AHP, TOPSIS, PROMETHEE II, VIKOR, SMAA, backtest
  tests/      pytest (testovací data jsou syntetická a tak označená)
frontend/     React přes Vite
data/         SQLite databáze a reporty (není v gitu)
docs/         plán, brainstorm, srovnání v1 a v2, výsledky backtestu
```

## Co od toho čekat

- Draft vysvětluje jen malou část výsledku zápasu; i dobré modely mají přesnost 52 až 60 %.
  Rozdíly v doporučení jsou desetiny až jednotky procentního bodu.
- S pár stovkami zápasů je většina matchupů a dvojic pod prahem 30 her, takže counter
  a synergie zůstávají blízko nuly a doporučení stojí hlavně na síle hrdiny. Backtest
  ([docs/vysledky.md](docs/vysledky.md)) zatím neukazuje, že by v2 trefovala picky hráčů
  lépe než jednoduché baseline.
- Hodnotí se jen hrdinové a jejich kombinace, ne hráči (pravidlo Riotu). Data jsou jen
  z oficiálního API, agregátory typu OP.GG se nestahují.

## Právní poznámka

Projekt není schválený společností Riot Games a nevyjadřuje její názory. Riot Games
a League of Legends jsou ochranné známky nebo registrované ochranné známky Riot Games, Inc.
