# Plán: doporučovač hrdinů v LoL – model, data, architektura

Převzato z dokumentu „Plán: doporučovač hrdinů v LoL – další kroky“ (Claude Docs, 20. 10. 2026).
Pořadí práce určují **milníky v CLAUDE.md**. Sekce „Fáze realizace“ níže je jen orientační.

## Cíl a výchozí stav

Cíl je funkční prototyp, který poběží lokálně na mém PC. Vylepšuje původní projekt z diplomky
(samotná práce zůstává beze změn) a zároveň je zkouškou, jak dobře AI takový systém navrhne
a postaví s Claude Code. Součástí je brainstorm, zda byl původní návrh dobrý.
Linie TOPSIS + AHP se zachová, jen dostane empirický obsah.

Co je v původní verzi špatně:

- Saatyho matice není reciproční a chybí kontrola konzistence (CR).
- Balance je pro všechny kandidáty stejná, takže v TOPSIS nic nemění a její váha 0,088 je mrtvá.
  (V kódu navíc kvůli chybě v dohledávání vychází počet AD hrdinů vždy 0.)
- Winrate po L2 normalizaci skoro nerozlišuje hrdiny (hodnoty kolem 0,5 se liší jen v tisícinách).
- Synergy a Counter jsou počty shod v seznamech o třech jménech (0, 1, 2).
  Counter je obráceně: počítá `WeakAgainst` kandidáta, ale TOPSIS ho bere jako přínos (ověřeno v kódu).
- Hrdina má jedinou roli, takže flex picky (Sett, Sylas, Viktor) nejdou doporučit v jiné roli.
- Data jsou statická, ručně z LeagueOfGraphs, jehož podmínky zakazují automatizovaný sběr.
- Mastery s váhou 0,391 řídí pořadí, ale měří odehraný čas, ne výkon. Chybí validace proti baseline.

## Vstupy: co lze získat a co ne

Vše podstatné jde získat z oficiálního Riot API a Data Dragonu. Chybí jen pořadí picků hráčů,
to se z ranked dat naučit nedá.

| Zdroj | Co dává | Omezení | Použití v modelu |
| --- | --- | --- | --- |
| account-v1 | Riot ID na PUUID | žádné | identifikace hráče |
| champion-mastery-v4 | mastery body po hrdinech | měří odehraný čas, ne výkon | prior komfortu |
| league-exp-v4 | seznamy hráčů podle tieru a divize | method limit nelze ověřit z dokumentace | vzorkování zápasů podle ranku |
| match-v5 | hrdina, teamPosition, výhra, bany s pickTurn, gameVersion, timeline | bez pořadí picků hráčů; teamPosition občas prázdná nebo INVALID | winrate, matchupy, duo, osobní profil |
| Data Dragon | seznam hrdinů, tagy, ikony, lokalizace cs_CZ | aktualizuje se po patchi s prodlevou | UI, hrubý profil hrdinů |
| Oracle's Elixir, Leaguepedia | profesionální drafty s pořadím | jen pro-scéna; v 2026 chyby a výpadky dat | volitelná studie efektu pořadí picků |

Praktická omezení:

- Development key vyprší po 24 hodinách a má limit 20 požadavků za sekundu a 100 za 2 minuty.
  Pro dlouhodobý sběr je vhodný registrovaný personal key.
- Veřejné nasazení s personal nebo development klíčem je zakázané, potřebuje production key.
- Agregátory (LeagueOfGraphs, OP.GG, U.GG, Lolalytics) automaticky nesbírat.
- Pro odhad winrate s přesností ±2 procentní body je potřeba zhruba 2 400 zápasů (binomická aproximace).
  Matchupy a dua potřebují řádově víc, proto je vyhlazení nutnost.

## Doporučený model

Dvouvrstvý hybrid: spodní vrstva počítá kritéria jako odchylky pravděpodobnosti výhry,
horní vrstva (MCDM) je skládá s preferencemi hráče a vysvětluje pořadí.
Čistě prediktivní model (gradient boosting, transformer) se jako hlavní metoda nepoužije:
draft vysvětluje jen malou část výsledku (přesnost před hrou kolem 55 až 60 %) a hůř se vysvětluje.

