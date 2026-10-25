# Srovnání pořadí v1 a v2

Vygenerováno 2026-10-25 08:46 UTC příkazem `python -m model.compare`.
Data: patch 16.21 (váhy patchů {'16.21': 1.0, '16.20': 0.5}), 1048 zápasů, agregace z 2026-10-24T19:40:47+00:00.

Nejde o validaci: agregace jsou ze stejných zápasů, ze kterých jsou drafty, takže pořadí
skutečného picku je optimistické. Backtest na novějším patchi je v docs/vysledky.md.

## Top 5 na stejných draftech

| Draft | v1 top 5 | v2 top 5 | shoda | ρ (celé pořadí) | skutečný pick | pořadí v1 / v2 |
| --- | --- | --- | --- | --- | --- | --- |
| EUN1_4019374713 (TOP, 5 enemies) | Olaf, Sion, Poppy, Garen, Sett | Sett, Urgot, Vayne, Teemo, Aurora | 1/5 | -0.15 | Gwen | 21 / 77 |
| EUN1_4019375193 (JUNGLE, 2 enemies) | Sejuani, Fiddlesticks, Nunu & Willump, Karthus, Rammus | Cho'Gath, Kayn, Elise, Rengar, Viego | 0/5 | -0.07 | Jax | není / 18 |
| EUN1_4019371598 (MIDDLE, 0 enemies) | Ryze, Lux, Yone, Yasuo, Viktor | Hwei, Malzahar, Aurora, Mel, Lux | 1/5 | -0.17 | Mel | není / 4 |
| EUN1_4019370244 (BOTTOM, 5 enemies) | Aphelios, Tristana, Kog'Maw, Xayah, Ezreal | Lucian, Jhin, Aphelios, Kog'Maw, Sivir | 2/5 | -0.00 | Lucian | 13 / 1 |
| EUN1_4019365314 (UTILITY, 2 enemies) | Renata Glasc, Thresh, Karma, Nami, Nautilus | Janna, Morgana, Lux, Fiddlesticks, Alistar | 0/5 | -0.11 | Leona | 8 / 56 |
| EUN1_4019361865 (TOP, 0 enemies) | Garen, Darius, Sett, Aatrox, Cho'Gath | Sett, Dr. Mundo, Tryndamere, Vayne, Nasus | 1/5 | -0.00 | Jayce | 8 / 84 |
| EUN1_4019362846 (JUNGLE, 5 enemies) | Lee Sin, Master Yi, Warwick, Kha'Zix, Fiddlesticks | Cho'Gath, Briar, Kayn, Elise, Viego | 0/5 | -0.14 | Ekko | není / 8 |
| EUN1_4019364325 (MIDDLE, 2 enemies) | Galio, Vladimir, Malzahar, Azir, Lux | Hwei, Malzahar, Aurora, Sylas, Lux | 2/5 | -0.08 | Syndra | 15 / 67 |
| EUN1_4019357653 (BOTTOM, 0 enemies) | Samira, Ezreal, Jinx, Kai'Sa, Jhin | Lucian, Jhin, Karthus, Vayne, Kog'Maw | 1/5 | 0.15 | Aphelios | 15 / 13 |
| EUN1_4019354496 (UTILITY, 5 enemies) | Karma, Milio, Taric, Thresh, Nami | Alistar, Janna, Braum, Nautilus, Nami | 1/5 | -0.16 | Braum | 10 / 3 |
| first pick TOP (nothing known) | Garen, Darius, Sett, Aatrox, Cho'Gath | Sett, Vayne, Aurora, Shen, Quinn | 1/5 | 0.06 | - | - |
| mid draft MIDDLE (2 allies, 2 enemies) | Lux, Yone, Sylas, Yasuo, Viktor | Hwei, Orianna, Locke, Nasus, Sylas | 1/5 | -0.19 | - | - |
| last pick TOP vs. Darius, all-AD team | Poppy, Olaf, Garen, Sett, Aatrox | Sett, Vayne, Urgot, Tryndamere, Aurora | 1/5 | -0.03 | - | - |

