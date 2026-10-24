# Průvodce: LoL draft prototyp s Claude Code

Zkrácená verze dokumentu „Průvodce: LoL draft prototyp s Claude Code“ (Claude Docs, 20. 10. 2026),
upravená podle rozhodnutí z 24. 10. 2026: **nová verze vzniká od nuly**, milník 2 už není
„rekonstrukce v1“, ale kostra nového projektu. Instalace (krok 0) je hotová.

## Stav prostředí (24. 10. 2026)

- Python 3.15, Node.js LTS a Git jsou nainstalované, Git má nastaveného autora.
- Claude Code se spouští v desktopové aplikaci Claude, záložka **Code** → **Local** → složka `C:\projekty\lol-draft-v2`.
- Development key Riot API funguje. Klíč je jen v souboru `.env`, nikdy v chatu ani v kódu.
- Původní aplikace běží jako referenční kopie v `C:\projekty\lol-draft` (backend port 5001, frontend 3000).

## Jak pracovat s Claude Code

Nejlepší výsledky dává cyklus **prozkoumej → naplánuj → proveď → ověř**.

**Režimy oprávnění**

- **Plánovací režim** na začátku každého milníku. Claude jen čte a navrhne plán, nic nemění.
  Plán si přečti a schval.
- **Režim s potvrzováním** první dva milníky. Uvidíš každou změnu a naučíš se, co agent dělá.
- **Auto režim** až budeš rozumět, co se děje, a máš commitnutou funkční verzi.

**Výstupní styl pro učení:** přes `/config` → Output style zapni **Explanatory** (vysvětlující „Insights“).
Na milníku 2 a 3 můžeš vyzkoušet **Learning** (nechá menší části kódu napsat tebe, označí je `TODO(human)`).

**Užitečné příkazy**

| Příkaz | K čemu |
| --- | --- |
| `/init` | Claude projde projekt a navrhne CLAUDE.md; až bude kód, nech ho doplnit |
| `/clear` | vyčistí konverzaci; používej mezi milníky |
| `/compact` | zkrátí dlouhou konverzaci do shrnutí |
| `/context` | ukáže, jak je zaplněná paměť konverzace |
| `/rewind` | vrátí kód i konverzaci k dřívějšímu bodu (checkpoint) |
| `/doctor` | kontrola instalace a nastavení |
| `/skills` | seznam dostupných skills |
| `/usage` | kolik limitu předplatného je vyčerpáno |

**Pravidla, která šetří čas i tokeny**

- Jeden milník, jedno téma. Velké zadání na jeden zátah se rozjede.
- Vždy chtěj ověření: spustit, otestovat, ukázat výstup.
- Po každém funkčním kroku commit („commitni změny s popisnou zprávou“).
- Když se Claude vydá špatným směrem, přeruš ho klávesou Esc a oprav zadání.
- Konkrétní zadání („v `backend/model/topsis.py` …“) místo obecného („oprav doporučování“).
- Ptej se „proč?“. To je hlavní způsob, jak se tu učit.

## Doporučené skills

**Vestavěné, používej od začátku**

| Skill | K čemu | Kdy |
| --- | --- | --- |
| `/doctor` | kontrola instalace a nastavení | při potížích |
| `/run` | spustí aplikaci a ukáže, že změna funguje | po změně backendu nebo UI |
| `/verify` | sestaví a spustí aplikaci, ověří, že změna dělá, co má | před commitem |
| `/debug` | pomoc při hledání chyby | když něco padá |
| `/code-review` | revize změn | na konci milníku |

**Vlastní skills, které si postupně vytvoříš** (do `.claude/skills/<název>/SKILL.md`):

- `refresh-data`: stažení nových zápasů a přepočet agregací (milník 3).
- `explain-recommendation`: vysvětlení konkrétního doporučení přes všechna kritéria (milník 6).
- `new-patch`: postup po vydání nového patche (milník 6).

Na tvorbu skills pomáhá plugin `skill-creator` (instaluj až na milníku 6, jen z oficiálního marketplace).
MCP servery, hooks, subagenty ani agent teams zatím nepotřebuješ.

## Cesta k prototypu: 7 milníků

Každý milník končí něčím, co jde spustit a commitnout.

### Milník 1: Seznámení a brainstorm návrhu
- **Cíl:** Claude zná projekt a spolu zhodnotíte, co bylo v původním návrhu dobře a co ne. Žádný kód.
- **Zadání:** „Jsi v plánovacím režimu. Přečti CLAUDE.md a docs/plan.md. Projdi původní kód
  v `C:\Users\SaltyAndTilted\lol-topsis-project` (jen čtení), shrň, jak aplikace fungovala,
  a pak se mnou proberte, co bylo v návrhu dobře a co bys dnes udělal jinak. Ptej se mě.“
- **Hotovo, když:** v `docs/brainstorm.md` je seznam rozhodnutí, co zachovat a co změnit.
- **Naučíš se:** plánovací režim, CLAUDE.md, jak Claude čte projekt.

