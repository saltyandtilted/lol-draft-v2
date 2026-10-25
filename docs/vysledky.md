# Výsledky backtestu modelu v2

Vygenerováno 2026-10-25 09:16 UTC příkazem `python -m model.backtest`.
Agregace jen z patche **16.20** (456 zápasů), test na patchi **16.21** (592 zápasů). Testovací zápasy do agregací nevstoupily (kontrola v kódu i v testu).
Testuje se jen draftová část modelu (A, B, C, S, F); osobní kritéria D a E a baseline „nejvyšší mastery“ ne, protože databáze nemá historii hráčů a dnešní mastery by do testu pustilo budoucnost.

## Shrnutí

- **Predikce výhry:** od konstanty se neliší průkazně (AUC 0.529, interval zlepšení log-loss obsahuje nulu).
- **Shoda s picky hráčů proti „nejvyšší vyhlazený winrate“:** rozdíl není průkazný (hit@5 v2 minus baseline +0.5 pb).
- **Shoda s picky hráčů proti „nejhranější v roli“:** v2 je průkazně horší (hit@5 v2 minus baseline -10.5 pb).
- **Shoda s picky hráčů proti „v1 (diplomka)“:** rozdíl není průkazný (hit@5 v2 minus baseline -1.2 pb).
- **Kvalita doporučení:** #1 od v2 byl na novém patchi zhruba stejně silný (rozdíl není průkazný) jako skutečný pick (+0.02 pb).

## 1. Predikce výhry z draftu

| Model | log-loss | Brier | AUC | přesnost |
| --- | --- | --- | --- | --- |
| konstanta (winrate modré strany) | 0.6926 | 0.2497 | 0.500 | 52.0% |
| v2: jen A (síla hrdiny) | 0.6928 | 0.2498 | 0.506 | 50.7% |
| v2: A+B+C (bez fitování) | 0.6916 | 0.2492 | 0.529 | 53.9% |
| v2: logistická regrese na A, B, C (cross-fit) | 0.6945 | 0.2507 | 0.472 | 47.3% |

Nižší log-loss a Brier jsou lepší, AUC 0,5 je náhoda. Plán čeká přesnost jen 52 až 60 %.
Zlepšení log-loss A+B+C proti konstantě: +0.0010 (90% interval -0.0022 až +0.0042); kladné = v2 je lepší.
Regrese je cross-fit: agregace z poloviny tréninkových zápasů, koeficienty fitované na druhé polovině. Koeficienty: A -0.22, B -0.12, C 0.00, intercept -0.000 (koeficient 1 = kritérium je škálované přesně).

![Kalibrace](img/kalibrace.png)

## 2. Doporučení: byl skutečný pick mezi doporučenými?

592 draftů z testovacích zápasů: jeden hráč, náhodná část spoluhráčů, 0, 2 nebo 5 známých nepřátel, skutečné bany.

| Metoda | pokrytí | hit@1 | hit@5 | hit@10 | MRR | síla #1 na novém patchi | síla top 5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2 | 96.6% | 3.5% | 18.4% | 29.4% | 0.119 | +0.08 pb | +0.21 pb |
| nejvyšší vyhlazený winrate | 96.6% | 4.9% | 17.9% | 29.9% | 0.127 | +0.13 pb | +0.22 pb |
| nejhranější v roli | 96.6% | 9.0% | 28.9% | 41.9% | 0.201 | +0.39 pb | +0.06 pb |
| v1 (diplomka) | 73.5% | 2.5% | 19.6% | 34.8% | 0.122 | -0.02 pb | +0.07 pb |

- **Pokrytí:** skutečný pick je mezi kandidáty metody (v2 a obě baseline mají stejný pool: hrdinové s aspoň 5 % her v roli na tréninkovém patchi; v1 má vlastní seznam rolí).
- **hit@k** měří shodu s tím, co hráči opravdu vybrali, ne optimalitu (survivorship bias).
- **Síla na novém patchi:** vyhlazený winrate hrdiny v roli spočítaný z testovacího patche (v procentních bodech proti průměru role). Ukazuje, jestli doporučený hrdina byl silný i v datech, která model neviděl.