„není“ = skutečný pick není mezi kandidáty dané verze (jiná role ve v1, pod 5 % her v roli ve v2).

## Stabilita a kontrolní metody v2

| Draft | podíl simulací v top 5 (SMAA) | ρ PROMETHEE II | ρ VIKOR | proč #1 |
| --- | --- | --- | --- | --- |
| EUN1_4019374713 (TOP, 5 enemies) | 100%, 98%, 96%, 100%, 24% | 0.813 | 0.927 | favourable matchups against known enemies; strong in this role on the current patch |
| EUN1_4019375193 (JUNGLE, 2 enemies) | 100%, 99%, 100%, 88%, 87% | 0.732 | 0.937 | improves your team's damage mix, frontline or CC; strong in this role on the current patch |
| EUN1_4019371598 (MIDDLE, 0 enemies) | 100%, 100%, 99%, 95%, 81% | 0.843 | 0.95 | strong in this role on the current patch |
| EUN1_4019370244 (BOTTOM, 5 enemies) | 100%, 100%, 100%, 89%, 44% | 0.836 | 0.964 | strong in this role on the current patch |
| EUN1_4019365314 (UTILITY, 2 enemies) | 100%, 100%, 100%, 100%, 100% | 0.748 | 0.937 | strong in this role on the current patch |
| EUN1_4019361865 (TOP, 0 enemies) | 100%, 100%, 78%, 77%, 58% | 0.716 | 0.909 | improves your team's damage mix, frontline or CC; strong in this role on the current patch |
| EUN1_4019362846 (JUNGLE, 5 enemies) | 100%, 100%, 100%, 89%, 100% | 0.848 | 0.953 | strong in this role on the current patch |
| EUN1_4019364325 (MIDDLE, 2 enemies) | 100%, 100%, 95%, 100%, 91% | 0.755 | 0.921 | strong in this role on the current patch |
| EUN1_4019357653 (BOTTOM, 0 enemies) | 100%, 100%, 80%, 73%, 50% | 0.566 | 0.922 | strong in this role on the current patch; improves your team's damage mix, frontline or CC |
| EUN1_4019354496 (UTILITY, 5 enemies) | 100%, 100%, 100%, 100%, 82% | 0.814 | 0.961 | favourable matchups against known enemies; improves your team's damage mix, frontline or CC |
| first pick TOP (nothing known) | 100%, 100%, 100%, 100%, 100% | 1.0 | 1.0 | strong in this role on the current patch |
| mid draft MIDDLE (2 allies, 2 enemies) | 100%, 100%, 100%, 91%, 100% | 0.825 | 0.957 | strong in this role on the current patch; improves your team's damage mix, frontline or CC |
| last pick TOP vs. Darius, all-AD team | 100%, 99%, 99%, 75%, 67% | 0.769 | 0.929 | favourable matchups against known enemies; strong in this role on the current patch |

## Ban nejlepšího kandidáta (first pick TOP)

| Verze | před banem (1 až 6) | po banu #1 (top 5) | zbytek ve stejném pořadí |
| --- | --- | --- | --- |
| v1 | Garen, Darius, Sett, Aatrox, Cho'Gath, Mordekaiser | Darius, Sett, Aatrox, Cho'Gath, Mordekaiser | ano |
| v2 | Sett, Vayne, Aurora, Shen, Quinn, Nasus | Vayne, Aurora, Shen, Quinn, Nasus | ano |

Ban nejlepšího kandidáta na všech 13 draftech: pořadí ostatních zůstalo ve v1 v 11 případech, ve v2 v 13 případech.

## Diagnostika: logistická regrese výhry na A, B, C (in-sample)

Zápasů: 1048. Koeficienty: A 2.261, B 12.076, C 7.601, intercept 0.014.
Koeficient 1 by znamenal, že kritérium je v log-odds přesně škálované. Hodnoty nad 1 jsou
tu očekávané ze dvou důvodů: vyhlazení odhady záměrně zmenšuje a regrese běží na stejných
zápasech, ze kterých jsou agregace (únik dat). Proto je to jen diagnostika; váhy A až D
zůstávají stejné; regrese na odložených datech je v docs/vysledky.md.

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
