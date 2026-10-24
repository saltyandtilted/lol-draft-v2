# Brainstorm: co zachovat a co změnit (milník 1)

Stav k 24. 10. 2026. Vychází z kódu v1 (`lol-topsis-project`, `lol-topsis-backend`),
diplomky (kap. 4.2–4.5, 5 a 6.1) a z docs/plan.md.
Cíl je funkční stránka, ne nová diplomka.

## Jak fungovala v1

1. Statický `champions.json` (167 hrdinů, data ručně z LeagueOfGraphs): jedna role na hrdinu,
   winrate, popularita, ban rate, AD/AP a seznamy po 3 jménech (StrongAgainst, WeakAgainst, GoodWith).
2. Riot ID → PUUID → mastery body (account-v1, champion-mastery-v4).
3. Kandidáti = hrdinové role bez banů a picků. Šest kritérií: Popularity, Winrate,
   Mastery (log(1+x)), Synergy a Counter (počty shod v seznamech), Balance (AD/AP v týmu).
4. TOPSIS s L2 normalizací a ideály z aktuální nabídky, váhy z posuvníků
   (výchozí ze Saatyho matice), výstup top 5.
5. UI: React (Create React App) + Bootstrap, rozbalovací seznamy pro picky a bany.

## Co zachovat

- Tok vstupů: Riot ID → role → picky a bany → top 5.
- Kombinace obecných dat o hrdinech s osobními daty hráče.
- TOPSIS jako hlavní agregace (problém byl ve vstupech, ne v metodě).
- Myšlenka z diplomky (scénář 3): při first picku nemá smysl řešit counter a synergii.
  V2 to dělá automaticky přes dynamiku vah podle fáze draftu.

## Co změnit (ověřeno v kódu a v diplomce)

| Problém v1 | Důkaz | Řešení ve v2 |
| --- | --- | --- |
| Saatyho matice nereciproční, bez CR | Popularity–Winrate: 1/7 vs. 5; CR = 0,106 (po opravě 0,11–0,12) | váhy se počítají metodou s kontrolou, viz Rozhodnutí 1 |
| Mastery řídí pořadí (váha 0,391) | diplomka kap. 5, scénář 2 | mastery jen jako komfort (E) s nízkou vahou, výkon nese D |
| Balance stejná pro všechny | spoluhráči se hledají mezi kandidáty → počet AD vždy 0 | F = přírůstek kvality týmového profilu po přidání kandidáta |
| Counter obráceně | WeakAgainst bráno jako přínos, StrongAgainst nepoužito | B = matchupové odchylky v log-odds z vlastních dat |
| Winrate nerozlišuje | rozsah 44,3–53,5 %, po L2 rozdíly v tisícinách | A = log-odds vůči průměru role, empirical Bayes |
| Ideály TOPSIS z aktuální nabídky | ban jednoho hrdiny mění pořadí ostatních | fixní ideály z celého poolu role a patche |
| Jedna role na hrdinu | pole `Position` | role podle podílu her v roli (flex picky) |
| Statická scrapovaná data | LeagueOfGraphs, OP.GG scraper | vlastní pipeline z Riot API |
| API klíče natvrdo v kódu | `app.py`, `app2.py` (staré, vypršelé) | klíč jen v `.env` |

## Rozhodnutí

1. **Bez posuvníků vah.** Váhy počítá model sám:
   - A až D (odchylky šance na výhru v log-odds): váhy z regularizované logistické regrese
     na vlastních zápasech, tedy z dat, ne z odhadu.
   - E a F (komfort, vyváženost): malá AHP matice s povinnou kontrolou CR < 0,1.
   - Dynamika podle fáze draftu (0 až 5 známých nepřátel) zůstává automatická.
2. **Sběr dat přes všechny ranky** s možností omezit rank při agregaci a v UI.
3. **Testovací účet:** zatím autorův vlastní (EUNE). Jiný veřejný účet jen v případě,
   že stará historie nestačí na kritérium D.
4. **UI anglicky** (Data Dragon `en_US`).
5. **Žádné výzkumné navíc:** scénáře z diplomky se nepřepisují do testů.
   Priorita je funkční stránka.
6. **Metody podle plánu, nejvhodnější varianty:** kontrolní metody (PROMETHEE II, VIKOR),
   nejistota vah (SMAA) a validace proti baseline zůstávají tak, jak jsou v docs/plan.md.
   Slouží kvalitě doporučení, ne výzkumu.

## Dodatek z milníku 4 (24. 10. 2026)

- **Úprava rozhodnutí 1: stejné váhy A až D.** Na 554 zápasech jsou koeficienty logistické
  regrese nespolehlivé. A až D mají stejnou jednotku (log-odds), takže stejné váhy jsou totéž
  co jejich součet: W = A + B + C + D + λ·S je odhad změny šance na výhru. Regrese zůstává jako
  diagnostika (`model/regression.py`); jako zdroj vah ji zvážíme v milníku 6.
- **TOPSIS skládá tři cíle {W, E, F}, ne sedm kritérií.** S A až D jako samostatnými kritérii
  plná mastery přebila rozdíl síly hrdinů zhruba o 7 p. b. (chyba v1 by se opakovala). AHP
  matice teď porovnává rozsahy (swing weighting): plný komfort odpovídá asi 3 až 4 p. b.
- **Blind safety S** = −rozptyl matchupových odchylek, vyhlazený k průměru role (jinak by
  málo dat vypadalo jako bezpečný pick). λ klesá z 0,5 při 0 známých nepřátelích na 0 při 5.
- **Vyváženost F** se násobí podílem známých spoluhráčů (m/4); bez spoluhráčů je 0.
- **Profil pro F** je ze statistik zápasů (poškození, utržené a zmírněné poškození, čas CC).
- **Priory matchupů a du podle realistické velikosti efektu:** lajnový matchup sd 0,15,
  mimolajnový 0,05, duo 0,07 log-odds. Původní shrinkage k = 50 her (sd ≈ 0,28) nechal
  součet šumu z párů s 1 až 2 hrami přebít sílu hrdiny.
