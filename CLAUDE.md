# LoL draft doporučovač – lokální prototyp

## O projektu
Osobní lokální prototyp doporučovače hrdinů pro draft v League of Legends.
Hráč zadá Riot ID, region, roli a stav draftu (spoluhráči, nepřátelé, bany)
a dostane top 5 hrdinů se zdůvodněním a údajem o nejistotě.
Je to NOVÁ verze projektu z mé diplomové práce (React + Flask, TOPSIS + AHP).
Diplomová práce se nemění a nový výzkum se nedělá. Cílem je funkční prototyp
lokálně na mém PC a naučit se pracovat s Claude Code.

- Plán modelu, dat a architektury: docs/plan.md
- Průvodce, milníky a tipy k práci: docs/pruvodce.md
- Rozhodnutí z brainstormu: docs/brainstorm.md (vznikne v milníku 1)

## Původní kód – jen inspirace, ne základ
- Původní kód: `C:\Users\SaltyAndTilted\lol-topsis-project` (novější)
  a `C:\Users\SaltyAndTilted\lol-topsis-backend` (starší).
- Spustitelná kopie v1: `C:\projekty\lol-draft` (klíč z .env, backend na portu 5001,
  frontend na 3000). Hodí se jako srovnávací baseline při validaci.
- Vznikl se starým ChatGPT a je slabý. Nekopíruj ho a nestav na něm.
  Čti ho jen pro pochopení původního záměru (kritéria, vstupy, UI).
- Do těchto složek nikdy nic nezapisuj. Jejich .env nečti.
- Chyby původní verze, které se nesmí opakovat:
  - AHP matice nebyla reciproční a chyběla kontrola konzistence (CR).
  - Balance vycházela pro všechny kandidáty stejně, takže nic neměnila.
  - Winrate po L2 normalizaci skoro nerozlišoval hrdiny.
  - Synergy a Counter byly jen počty shod v krátkých seznamech;
    Counter byl obráceně (WeakAgainst bráno jako přínos).
  - Hrdina měl jedinou roli, flex picky nešlo doporučit.
  - Mastery (váha 0,391) řídilo pořadí, i když měří odehraný čas, ne výkon.
  - Data byla statická a scrapovaná z LeagueOfGraphs (zakázáno).
  - Chyběla validace proti baseline.

## Model (podrobně v docs/plan.md, sekce Doporučený model)
Dvouvrstvý hybrid: spodní vrstva počítá kritéria jako odchylky pravděpodobnosti
výhry, horní vrstva (MCDM) je skládá s preferencemi hráče a vysvětluje pořadí.
- Kritéria:
  - A síla hrdiny: winrate v roli, patchi a ranku; log-odds vůči průměru role;
    beta-binomické empirical Bayes.
  - B counter: matchupové odchylky proti známým nepřátelům, vyšší váha
    lajnovému soupeři; log-odds, shrinkage k nule.
  - C synergie: duo odchylka oproti očekávání; log-odds, shrinkage k nule.
  - D osobní forma: winrate hráče na hrdinovi s časovým útlumem,
    hierarchicky vyhlazený, prior pro nehrané hrdiny.
  - E komfort: log(1 + mastery) se saturací a nedávnost hraní.
  - F vyváženost: přírůstek kvality týmového profilu (AD/AP, frontline, CC)
    po přidání kandidáta. Musí záviset na kandidátovi.
  - G meta (volitelné): popularita jako slabý signál.
- Agregace: TOPSIS s fixními ideály z celého poolu role a patche (ne z aktuální
  nabídky). PROMETHEE II a VIKOR jako kontrola robustnosti (Spearmanovo ρ).
  Součet A až D jako odhad výhry.
- Váhy: AHP s reciproční maticí a CR < 0,1 (nebo BWM). Dynamika podle fáze
  draftu (0 až 5 známých nepřátel). Nejistota vah přes SMAA / Monte Carlo
  s Dirichletem, výstup: pravděpodobnost, že kandidát je v top 5.
- Kandidáti: hrdinové životaschopní v roli (podíl her v roli nad prahem,
  např. 5 %), bez banů a už vybraných.
- Výstup: top 5 s rozpadem příspěvků kritérií, krátkým „proč“, počtem zápasů,
  šířkou intervalu, stabilitou v top 5 a patchem s datem dat.
- Nedělat: MCTS, reinforcement learning, embeddingy, ELECTRE.
- Pravidlo Riotu: hodnotit se smí hrdinové a kombinace, ne hráči
  (žádné MMR ani Elo skóre hráčů).

## Data
- Zdroje: account-v1 (Riot ID na PUUID), champion-mastery-v4, league-exp-v4
  (vzorkování hráčů podle ranku), match-v5 (zápasy), Data Dragon
  (hrdinové, tagy, ikony, cs_CZ).
- Jen ranked solo (queue 420). Výchozí region EUNE (platforma eun1, routing europe).
- Pořadí picků hráčů v ranked datech není, efekt pořadí se nemodeluje.