| Kritérium | Co měří | Jednotka | Vyhlazení |
| --- | --- | --- | --- |
| A, síla hrdiny | winrate hrdiny v roli, patchi a ranku | odchylka v log-odds od průměru role | beta-binomické empirical Bayes |
| B, counter | součet matchupových odchylek proti známým nepřátelům, vyšší váha lajnovému soupeři | log-odds | shrinkage k nule |
| C, synergie | duo odchylka oproti očekávání z individuálních sil | log-odds | shrinkage k nule |
| D, osobní forma | winrate hráče na hrdinovi s časovým útlumem | log-odds | hierarchicky k hrdinovi; prior pro nehrané hrdiny |
| E, komfort | log(1 + mastery) se saturací a nedávnost hraní | min-max vůči fixním hranicím | žádné |
| F, vyváženost | přírůstek kvality týmového profilu (AD/AP, frontline, CC) po přidání kandidáta | min-max | žádné |
| G, meta (volitelné) | popularita jako slabý signál bezpečnosti | min-max | žádné |

Kritéria A až D jsou ve stejné jednotce, takže jdou sčítat jako odhad změny pravděpodobnosti výhry.
E až G nesou preference a komfort.

**Agregace**

- TOPSIS s fixními ideály z celého poolu role a patche (ne z aktuální nabídky) je hlavní výstup.
  Zabanování hrdiny pak nepřehodí pořadí ostatních.
- PROMETHEE II a VIKOR slouží jako kontrola robustnosti. VIKOR navíc trestá kandidáta s jednou
  katastrofální slabinou (hard counter). Shodu pořadí měřit Spearmanovým ρ.
- Vedle toho prostý součet A až D jako odhad výhry a volitelně regularizovaná logistická regrese
  jako referenční model a zdroj vah.

**Váhy**

- Výchozí váhy z AHP s kontrolou CR < 0,1, nebo z BWM (9 porovnání místo 15 u šesti kritérií),
  doplněné koeficienty z logistické regrese.
- Dynamika podle fáze draftu: při 0 známých nepřátelích nižší váha B a vyšší „blind-safety“
  (nízký rozptyl matchupových odchylek), při last picku vyšší B.
  Lineární interpolace podle počtu známých nepřátel 0 až 5.
- Nejistota vah: SMAA-2 nebo Monte Carlo s Dirichletovým rozdělením kolem AHP vah.
  Výstupem je pravděpodobnost, že kandidát skončí v top 5.

**Odložit do diskuse:** MCTS, reinforcement learning, DraftRec a embeddingy hrdinů
(potřebují řádově víc dat a jsou hůř interpretovatelné). ELECTRE má složitou parametrizaci
a hodí se pro částečné uspořádání, ne pro seznam top 5.

Pravidlo Riotu: hodnotit se smí hrdinové a kombinace, ne hráči. Žádné MMR ani Elo skóre hráčů.

## Jak to bude fungovat

Hráč zadá Riot ID, region, roli a stav draftu a dostane top 5 hrdinů se zdůvodněním a údajem o nejistotě.

1. **Vstup:** Riot ID s regionem, role, spoluhráči a nepřátelé (hrdina a role), bany.
   Z počtu známých nepřátel se odvodí fáze draftu.
2. **Kandidáti:** hrdinové životaschopní v dané roli (podíl her v roli nad prahem, např. 5 %),
   bez zabanovaných a už vybraných.
3. **Profil hráče:** poslední ranked hry z match-v5 a mastery z champion-mastery-v4, v cache na 10 až 30 minut.
4. **Kritéria A až F:** A, B, C a F se čtou z předpočítaných agregací pro aktuální patch a rank,
   D se počítá z profilu hráče, E z mastery.
