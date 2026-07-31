# Erklärung: `download.py`

Dieses Skript lädt Futures-Marktdaten (OHLCV, stündlich) von **Databento**
herunter und speichert sie **Hive-partitioniert** nach `product`/`year` im
lokalen Datenverzeichnis. Es ist **config-getrieben** (`config.yaml`) und
**idempotent**: mehrfaches Ausführen lädt nur fehlende/unvollständige Daten
nach, statt alles neu herunterzuladen.

Quelle: [download.py](download.py)

---

## 1. Grundidee

```
python download.py --estimate     # nur Kosten schätzen, nichts laden
python download.py                # alle Produkte aus config.yaml laden (idempotent)
python download.py -p ES -p NQ    # nur bestimmte Produkte
python download.py --extension    # zusätzlich Extension-Produkte (Crypto, SOFR, ...)
python download.py --dry-run      # zeigen, was geladen würde, ohne API-Call
python download.py -p ES -y 2024 --force   # bestimmtes Jahr zwangsweise neu laden
```

Der Ablauf in `main()` ([download.py:557-802](download.py#L557-L802)) ist immer:

1. Config laden
2. Für jedes Produkt den **Ist-Zustand** (welche Jahre existieren, welche fehlen/unvollständig) analysieren
3. Kosten **schätzen** (immer, auch ohne `--estimate`)
4. Nutzer muss bestätigen (außer bei `--dry-run`/`--estimate`)
5. Herunterladen (sequenziell oder parallel)
6. Zusammenfassung ausgeben

---

## 2. Konfiguration (`FuturesConfig`)

[download.py:59-102](download.py#L59-L102)

```python
@dataclass
class FuturesConfig:
    dataset: str            # z.B. "GLBX.MDP3" (CME Globex)
    schema: str              # z.B. "ohlcv-1h"
    roll_type: str           # "v" (volume-basiert) oder "c" (kalenderbasiert)
    tenors: list[int]        # z.B. [0, 1, 2] = Front/1st/2nd Deferred
    default_start: str
    default_end: str
    products: dict[str, dict[str, Any]]
    extension_products: dict[str, dict[str, Any]] = field(default_factory=dict)
```

- `FuturesConfig.load(path)` liest `config.yaml` per `yaml.safe_load` ein.
- `get_product_start(product)`: Startdatum eines Produkts — nimmt das
  produktspezifische `start`, falls in der YAML gesetzt, sonst
  `default_start`. So können einzelne Produkte (z. B. wegen späterer
  Datenverfügbarkeit) einen abweichenden Beginn haben.
- `get_all_products(include_extension)`: liefert die Liste der
  Standard-Produkte, optional erweitert um `extension_products`
  (Crypto, SOFR etc.).

`get_config_path()` ([download.py:105-107](download.py#L105-L107)) zeigt
standardmäßig auf `config.yaml` im selben Verzeichnis wie das Skript.

---

## 3. Hive-Partitionierung

[download.py:115-142](download.py#L115-L142)

Die Daten werden abgelegt unter:

```
<data_dir>/futures/market/continuous/hourly/product=<PRODUCT>/year=<YEAR>/data.parquet
```

- `get_hive_base_path(data_dir)`: Basisverzeichnis für alle Futures-Daten.
- `get_partition_path(data_dir, product, year)`: Pfad zu genau einer
  Jahres-Partition eines Produkts.
- `list_existing_years(data_dir, product)`: durchsucht das Produktverzeichnis
  nach vorhandenen `year=*`-Unterordnern mit gültiger `data.parquet`.

Dieses Schema erlaubt spätere **inkrementelle Erweiterung** (neue Jahre
hinzufügen) und effizientes selektives Lesen via `hive_partitioning=True`
beim Laden (siehe `loader.py`).

---

## 4. Coverage-Analyse — was fehlt noch?

[download.py:145-266](download.py#L145-L266)

### `get_year_coverage(data_dir, product, year)`
Öffnet (falls vorhanden) die Parquet-Datei einer Jahres-Partition **lazy**
(`pl.scan_parquet`) und ermittelt per Aggregation:
- `min_date`, `max_date` (aus Spalte `timestamp`)
- Zeilenanzahl (`rows`)

Existiert die Datei nicht oder schlägt das Lesen fehl, wird
`(None, None, 0)` zurückgegeben.

### `analyze_product_coverage(data_dir, product, config, end_date)`
Geht für ein Produkt jedes Jahr von `start_year` bis `end_year` durch und
bewertet pro Jahr (`YearStatus`):

- **Keine Daten vorhanden** (`rows == 0`) → Jahr muss geladen werden.
- **Daten vorhanden** → Jahr gilt als **vollständig**, wenn `max_date`
  höchstens 5 Tage vor dem erwarteten Jahresende liegt (Toleranz für
  Feiertage/Wochenenden/Börsenschließungen). Beim letzten Jahr wird gegen
  das tatsächliche `end_date` statt gegen den 31.12. geprüft.
- Unvollständige Jahre landen in `years_to_download`.

Ergebnis ist ein `ProductCoverage`-Objekt mit dem Status jedes Jahres und
der Liste der nachzuladenden Jahre.

---

## 5. Kostenschätzung

[download.py:274-325](download.py#L274-L325)

`estimate_cost(config, products, years_by_product)`:
- Initialisiert einen Databento-Client (`db.Historical()`).
- Baut für jedes Produkt die **Continuous-Contract-Symbole**, z. B.
  `ES.v.0`, `ES.v.1`, `ES.v.2` (`f"{product}.{roll_type}.{pos}"` für jeden
  Tenor).
- Ruft für jedes zu ladende Jahr `client.metadata.get_cost(...)` auf
  (Databentos offizielle Kosten-Schätzungs-API) und summiert die Kosten.
- Fehler bei einzelnen Schätzungen werden nur als Warnung geloggt, nicht
  fatal.

Diese Schätzung läuft **immer** vor einem echten Download, unabhängig vom
Modus (`--estimate`, `--dry-run` oder echter Download).

---

## 6. Download-Logik

### `download_full_product(product, config, data_dir, dry_run)`
[download.py:333-455](download.py#L333-L455)

Kernidee: **ein einziger API-Call pro Produkt** über die komplette
Zeitspanne (`start_date` bis `end_date`), statt Jahr für Jahr einzeln zu
laden — laut Kommentar ~15x effizienter wegen geringerem API-Overhead.

Ablauf:
1. Symbole bauen (`ES.v.0`, `ES.v.1`, ...).
2. `client.timeseries.get_range(...)` mit `stype_in="continuous"` holt die
   Rohdaten von Databento.
3. `patch_databento_symbology()` (aus `utils/downloading.py`) behebt einen
   bekannten Symbology-Bug in Databento 0.72.0.
4. Die Daten werden über eine temporäre Parquet-Datei nach Polars
   konvertiert (`data.to_parquet(...)` → `pl.read_parquet(...)`) — ein
   Umweg, der vermutlich Typprobleme bei der direkten Databento→Polars
   Konvertierung umgeht.
5. Spalten normalisieren:
   - `ts_event` → `timestamp` (kanonischer Name)
   - Symbol-Spalte (`asset` oder `symbol`, je nach Databento-Version)
   - `product`-Spalte per Literal hinzufügen
   - `tenor` per Regex aus dem Symbol extrahieren (z. B. `GF.v.0` → `0`)
6. Nur die kanonischen Zielspalten behalten (`keep_cols`).
7. `year` aus `timestamp` ableiten und **pro Jahr** in die passende
   Hive-Partition schreiben:
   - Existiert die Partition schon, wird sie mit den neuen Daten
     **gemerged**, Duplikate über `unique(subset=["timestamp", "tenor"], keep="last")`
     entfernt und neu sortiert geschrieben — das macht den Vorgang
     idempotent und erlaubt Nachladen/Ergänzen ohne Datenverlust.
   - Sonst wird die Partition neu angelegt.

Rückgabe: `(Gesamtzeilenzahl, Statusmeldung)`.

### `download_product_efficient(...)` ([download.py:458-480](download.py#L458-L480))
Dünner Wrapper um `download_full_product`, der das Ergebnis in ein
einheitliches `stats`-Dict (`downloaded`, `failed`, `rows`, `messages`)
verpackt — wird sowohl sequenziell als auch parallel verwendet.

### `download_parallel(...)` ([download.py:483-549](download.py#L483-L549))
Lädt mehrere Produkte gleichzeitig über einen
`ThreadPoolExecutor(max_workers=workers)`. Jeder Produkt-Download läuft als
ein Future; Ergebnisse werden per `as_completed` verarbeitet und
Fortschritt live ausgegeben (`[i/N] PRODUKT: X rows`).

---

## 7. CLI (`main()`)

[download.py:557-802](download.py#L557-L802)

Wichtige Argumente:

| Flag | Bedeutung |
|---|---|
| `-p/--product` | Einzelne Produkte auswählen (wiederholbar); Default = alle aus Config |
| `-x/--extension` | Extension-Produkte (Crypto, SOFR, ...) einschließen |
| `-y/--year` | Bestimmte Jahre erzwingen (wiederholbar) |
| `--end-date` | Enddatum aus Config überschreiben |
| `-e/--estimate(-only)` | Nur Kosten schätzen, kein Download |
| `-n/--dry-run` | Zeigen, was geladen würde, ohne API-Call/Kosten zu verursachen |
| `-f/--force` | Vorhandene Daten trotzdem neu laden |
| `--config` | Alternativer Pfad zur YAML-Config |
| `-j/--parallel N` | N parallele Download-Worker (Default 1 = sequenziell) |

Ablauf im Detail:

1. **Config & Datenverzeichnis auflösen** (`resolve_data_dir(None)` aus
   `utils/downloading.py`).
2. **Produktliste bestimmen**: explizite `--product`-Angaben oder alle aus
   der Config (`get_all_products`).
3. **Coverage-Analyse pro Produkt** (`analyze_product_coverage`), dabei:
   - Bei `--year`: nur die angegebenen Jahre (sofern sie fehlen oder
     `--force` gesetzt ist).
   - Bei `--force` ohne `--year`: **alle** Jahre im Bereich erzwingen.
   - Sonst: nur die von der Coverage-Analyse als fehlend erkannten Jahre.
4. **Zusammenfassung ausgeben**: welche Produkte brauchen ein Update, mit
   vorhandenen vs. benötigten Jahren. Sind alle Produkte aktuell und
   `--force` nicht gesetzt, bricht das Skript hier bereits ab (Exit 0).
5. **Kosten schätzen** (immer) — via `estimate_cost`.
6. Bei `--estimate`: Kosten anzeigen (`databento_estimate_only_notice`) und
   beenden, **kein Download**.
7. Bei `--dry-run`: geschätzte Kosten anzeigen und beenden, **kein
   Download, kein API-Call für die eigentlichen Daten**.
8. **Bestätigung einholen**: `databento_acknowledge(cost, force=args.force)`
   — bei kostenpflichtigem Download muss der Nutzer explizit zustimmen,
   außer `--force` ist gesetzt (Sicherheitsnetz gegen versehentliche
   Kosten).
9. **Herunterladen**:
   - `args.parallel > 1` → `download_parallel(...)`
   - sonst → sequenzielle Schleife über `download_product_efficient(...)`
10. **Abschlussbericht**: heruntergeladene Produkte, Gesamtzeilen,
    übersprungene/fehlgeschlagene Produkte.

---

## 8. Design-Prinzipien (aus den Kommentaren/Config abgeleitet)

- **Idempotenz**: Mehrfaches Ausführen ohne `--force` lädt nur, was fehlt
  oder unvollständig ist — sicher für wiederholte Cronjob-artige Aufrufe.
- **Inkrementalität**: Das Enddatum in der Config kann später erhöht
  werden, um die Daten zu erweitern, ohne Altbestände neu zu laden.
- **Kostenkontrolle**: Schätzung ist obligatorisch vor jedem echten
  Download; explizite Bestätigung nötig (`databento_acknowledge`), da
  Databento-Anfragen kostenpflichtig sind (siehe `config.yaml`: ca. 0,58 $
  pro Produkt/10 Jahre/3 Tenors, ~75 $ für das gesamte 30-Produkte-Set).
- **Effizienz**: Ein API-Call pro Produkt über die volle Zeitspanne statt
  Jahr-für-Jahr-Calls, danach lokale Aufteilung in Jahres-Partitionen
  (~15x schneller laut Kommentar).
- **Robustheit**: Merge-mit-Dedup beim Schreiben bestehender Partitionen
  verhindert Datenverlust und doppelte Zeilen bei wiederholten/
  überlappenden Downloads.
