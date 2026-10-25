# Výsledky backtestu modelu v2

Vygenerováno 2026-10-25 12:37 UTC příkazem `python -m model.backtest`.
Agregace jen z patche **16.20** (1530 zápasů), test na patchi **16.21** (1499 zápasů). Testovací zápasy do agregací nevstoupily (kontrola v kódu i v testu).
Testuje se jen draftová část modelu (A, B, C, S, F); osobní kritéria D a E a baseline „nejvyšší mastery“ ne, protože databáze nemá historii hráčů a dnešní mastery by do testu pustilo budoucnost.

## Shrnutí

- **Predikce výhry:** od konstanty se neliší průkazně (AUC 0.508, interval zlepšení log-loss obsahuje nulu).
- **Shoda s picky hráčů proti „nejvyšší vyhlazený winrate“:** rozdíl není průkazný (hit@5 v2 minus baseline -0.6 pb).
- **Shoda s picky hráčů proti „nejhranější v roli“:** v2 je průkazně horší (hit@5 v2 minus baseline -14.1 pb).
- **Shoda s picky hráčů proti „v1 (diplomka)“:** v2 je průkazně horší (hit@5 v2 minus baseline -5.9 pb).
- **Kvalita doporučení:** #1 od v2 byl na novém patchi průkazně silnější než skutečný pick (+0.15 pb).

## 1. Predikce výhry z draftu

| Model | log-loss | Brier | AUC | přesnost |
| --- | --- | --- | --- | --- |
| konstanta (winrate modré strany) | 0.6924 | 0.2496 | 0.500 | 52.0% |
| v2: jen A (síla hrdiny) | 0.6972 | 0.2520 | 0.490 | 49.3% |
| v2: A+B+C (bez fitování) | 0.6958 | 0.2513 | 0.508 | 50.8% |
| v2: logistická regrese na A, B, C (cross-fit) | 0.6924 | 0.2496 | 0.512 | 52.0% |

Nižší log-loss a Brier jsou lepší, AUC 0,5 je náhoda. Plán čeká přesnost jen 52 až 60 %.
Zlepšení log-loss A+B+C proti konstantě: -0.0034 (90% interval -0.0075 až +0.0006); kladné = v2 je lepší.
Regrese je cross-fit: agregace z poloviny tréninkových zápasů, koeficienty fitované na druhé polovině. Koeficienty: A -0.36, B 0.10, C -0.24, intercept -0.113 (koeficient 1 = kritérium je škálované přesně).

![Kalibrace](img/kalibrace.png)

## 2. Doporučení: byl skutečný pick mezi doporučenými?

1499 draftů z testovacích zápasů: jeden hráč, náhodná část spoluhráčů, 0, 2 nebo 5 známých nepřátel, skutečné bany.

| Metoda | pokrytí | hit@1 | hit@5 | hit@10 | MRR | síla #1 na novém patchi | síla top 5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2 | 96.7% | 3.2% | 12.6% | 23.7% | 0.100 | +0.11 pb | -0.09 pb |
| nejvyšší vyhlazený winrate | 96.7% | 3.0% | 13.2% | 23.1% | 0.100 | -0.02 pb | -0.01 pb |
| nejhranější v roli | 96.7% | 7.0% | 26.7% | 43.4% | 0.184 | -0.42 pb | -0.04 pb |
| v1 (diplomka) | 74.5% | 3.1% | 18.5% | 36.2% | 0.125 | +0.12 pb | -0.01 pb |

- **Pokrytí:** skutečný pick je mezi kandidáty metody (v2 a obě baseline mají stejný pool: hrdinové s aspoň 5 % her v roli na tréninkovém patchi; v1 má vlastní seznam rolí).
- **hit@k** měří shodu s tím, co hráči opravdu vybrali, ne optimalitu (survivorship bias).
- **Síla na novém patchi:** vyhlazený winrate hrdiny v roli spočítaný z testovacího patche (v procentních bodech proti průměru role). Ukazuje, jestli doporučený hrdina byl silný i v datech, která model neviděl.

