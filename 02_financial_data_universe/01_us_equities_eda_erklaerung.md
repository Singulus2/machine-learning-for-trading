# `01_us_equities_eda.py` — Erklärung des Notebooks

**Explorative Datenanalyse (EDA) des US-Aktien-Panels.** Das Notebook profiliert
den Datensatz [`us_equities.parquet`](../data/equities/market/us_equities/us_equities_erklaerung.md):
sein Schema, seine Preiskonventionen und — der Teil, der über die Backtest-
Tauglichkeit entscheidet — die **zeitliche Form seiner Abdeckung**.

Buchbezug: **§2.2** („The Asset-Class Market Data Landscape" — Equities).

## Die eine zentrale Erkenntnis

Das Notebook wirkt zunächst wie eine Routine-Profilierung, läuft aber gezielt auf
**einen einzigen, folgenschweren Befund** zu:

> Das Panel ist **kein** survivorship-bias-freies Abbild des US-Aktienmarkts,
> sondern ein **2014er-Schnappschuss, rückwärts bis zum IPO jedes Symbols
> aufgefüllt** — und dann bis zum Feed-Ende (März 2018) fortgeschrieben.

Alles andere im Notebook ist die Beweisführung dafür. Das ist eine wichtige
Korrektur zur Datensatz-Beschreibung, die WIKI Prices oft pauschal als
„survivorship-bias-frei" bezeichnet.

## Aufbau (6 Abschnitte + Fazit)

### 1. Laden & Schema inspizieren
- Lädt das Panel über `data.load_us_equities()`. Der Parameter `MAX_SYMBOLS`
  (Papermill/CI) erlaubt eine schnelle Teilmenge; `0` = alles.
- Gibt Shape, Spalten und Schema aus.
- **Roh vs. bereinigt:** erklärt die zwei Preiskonventionen — rohe
  `open/high/low/close/volume` für *tatsächlich gehandelte Preisniveaus*,
  bereinigte `adj_*` für *Renditen und Backtests*. Zusätzlich liefert das Panel
  die Korrektur-Inputs `ex-dividend` und `split_ratio` mit, sodass
  `02_corporate_actions` die Bereinigung an einem Beispiel **nachrechnen** kann.

### 2. Abdeckung: der Querschnitt
- Zählt eindeutige Symbole, Datumsspanne, Gesamtzeilen.
- Baut eine **`lifespans`-Tabelle**: eine Zeile pro Symbol mit Eintritt
  (`first_date`), Austritt (`last_date`), Handelstagen und Durchschnittspreis.
  Das Flag `leaves_early` = `last_date < dataset_end` markiert Symbole, die
  **vor** dem letzten Panel-Datum verschwinden.

### 3. Abdeckung über die Zeit (zwei Diagramme)
Der Querschnitt sagt *wie viele* Symbole, aber nicht *wann*. Zwei Sichten klären das:
- **Universumsgröße** (`active_by_year`, Liniendiagramm): distinkte Symbole je
  Kalenderjahr. Das Universum **wächst 50 Jahre, erreicht einen Peak (~3.163 in
  2014) und schrumpft dann**. „Ein Markt tut das nicht — ein Datenerhebungsprozess
  tut das."
- **Ein-/Austritte** (`flows`, Balkendiagramm, Austritte negativ): Erst- und
  Letztbeobachtungen je Jahr. Eine gestrichelte Linie markiert das **erste
  Austrittsjahr im Datensatz**.

### 4. Was der Austritts-Record wirklich zeigt
Der interpretatorische Kern:
- Eintritte laufen ab 1962 kontinuierlich. Austritte **nicht**: Das Panel
  verzeichnet **keinen einzigen Austritt vor 2014**.
- Firmen sind natürlich vorher ausgeschieden (Enron delistete 2002). Das Diagramm
  ist also **keine Aussage über den Markt, sondern über die Datei**:
  Austrittsinformation wurde **erst ab ~2014 erfasst**.
- Mechanismus: Das Panel wurde aus den 2014 existierenden Symbolen zusammengesetzt,
  jeweils bis zum IPO backfilled. Bereits „tote" Firmen wurden **nie aufgenommen**,
  ihr Verschwinden also nie erfasst. Ab 2014 ist das Panel „live" → Austritte
  werden verzeichnet. Beide Flüsse verebben danach, bis der Feed 2018 stoppt.

**Konsequenz für Backtests:**
- Vor 2014 enthält das Panel **nur Firmen, die bis 2014 überlebt haben** → ein
  1990er-Backtest sieht **keine einzige Pleite**.
- Ab 2014 sind Austritte erfasst → survivorship-bewusste Arbeit möglich.
- Das Fehlen von Austritten vor 2014 ist **„absence of evidence", kein Beleg**,
  dass nichts ausgeschieden wäre. Wir wissen nicht, was fehlt.

### 5. Datenqualität
- **Null-Zählung** über alle Spalten (Rate ~0,0006 % der Werte — praktisch sauber).
- **OHLC-Invarianten** via `check_ohlc_invariants` auf den `adj_*`-Spalten
  (z. B. `high ≥ low`, `high ≥ open/close` …) — alle bestehen zu 100 %.
- **Pointe:** Beide Checks bestehen — und **keiner** würde die Abdeckungslücke aus
  §4 finden. Nulls und OHLC-Invarianten sind **Innerhalb-Zeilen-Checks**;
  Survivorship ist eine Eigenschaft davon, **welche Zeilen überhaupt existieren**.
  Kein zeilenbasierter Test findet ein Symbol, das nie in die Datei geschrieben wurde.

### 6. Beispiel: ein einzelnes Symbol
- Filtert `AAPL`, zeigt Handelstage, Zeitspanne und die letzten 5 Tage
  (bereinigte Preise) — konkrete Veranschaulichung der Struktur.

## Kernaussagen (Key Takeaways des Notebooks)

1. **Lange Historie, breiter Querschnitt:** 3.199 Symbole, 1962–2018, 15,4 Mio.
   Zeilen; längste Einzelhistorie ~14.155 Tage (~56 Jahre).
2. **Zwei Preiskonventionen:** roh vs. `adj_*` — Renditen aus `adj_*`, gehandelte
   Niveaus aus den Rohspalten.
3. **Saubere Zeilen:** Null-Rate 0,0006 %; alle sechs OHLC-Invarianten zu 100 %.
4. **Ein Abdeckungs-Record, der keinen Markt beschreibt:** 777 Symbole (24,3 %)
   enden vor dem letzten Datum — und **jedes davon in 2014 oder später**.

**Befund 4 dominiert die Befunde 1–3.** Die Befunde 1–3 sind das, was eine
Validierungs-Pipeline prüft; Befund 4 ist der, der den Backtest zerstört hätte —
und kein zeilenbasierter Check hätte ihn ausgelöst.

## Einordnung in die Notebook-Kette

| Notebook | Rolle |
|----------|-------|
| **`01_us_equities_eda`** (dieses) | stellt fest, **was in der Datei ist** — und legt die Anomalie offen |
| `02_corporate_actions` | validiert die Bereinigungsfaktoren hinter `adj_*` an einem Beispiel (besteht für AAPL) |
| `15_survivorship_bias_detection` | greift Befund 4 auf und **quantifiziert den Schaden** — und findet, dass die Bereinigung *nicht* panelweit hält |

## Technische Notiz

Das Notebook nutzt **Polars** (`pl`) für die Aggregationen und **Plotly**
(`go.Figure`) für die Diagramme; Farben kommen aus `utils.style.COLORS`. Es ist im
**jupytext-percent-Format** (`.py`) geschrieben und mit der `.ipynb` gepaart —
Änderungen an der `.py` spiegeln sich beim Sync ins Notebook.

---

**Merksatz:** *Dieses EDA-Notebook zeigt: sauberes Schema, saubere Zeilen — aber
die Abdeckung verrät, dass WIKI Prices ein 2014-Schnappschuss ist. Zeilenchecks
(Nulls, OHLC) finden das nie; nur der Blick auf „welche Symbole wann eintreten und
austreten" deckt den Survivorship-Bias auf.*
