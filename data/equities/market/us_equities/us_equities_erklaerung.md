# `us_equities.parquet` — Erklärung des Datensatzes

Historische **Tages-Kursdaten (OHLCV)** für US-Aktien aus dem Datensatz
**NASDAQ Data Link „WIKI Prices"** (früher Quandl `WIKI/PRICES`). Der Datensatz
ist **eingefroren**: NASDAQ Data Link hat die Aktualisierung im März 2018
eingestellt, deshalb lädt der Downloader die Datei **einmalig** herunter.

## Eckdaten

| Merkmal | Wert |
|---------|------|
| **Zeilen** | 15.389.314 |
| **Ticker (Symbole)** | 3.199 US-Unternehmen |
| **Zeitraum** | 1962-01-02 bis 2018-03-27 (Tagesfrequenz) |
| **Dateigröße** | ~500 MB (Parquet) |
| **Quelle** | NASDAQ Data Link (ehem. Quandl) `WIKI/PRICES` |
| **Zugang** | kostenloser API-Key (https://data.nasdaq.com/sign-up) |
| **Format** | Spaltenbasiertes Parquet (per Lazy-Loading nutzbar) |

**Warum wichtig:** Der Datensatz ist **survivorship-bias-frei** — er enthält auch
**delistete** Firmen (Pleiten, Übernahmen). Backtests auf einem Universum, das nur
noch *heute existierende* Aktien enthält, überschätzen die Rendite systematisch.
Genau diesen Fehler vermeidet dieser Datensatz.

## Schema (14 Spalten)

| Spalte | Typ | Bedeutung |
|--------|-----|-----------|
| `ticker` | String | Börsensymbol, z. B. `AAPL` |
| `date` | Datetime | Handelstag |
| `open` / `high` / `low` / `close` | Float | **Roh**-Kurse des Tages (wie damals gehandelt) |
| `volume` | Float | gehandeltes Volumen (Stück) |
| `ex-dividend` | Float | ausgeschüttete Dividende an diesem Tag (0 = keine) |
| `split_ratio` | Float | Aktiensplit-Verhältnis (1 = kein Split; 2 = 2:1-Split …) |
| `adj_open` / `adj_high` / `adj_low` / `adj_close` | Float | **bereinigte** Kurse |
| `adj_volume` | Float | bereinigtes Volumen |

## Der entscheidende Punkt: roh vs. bereinigt (`adj_*`)

Die `adj_*`-Spalten sind **um Splits und Dividenden rückwirkend korrigiert**. Das
ist essenziell, weil ein Split den Kurs künstlich springen lässt, **ohne** dass
Vermögen verloren geht.

**Beispiel Apple (`AAPL`) — die Split-Ereignisse im Datensatz:**

| Datum | `close` (roh) | `split_ratio` | `adj_close` (bereinigt) |
|-------|--------------|---------------|-------------------------|
| 1987-06-16 | 41,50 | 2,0 | 1,22 |
| 2000-06-21 | 55,63 | 2,0 | 3,57 |
| 2005-02-28 | 44,86 | 2,0 | 5,77 |
| 2014-06-09 | 93,70 | 7,0 | 88,19 |

Am 2014-06-09 wurde Apple **7:1** gesplittet: Der Rohkurs fiel über Nacht von
~645 auf ~93 USD — ein reiner Buchungseffekt. In der `adj_close`-Spalte gibt es
diesen Sprung **nicht**; sie bildet die tatsächliche **Rendite** eines Anlegers
ab. Deshalb gilt:

> **Für Renditen, Signale und Backtests immer `adj_close` (bzw. die `adj_*`-Reihe)
> verwenden — niemals die rohen `close`-Werte.** Die Rohkurse sind nur für die
> Rekonstruktion des historischen Handelspreises nützlich.

Im Datensatz gibt es **4.095** Zeilen mit einem Split (`split_ratio ≠ 1`) und
**118.131** Zeilen mit einer Dividende (`ex-dividend ≠ 0`) — beides fließt in die
Bereinigung ein.

## Datenqualität

- **Keine fehlenden** `ticker`- oder `date`-Werte.
- Wenige Null-Werte in den Kursspalten (z. B. 538 in `open`/`adj_open`, 55 in
  `high`/`low`, 1 in `adj_close`) — vernachlässigbar bei 15,4 Mio. Zeilen, aber
  vor Berechnungen ggf. filtern.
- **Long-Format** (eine Zeile = ein Ticker × ein Tag). Für Panel-Analysen ist ggf.
  ein Pivot auf `date` × `ticker` nötig.

## Laden im Code

Der Loader normalisiert die Spaltennamen (`ticker → symbol`, `date → timestamp`):

```python
from data import load_us_equities

df = load_us_equities()                            # gesamtes Universum
df = load_us_equities(symbols=["AAPL", "MSFT"])    # einzelne Titel
df = load_us_equities(start_date="2000-01-01",
                      end_date="2010-12-31")        # Zeitraum
df = load_us_equities(max_symbols=50)              # 50 zufällige (Prototyping)
```

Fehlt die Parquet-Datei, wirft der Loader `DataNotFoundError` mit dem exakten
Download-Befehl.

## Erneut herunterladen

```bash
uv run python data/equities/market/us_equities/download.py --api-key DEIN_KEY
```

Da der Datensatz eingefroren ist, ist ein erneuter Download nur bei Datenverlust
nötig (`--force` erzwingt das Überschreiben). Die ~500-MB-Datei ist über
`.gitignore` (`data/**/*.parquet`) vom Repository ausgeschlossen.

## Wer nutzt den Datensatz?

- `case_studies/us_equities_panel/` — die durchgehende Fallstudie (Kap. 7 → 20).
- Kapitel-2-EDA-Notebook [`01_us_equities_eda.py`](../../../../02_financial_data_universe/01_us_equities_eda.py) — Abdeckungs-Survey.
- Jedes Kapitel, das eine lange, survivor-freie US-Aktienhistorie braucht.

---

**Merksatz:** *WIKI Prices = lange (1962–2018), survivorship-bias-freie
US-Tagesdaten. Roh-OHLCV für den historischen Preis, `adj_*` für Renditen und
Backtests — und der Datensatz ist eingefroren, also einmal laden und fertig.*