### Milník 2: Kostra nového projektu
- **Cíl:** prázdná, ale spustitelná aplikace: Flask backend, React přes Vite, SQLite, pytest.
- **Zadání:** „Podle CLAUDE.md a docs/brainstorm.md navrhni strukturu složek nové verze a pak ji vytvoř:
  Flask backend s endpointem `/api/health`, React (Vite) frontend, který ho zavolá, SQLite, načítání
  klíče z .env, pytest s jedním testem. Doplň sekci Příkazy v CLAUDE.md. Vysvětluj, co který soubor dělá.“
- **Hotovo, když:** běží backend i frontend, frontend ukáže odpověď z backendu, `pytest` projde, je commit.
- **Naučíš se:** virtuální prostředí Pythonu, `npm`, Vite, spouštění dvou procesů, první commity.

### Milník 3: Datová pipeline z Riot API
- **Cíl:** skript stáhne ranked zápasy do SQLite, respektuje rate limity a má kontroly kvality.
- **Zadání:** „Napiš sběrač dat podle docs/plan.md (sekce Vstupy, Architektura, Kontroly kvality dat).
  Začni malým testem na 20 zápasech, pak teprve větší běh. Klíč čti z .env.
  Vysvětli mi, jak funguje rate limiting a proč.“
- **Hotovo, když:** databáze má stovky až tisíce zápasů, skript jde přerušit a znovu spustit bez duplicit,
  po běhu vznikne report kvality.
- **Naučíš se:** práce s API, SQLite, dlouhé běhy na pozadí, první vlastní skill `refresh-data`.

### Milník 4: Model v2
- **Cíl:** kritéria A až F z vlastních dat, vyhlazení, reciproční AHP s CR, TOPSIS s fixními ideály,
  kontrolní metody.
- **Zadání:** „Implementuj model v2 podle docs/plan.md (sekce Doporučený model). Ke každé funkci napiš test.
  Na konci porovnej pořadí v1 a v2 na stejných draftech a vysvětli rozdíly.“
- **Hotovo, když:** testy procházejí a máš srovnávací tabulku v1 a v2.
- **Naučíš se:** pytest, jak nechat agenta ověřovat vlastní práci, plánovací režim pro větší změny.

### Milník 5: API a UI
- **Cíl:** API čte agregace z databáze, UI ukazuje ikony, rozpad skóre, nejistotu a chybové stavy.
- **Zadání:** „Napoj model v2 na Flask API a vytvoř React UI podle docs/plan.md (sekce Jak to bude fungovat).
  Ikony ber z Data Dragonu. Po každé změně ověř funkčnost přes /run.“
- **Hotovo, když:** celý tok funguje v prohlížeči od Riot ID po vysvětlené top 5.
- **Naučíš se:** `/run`, `/verify`, `/run-skill-generator`.

### Milník 6: Validace a vlastní skills
- **Cíl:** backtest proti baseline, citlivostní analýza vah, užitečné vlastní skills.
- **Zadání:** „Udělej backtest podle docs/plan.md (sekce Validace a evaluace). Výsledky shrň
  do docs/vysledky.md s grafy. Pak mi pomoz vytvořit skill explain-recommendation a otestovat ho
  přes skill-creator.“
- **Hotovo, když:** víš, jestli v2 doporučuje lépe než baseline, a máš funkční vlastní skills.
- **Naučíš se:** skill-creator, subagent na rešerši (jedna ukázka), `/code-review`.

### Milník 7: Úklid a dokumentace
- **Cíl:** README s postupem spuštění, aktualizovaný CLAUDE.md, čistá historie.
- **Zadání:** „Napiš README, aby projekt spustil i někdo bez znalosti historie. Spusť /init a navrhni
  úpravy CLAUDE.md podle toho, co víme teď.“
- **Hotovo, když:** projekt spustíš podle README na čistém terminálu.

Volitelně potom: nahrát projekt na GitHub jako zálohu.

## Bezpečnost a když se něco pokazí

Nejdůležitější pojistky: klíč jen v `.env` a commit po každém funkčním kroku.

| Situace | Co udělat |
| --- | --- |
| Claude změnil něco, co nechceš | `/rewind` a vrátit se k checkpointu, nebo „vrať poslední změny“ |
| Rozbitý kód a nevíš od kdy | „ukaž posledních 5 commitů a vrať soubory na poslední funkční verzi“ |
| Claude se točí v kruhu | Esc, `/clear` a zadání znovu, kratší a konkrétnější |
| Odpovědi jsou horší v dlouhé konverzaci | `/context`; pokud je plný, `/clear` a začni od CLAUDE.md a aktuálního milníku |
| Riot API vrací 401 nebo 403 | development key vypršel; obnov ho na developer portálu a přepiš v `.env` |
| Riot API vrací 429 | překročený limit; sběrač má počkat, nespouštět víc běhů najednou |
| Došel limit předplatného | počkat na obnovení; `/usage` ukáže využití |

Než schválíš příkaz, který maže soubory nebo instaluje balíčky, přečti si ho.
Auto režim zapínej až po commitu. Kód od agenta je potřeba číst a chápat; když nechápeš, zeptej se „proč“.
Pokud omylem commitneš klíč, okamžitě ho na developer portálu vyměň.