5. **Váhy:** výchozí z AHP nebo BWM, upravené podle fáze draftu a posuvníků hráče.
6. **Agregace:** TOPSIS s fixními ideály jako hlavní pořadí, PROMETHEE II a VIKOR jako kontrola,
   SMAA pro stabilitu pořadí.
7. **Výstup:** top 5 s rozpadem příspěvků jednotlivých kritérií, krátkým textem „proč“, počtem zápasů
   a šířkou intervalu u každého čísla, podílem simulací, v nichž kandidát zůstal v top 5,
   a patchem s datem snapshotu dat.

## Architektura

Osm komponent v offline a online části:

- **Offline:** Data Dragon (hrdinové, tagy) → sběr hráčů (league-exp-v4) → sběr zápasů (match-v5)
  s kontrolami kvality a karanténou → agregace podle patche, role a ranku (empirical Bayes, matchupy, dua)
  → databáze agregací.
- **Online:** Flask API (čte jen agregace a profil hráče z cache) → model (kritéria, váhy, TOPSIS,
  kontrolní metody, SMAA) → React UI.

Datovou pipeline spouští plánovač (nebo ručně) mimo provoz aplikace. API při dotazu čte jen
předpočítané agregace z databáze a profil hráče z cache, takže odpověď nezávisí na rate limitu Riot API.

Pro lokální prototyp stačí SQLite a jeden proces. Redis, Docker, PostgreSQL ani production key se nepotřebují.

## Kontroly kvality dat

Kontroly jsou cílené na místa, kde by chyba v datech změnila doporučení. Žádný velký framework,
ale každá kontrola má jasné pravidlo a jasný následek.

| Kontrola | Kde | Pravidlo | Při selhání |
| --- | --- | --- | --- |
| Duplicity | stahování | jeden záznam na `matchId`; stejný zápas přijde z historie více hráčů | přeskočit, započítat do reportu |
| Remaky a předčasné surrendery | stahování | `gameEndedInEarlySurrender` nebo velmi krátká hra | do karantény |
| Fronta a patch | stahování | jen ranked solo (queue 420), `gameVersion` vyplněná | do karantény |
| Úplnost zápasu | stahování | 10 hráčů, 5 unikátních rolí na tým, žádná prázdná nebo INVALID `teamPosition` | do karantény |
| Platnost hrdinů | stahování | ID hrdiny existuje v Data Dragonu pro daný patch | do karantény |
| Minimální vzorek | agregace | práh počtu her pro winrate hrdiny, výrazně vyšší pro matchupy a dua; pod prahem jen vyhlazená hodnota a příznak „málo dat“ | nezobrazovat surový winrate |
| Sanity checky | agregace | celkový winrate kolem 50 %, rozumný poměr blue/red, rozložení ranků odpovídá vzorkování | varování v reportu |
| Mix patchů | agregace | agregace jen z aktuálního patche, případně se snižující vahou starších | varování, pokud je aktuálního patche málo |
| Konzistence vah | model | AHP: reciproční matice a CR < 0,1 | odmítnout váhy, nepočítat |
| Vstupy TOPSIS | model | žádné chybějící hodnoty, kritérium s nulovým rozptylem vyřadit (dělení nulou) | vyřadit kritérium, zalogovat |

**Jak to zavést**

- Validace schématu odpovědí z Riot API (pydantic), kontroly tabulek před agregací (pandera nebo
  pár vlastních funkcí). Great Expectations je pro lokální prototyp zbytečně těžký.
- Vadné záznamy se neodhazují potichu. Jdou do tabulky karantény v SQLite s `matchId` a důvodem.
- Po každém běhu pipeline krátký report: kolik zápasů přišlo, kolik prošlo, kolik vypadlo a proč,
  a varování ze sanity checků. Report se uloží k datům snapshotu.
- Každá kontrola má pytest s malým testovacím vzorkem, včetně záměrně vadných zápasů.

**Priorita:** deduplikace, vyřazení remaků a minimální vzorek u matchupů a du.

## Fáze realizace (orientační)