Rozdíly hit@5 proti v2 (párově na stejných draftech, bootstrap):

- v2 − nejvyšší vyhlazený winrate: -0.6 pb (90% interval -1.5 až +0.3 pb)
- v2 − nejhranější v roli: -14.1 pb (90% interval -16.3 až -11.9 pb)
- v2 − v1 (diplomka): -5.9 pb (90% interval -8.0 až -3.7 pb)

Síla #1 na novém patchi minus síla skutečného picku:

- v2: +0.15 pb (90% interval +0.01 až +0.29 pb)
- nejvyšší vyhlazený winrate: +0.02 pb (90% interval -0.10 až +0.14 pb)
- nejhranější v roli: -0.38 pb (90% interval -0.46 až -0.30 pb)
- v1 (diplomka): +0.16 pb (90% interval +0.05 až +0.27 pb)

![hit@k](img/hit-at-k.png)

hit@5 podle počtu známých nepřátel:

| Metoda | 0 nepřátel | 2 nepřátel | 5 nepřátel |
| --- | --- | --- | --- |
| v2 | 12.0% | 12.4% | 13.4% |
| nejvyšší vyhlazený winrate | 12.8% | 12.2% | 14.6% |
| nejhranější v roli | 27.8% | 28.4% | 23.8% |
| v1 (diplomka) | 21.4% | 17.2% | 16.8% |

Winrate hráčů, jejichž pick byl v top 5 v2: 49.7% (189 draftů), ostatní: 48.5% (1310). Je to korelace, ne kauzální efekt.

## 3. Citlivost

**Nejistota vah (SMAA, 100 draftů):** hrdina z top 5 v ní zůstal průměrně v 97.9% simulací, 95.4% doporučení má stabilitu aspoň 80 %.
**Kontrolní metody:** průměrné Spearmanovo ρ s TOPSIS: PROMETHEE II 0.94, VIKOR 0.99.

![SMAA](img/smaa-stabilita.png)

**Jiné AHP matice** (E má s prázdným profilem nulový rozptyl a vypadne, rozhoduje poměr W a F):

| Varianta | váhy W / E / F | CR | průměrná shoda top 5 | stejná #1 | hit@5 |
| --- | --- | --- | --- | --- | --- |
| výchozí AHP (7:1, 6:1) | 0.76 / 0.11 / 0.12 | 0.002 | 5.0 z 5 | 100.0% | 12.6% |
| W slabší (3:1) | 0.60 / 0.20 / 0.20 | 0.000 | 4.5 z 5 | 85.6% | 12.9% |
| W silnější (9:1) | 0.82 / 0.09 / 0.09 | 0.000 | 4.9 z 5 | 97.7% | 12.9% |

**Síla priorů matchupů a du** (násobek `PRIOR_SD`; 0,5 = víc shrinkage, 2 = méně):

| Násobek | log-loss A+B+C | AUC | hit@5 v2 |
| --- | --- | --- | --- |
| 1 | 0.6958 | 0.508 | 12.6% |
| 0.5 | 0.6967 | 0.495 | 13.3% |
| 2 | 0.7004 | 0.524 | 13.3% |

## Omezení

- Malý vzorek: tréninkový patch má jen stovky zápasů, většina matchupů a du je pod prahem 30 her,
  takže kritéria B a C drží priory blízko nuly. S víc daty se výsledky mohou změnit.
- hit@k měří shodu s chováním hráčů (survivorship bias), ne to, jestli byl pick nejlepší.
- „Síla na novém patchi“ používá jen kritérium A z testovacích dat; je to rozumná, ale ne úplná
  reference (neobsahuje matchupy ani synergie). Vyhlazení navíc méně stahuje k nule často hrané
  hrdiny, takže reference mírně zvýhodňuje baseline „nejhranější v roli“.
- D (osobní forma) a E (komfort) nejsou testované; jejich váhy zůstávají expertní (AHP).
- Pořadí picků v ranked datech není, drafty jsou rekonstruované náhodným výběrem známých hrdinů.