## Kontroly kvality dat
- Při stahování: deduplikace podle matchId; remaky a předčasné surrendery
  do karantény; jen queue 420 s vyplněnou gameVersion; úplnost zápasu
  (10 hráčů, 5 unikátních rolí na tým, žádná prázdná nebo INVALID
  teamPosition); ID hrdiny existuje v Data Dragonu.
- Při agregaci: minimální vzorek (vyšší pro matchupy a dua, pod prahem jen
  vyhlazená hodnota s příznakem „málo dat“); sanity checky (celkový winrate
  kolem 50 %, poměr blue/red); agregace z aktuálního patche.
- V modelu: AHP s CR >= 0,1 odmítnout; v TOPSIS žádné chybějící hodnoty,
  kritérium s nulovým rozptylem vyřadit a zalogovat.
- Vadné záznamy se neodhazují potichu: tabulka karantény v SQLite
  s matchId a důvodem. Po každém běhu pipeline krátký report kvality.
- Implementace: pydantic pro odpovědi API, pandera nebo vlastní funkce
  pro tabulky. Každá kontrola má pytest včetně záměrně vadných zápasů.
- Priorita: deduplikace, remaky, minimální vzorek u matchupů a du.

## Architektura
- Datová pipeline běží odděleně od aplikace a ukládá předpočítané agregace.
- API při dotazu čte jen agregace z databáze a profil hráče z cache
  (10 až 30 minut), takže odpověď nezávisí na rate limitu.
- Lokálně stačí SQLite a jeden proces. Žádný Docker, Redis ani PostgreSQL.

## Validace (docs/plan.md, sekce Validace a evaluace)
- Test na zápasech z novějšího patche než agregace. Pozor na data leakage.
- Baseline: nejvyšší vyhlazený winrate v roli, nejhranější hrdina,
  nejvyšší mastery hráče, původní model v1 (jen jako srovnávací funkce).
- Metriky: log-loss, Brier, AUC, kalibrace; hit@k; stabilita top 5 (SMAA).
- Očekávaná přesnost predikce z draftu je jen 52 až 60 %.

## Milníky (podrobně v docs/pruvodce.md)
1. Brainstorm: přečti plán a původní kód (jen čtení), zapiš rozhodnutí
   do docs/brainstorm.md. Žádný kód.
2. Kostra nového projektu: backend (Flask), frontend (React přes Vite),
   SQLite, načítání .env, pytest, doplnit sekci Příkazy.
3. Datová pipeline z Riot API s kontrolami kvality a reportem.
4. Model v2 (kritéria A až F, AHP s CR, TOPSIS, kontrolní metody) s testy.
5. API a UI: ikony z Data Dragonu, rozpad skóre, nejistota, chybové stavy.
6. Validace proti baseline a vlastní skills (refresh-data,
   explain-recommendation, new-patch).
7. README, úklid, aktualizace CLAUDE.md přes /init.

Aktuální milník: 1

## Kdo jsem a jak mě učit
- Datový analytik, znám Python, pandas a SQL. React a Claude Code jsou pro mě nové.
- Před každou větší změnou krátce řekni, co uděláš a proč.
- Po dokončení kroku vysvětli 1 až 3 věci, které se z něj mám naučit.
- Když používáš nový nástroj, příkaz nebo knihovnu, vysvětli ho jednou větou.
- Navrhni, kdy je vhodné použít skill, plánovací režim nebo commit.
- Neodbíhej mimo aktuální milník. Další krok navrhni, ale nezačínej ho.
- Komunikuj česky, kód a commity anglicky.

## Technologie
- Backend: Python, Flask, pandas, numpy, SQLite
- Frontend: React přes Vite (ne Create React App)
- Data: Riot API (development key, platí 24 hodin), Data Dragon
- Testy: pytest
- Mám Python 3.15. Pokud nějaká knihovna nejde nainstalovat, řekni mi to
  a navrhni přechod na Python 3.13 (`py -3.13`).
- Windows a PowerShell. Port 5000 je na Windows často blokovaný, backend dej na 5001.

## Pravidla
- API klíč je jen v .env (a .env je v .gitignore). Nikdy ho nečti, nevypisuj,
  nevkládej do kódu ani do commitu. V repozitáři je jen .env.example.
- Respektuj rate limity Riot API (20 req/s, 100 req/2 min) a ošetři odpověď 429.
  401/403 znamená vypršelý klíč – řekni mi, ať ho obnovím.
- Agregátory (LeagueOfGraphs, OP.GG, U.GG, Lolalytics) automaticky nestahuj.
- Každou změnu ověř spuštěním nebo testem a ukaž výsledek. Bez ověření není hotovo.
- Po každém funkčním kroku navrhni commit s popisnou zprávou.
- Testovací data jasně označ jako testovací.
- Nečti venv/, node_modules/ ani databázové soubory, pokud to úkol nevyžaduje.
- Když si nejsi jistý zadáním, zeptej se dřív, než začneš.

## Příkazy
(Doplň v milníku 2: jak spustit backend, frontend a testy.)