Pořadí práce určují milníky v CLAUDE.md. Tabulka ukazuje obsah jednotlivých částí.

| Fáze | Co se dělá | Výstup |
| --- | --- | --- |
| Oprava metodiky | reciproční AHP s CR (nebo BWM), Balance jako přírůstek, winrate v log-odds, citlivostní analýza, srovnání TOPSIS, VIKOR a PROMETHEE II | model v2 a srovnání pořadí proti v1 |
| Datová pipeline | league-exp-v4, pak match-v5 do SQLite, kontroly kvality s karanténou, agregace podle patche, role a ranku, empirical Bayes, matchupy a dua s minimálním vzorkem, tabulka hrdina × role | databáze agregací pro aktuální patch a report kvality dat |
| Osobní profil | winrate hráče z match-v5 s útlumem, hierarchické vyhlazení, prior pro nehrané hrdiny | kritéria D a E z reálných dat |
| Validace | referenční logistická regrese, kalibrace, backtest na novějším patchi, baseline, SMAA | tabulka metrik a graf stability pořadí |
| Architektura a UX | oddělení pipeline a API, cache, konfigurace přes proměnné prostředí, ikony z Data Dragonu, vysvětlení doporučení, blokace vybraných hrdinů, chybové stavy | použitelná aplikace |
| Volitelně | pořadí picků z profesionálních dat, MCTS jako experiment | kapitola do diskuse |

Datová pipeline je nejdelší a omezuje ji rate limit klíče (development key: hodiny až dny sběru).

## Validace a evaluace

Model se testuje na zápasech z novějšího patche, než ze kterých jsou spočítané agregace.
Náhodné míchání přes patche by do testu pustilo informace o metě.

**Baseline:** nejvyšší vyhlazený winrate v roli; nejhranější hrdina v roli;
hrdina s nejvyšší mastery hráče; původní model v1 z diplomky (jen jako srovnávací funkce).

**Metriky**

- Predikce výhry: log-loss, Brier skóre, AUC a reliability diagram (kalibrace).
- Doporučení: hit@k, tedy zda byl skutečný pick v top k. Měří shodu s chováním hráčů, ne optimalitu.
- Průměrná predikovaná pravděpodobnost výhry doporučených picků proti skutečným podle referenčního modelu.
- Winrate zápasů, kde byl skutečný pick v top k, proti ostatním (korelace, ne kauzální efekt).
- Citlivost: stabilita top 5 vůči vahám (SMAA), normalizaci a síle priorů;
  shoda pořadí metod přes Spearmanovo ρ nebo Kendallovo τ.

**Na co si dát pozor**

- Data leakage: agregace jen ze zápasů před testovacím obdobím, osobní profil jen z her před daným zápasem.
- Survivorship bias: data obsahují jen to, co hráči zvolili, takže hit@k neznamená „správně“.
- Očekávaná přesnost predikce výhry z draftu je jen 52 až 60 %. Hodnota modelu je v kalibrovaných
  malých rozdílech, ne ve vysoké přesnosti.

## Rozhodnutí a stav (aktualizováno 24. 10. 2026)

- [x] Rozsah: osobní prototyp lokálně na mém PC. Cíl je naučit se Claude Code a vyzkoušet, co AI zvládne.
  Diplomová práce se nemění a nový výzkum se nedělá.
- [x] Nová verze vzniká od nuly. Původní kód je jen inspirace a srovnávací baseline.
- [x] Live integrace s klientem hry se odkládá, draft se zadává ručně.
- [x] Původní kód a `champions.json` existují (`C:\Users\SaltyAndTilted\lol-topsis-project`,
  spustitelná kopie v `C:\projekty\lol-draft`).
- [x] Riot API: development key funguje (načtení profilu přes account-v1 a champion-mastery-v4 ověřeno).
  Platí 24 hodin.
- [ ] Region a rank: EUNE. Hráč už roky nehraje, osobní historie bude nejspíš stará nebo prázdná.
  Ověřit na prototypu, případně testovat s jiným veřejným účtem.