Rozdíly hit@5 proti v2 (párově na stejných draftech, bootstrap):

- v2 − nejvyšší vyhlazený winrate: +0.5 pb (90% interval -1.0 až +2.2 pb)
- v2 − nejhranější v roli: -10.5 pb (90% interval -14.2 až -7.1 pb)
- v2 − v1 (diplomka): -1.2 pb (90% interval -4.7 až +2.4 pb)

Síla #1 na novém patchi minus síla skutečného picku:

- v2: +0.02 pb (90% interval -0.10 až +0.13 pb)
- nejvyšší vyhlazený winrate: +0.06 pb (90% interval -0.04 až +0.15 pb)
- nejhranější v roli: +0.32 pb (90% interval +0.20 až +0.46 pb)
- v1 (diplomka): -0.08 pb (90% interval -0.21 až +0.03 pb)

![hit@k](img/hit-at-k.png)

hit@5 podle počtu známých nepřátel:

| Metoda | 0 nepřátel | 2 nepřátel | 5 nepřátel |
| --- | --- | --- | --- |
| v2 | 14.6% | 21.8% | 18.8% |
| nejvyšší vyhlazený winrate | 13.1% | 22.3% | 18.3% |
| nejhranější v roli | 24.2% | 32.5% | 29.9% |
| v1 (diplomka) | 22.2% | 16.8% | 19.8% |

Winrate hráčů, jejichž pick byl v top 5 v2: 47.7% (109 draftů), ostatní: 52.4% (483). Je to korelace, ne kauzální efekt.

## 3. Citlivost

**Nejistota vah (SMAA, 100 draftů):** hrdina z top 5 v ní zůstal průměrně v 94.8% simulací, 89.6% doporučení má stabilitu aspoň 80 %.
**Kontrolní metody:** průměrné Spearmanovo ρ s TOPSIS: PROMETHEE II 0.82, VIKOR 0.96.

![SMAA](img/smaa-stabilita.png)

**Jiné AHP matice** (E má s prázdným profilem nulový rozptyl a vypadne, rozhoduje poměr W a F):

| Varianta | váhy W / E / F | CR | průměrná shoda top 5 | stejná #1 | hit@5 |
| --- | --- | --- | --- | --- | --- |
| výchozí AHP (7:1, 6:1) | 0.76 / 0.11 / 0.12 | 0.002 | 5.0 z 5 | 100.0% | 18.4% |
| W slabší (3:1) | 0.60 / 0.20 / 0.20 | 0.000 | 4.1 z 5 | 73.5% | 15.9% |
| W silnější (9:1) | 0.82 / 0.09 / 0.09 | 0.000 | 4.8 z 5 | 94.4% | 17.9% |

**Síla priorů matchupů a du** (násobek `PRIOR_SD`; 0,5 = víc shrinkage, 2 = méně):

| Násobek | log-loss A+B+C | AUC | hit@5 v2 |
| --- | --- | --- | --- |
| 1 | 0.6916 | 0.529 | 18.4% |
| 0.5 | 0.6925 | 0.514 | 19.3% |
| 2 | 0.6909 | 0.540 | 15.5% |

## Omezení

- Malý vzorek: tréninkový patch má jen stovky zápasů, většina matchupů a du je pod prahem 30 her,
  takže kritéria B a C drží priory blízko nuly. S víc daty se výsledky mohou změnit.
- hit@k měří shodu s chováním hráčů (survivorship bias), ne to, jestli byl pick nejlepší.
- „Síla na novém patchi“ používá jen kritérium A z testovacích dat; je to rozumná, ale ne úplná
  reference (neobsahuje matchupy ani synergie). Vyhlazení navíc méně stahuje k nule často hrané
  hrdiny, takže reference mírně zvýhodňuje baseline „nejhranější v roli“.
- D (osobní forma) a E (komfort) nejsou testované; jejich váhy zůstávají expertní (AHP).
- Pořadí picků v ranked datech není, drafty jsou rekonstruované náhodným výběrem známých hrdinů.

