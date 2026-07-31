# `06_futures_continuous.py` — Erklärung der Funktionen

**Konstruktion einer kontinuierlichen Futures-Preisreihe** aus einzelnen,
verfallenden Kontrakten: Roll-Erkennung, Vergleich der Adjustierungsmethoden
(raw, Panama/additiv, Ratio/multiplikativ) und Validierung gegen Databentos
vorgefertigte Continuous-Serie.

Buchbezug: **§2.2** („The Asset-Class Market Data Landscape" — Futures); die
Methoden-Gegenüberstellung begründet die Engineering-Entscheidung, sowohl
rohe Einzelkontrakt-Historien als auch eine oder mehrere Continuous-Varianten
zu speichern.

Dieses Dokument geht die Funktionen des Notebooks der Reihe nach durch und
erklärt jeweils **was sie tun, warum sie so gebaut sind** und welche Fallstricke
sie umgehen.

---

## Übersicht: Datenfluss durch die Funktionen

```
es_individual (stündliche Einzelkontrakt-Bars)
        │
        ▼
parse_contract_symbol()          — Symbol → {product, month, year}  (nur für contract_df)
        │
        ▼
identify_front_month()           — welcher Kontrakt ist an Tag X der "Front Month"?
   (Alternative: identify_front_month_calendar())
        │
        ▼
create_continuous_raw()          — Front-Month-Preise aneinanderreihen (mit Sprüngen an Rolls)
        │
        ├──► _compute_roll_gaps()   ──► create_continuous_panama()   (additive Adjustierung)
        │
        └──► _compute_roll_ratios() ──► create_continuous_ratio()    (multiplikative Adjustierung)

construct_and_validate()         — kapselt obigen Ablauf + Vergleich gegen Databento, produktgenerisch
```

---

## 1. `parse_contract_symbol(symbol: str) -> dict`

**Zweck:** Zerlegt ein Futures-Symbol wie `"ESH24"` in seine Bestandteile.

```python
{"product": "ES", "month_code": "H", "month": 3, "year": 2024}
```

**Wie:** Ein Regex `^([A-Z]+)([FGHJKMNQUVXZ])(\d+)$` trennt Produktkürzel,
Monatscode und Jahreszahl. Der Monatscode wird über das Dictionary
`_MONTH_CODES` (F=Jan, G=Feb, H=Mär, … Z=Dez — die aus dem Optionsmarkt
bekannten CME-Monatscodes) in eine Zahl übersetzt. Die zweistellige Jahreszahl
wird mit einer einfachen Schwelle (`< 50` → 20xx, sonst 19xx) ins volle Jahr
umgerechnet.

**Warum kein `symbol`-Feld im Rückgabewert?** Die Funktion bekommt das Symbol
bereits als Parameter — es zurückzugeben wäre redundant für die Funktion
selbst. An der einzigen Aufrufstelle im Notebook wird es per
Dictionary-Unpacking (`{**parse_contract_symbol(r["symbol"]), "symbol": r["symbol"]}`)
wieder angeheftet, weil es dort als Join-Schlüssel zu `contract_defs`
gebraucht wird.

**Fehlerfall:** Nicht parsebare Symbole lösen `ValueError` aus — bewusst kein
stilles Überspringen, da ein falsch geparster Kontrakt die Sortierung nach
`year`/`month` (und damit die Roll-Reihenfolge) unbemerkt verfälschen würde.

---

## 2. `identify_front_month(individual_df, min_outright_price=500.0) -> pl.DataFrame`

**Zweck:** Bestimmt tagesgenau, welcher Kontrakt der "Front Month" (der
liquideste, aktuell gehandelte Kontrakt) ist — die Grundlage jeder
Continuous-Serie.

**Ablauf:**
1. **Spread-Filter:** CME listet neben den Outright-Kontrakten auch
   Calendar Spreads, die zum Inter-Monats-Preisunterschied (~50–100 $)
   handeln, nicht zum Indexniveau (~5.000 $ bei ES). Der Filter
   `close >= min_outright_price` verhindert, dass ein volumenstarker Spread
   fälschlich als Front Month erkannt wird.
2. **Tagesvolumen je Kontrakt:** Aggregiert stündliches Volumen zu
   Tagesvolumen pro `instrument_id`.
3. **Täglicher Leader:** Für jeden Tag wird der Kontrakt mit dem höchsten
   Tagesvolumen als `leader` markiert (`sort_by(...).last()`).
4. **No-Rollback-Constraint:** Die reine Leader-Liste flackert oft in der
   Roll-Woche zwischen zwei Kontrakten hin und her, weil das Volumen an
   einzelnen Tagen kurzzeitig zurückschwappen kann. Die Schleife über
   `leader_ids` erzwingt daher: Ein Wechsel des Front-Kontrakts ist nur
   erlaubt, wenn der neue Kontrakt **noch nie zuvor** Front-Month war
   (`used_contracts`-Set). Damit kann die Front-Position nur vorwärts
   springen, nie zurück — ein monoton wachsender Zeiger durch die
   Kontraktkette.
5. **Expansion auf Stundenbars:** Die täglich bestimmte `front_symbol`-Spalte
   wird per Left-Join auf jeden Stunden-Timestamp zurückgespiegelt.
6. **Roll-Flag:** `is_roll = front_symbol != prev_front` (mit `shift(1)`)
   markiert jede Stunde, an der sich der Front-Kontrakt ändert.

**Rückgabe:** `timestamp, front_symbol, prev_front, is_roll` — die zentrale
Roll-Tabelle, die alle nachfolgenden `create_continuous_*`-Funktionen als
Input nehmen.

**Ergebnis im Buch/Notebook:** 40 Rolls für ES 2016–2025 — passend zu vier
Quartals-Rolls/Jahr × 10 Jahre.

---

## 3. `identify_front_month_calendar(individual_df, definition_df, roll_days_before=5) -> pl.DataFrame`

**Zweck:** Alternative, kalenderbasierte Roll-Erkennung — rollt einen festen
Anzahl Tage vor Verfall, statt auf Volumen zu reagieren. Im Notebook nur als
**Lehrbeispiel** präsentiert, nicht produktiv genutzt (siehe unten, warum).

**Ablauf:**
1. Joint `definition_df` (Kontraktdefinitionen mit echtem `expiration`-Datum)
   über die Spalte `symbol` an die Einzelkontrakt-Daten.
2. Berechnet `days_to_expiry = expiry_date - trade_date`.
3. Filtert auf Kontrakte mit `days_to_expiry > roll_days_before` und wählt je
   Timestamp den Kontrakt mit dem **kleinsten** verbleibenden Days-to-Expiry
   (`sort(...).group_by("timestamp").first()`) — also den nächstliegenden
   Kontrakt, der die Roll-Schwelle noch nicht unterschritten hat.
4. Gleiches Roll-Flag-Schema wie bei `identify_front_month`.

**Warum nicht produktiv verwendet?** Die Funktion braucht eine `symbol`-Spalte
im Einzelkontrakt-DataFrame, um mit `definition_df` zu joinen. Der
Databento-Individual-Parquet trägt aber nur numerische `instrument_id`-Werte,
keine ESH24-artigen Symbole. Die Funktion bleibt als Referenz für den
methodischen Kontrast (Volumen vs. Kalender) im Code, wird aber im Rest des
Notebooks nicht aufgerufen.

**Trade-off, den das Notebook festhält:** Volumenbasiert folgt der
tatsächlichen Liquiditätsverschiebung, aber das Roll-Timing variiert;
kalenderbasiert ist vorhersagbar und leicht zu automatisieren, kann aber in
einen noch illiquiden Kontrakt rollen.

---

## 4. `create_continuous_raw(individual_df, front_months) -> pl.DataFrame`

**Zweck:** Baut die unadjustierte ("raw") Continuous-Serie — für jeden
Timestamp genau die OHLCV-Werte des an diesem Tag gültigen Front-Kontrakts.

**Wie:** Inner-Join von `individual_df` mit `front_months` über `timestamp`,
dann Filter auf `instrument_id == front_symbol`. Das Ergebnis ist eine
lückenlose Preisreihe — aber mit **künstlichen Sprüngen an jedem Roll-Datum**,
weil sich beim Kontraktwechsel das Preisniveau ändert. Diese Rohserie ist die
gemeinsame Basis für alle drei Betrachtungsweisen (raw, Panama, Ratio) und für
den späteren Databento-Vergleich.

**Wichtig:** Renditen, die über ein Roll-Datum hinweg aus dieser Serie
berechnet werden, sind **ungültig** — genau das Problem, das die beiden
Adjustierungsmethoden unten lösen.

---

## 5. `_compute_roll_gaps(individual_df, front_months) -> pl.DataFrame`

**Zweck:** Hilfsfunktion für Panama-Adjustierung. Berechnet an jedem
Roll-Datum die **additive Differenz** zwischen neuem und altem Kontrakt:
`gap = new_close - old_close`.

**Wie:** Nimmt aus `front_months` nur die Zeilen mit `is_roll == True`.
Joint einmal die Schlusskurse des `prev_front`-Kontrakts (`old_close`) und
einmal die des `front_symbol`-Kontrakts (`new_close`) am jeweiligen
Roll-Timestamp gegen die Preistabelle. Gibt `timestamp, gap` zurück.

**Namenskonvention:** Der führende Unterstrich markiert die Funktion als
internes Hilfsmittel — sie wird nur von `create_continuous_panama` aufgerufen
und ist für sich genommen kein Analyseergebnis.

---

## 6. `create_continuous_panama(individual_df, front_months) -> pl.DataFrame`

**Zweck:** Additive ("Panama") Back-Adjustierung — verschiebt historische
Preise so, dass an jedem Roll-Datum kein Sprung mehr sichtbar ist, während
der **aktuellste** Kontraktabschnitt unverändert bleibt.

**Kernidee:** `adjusted_price = raw_price + cumulative_gap`. Es wird
**addiert statt subtrahiert**, weil alte Preise auf das Niveau des aktuellen
Kontrakts angehoben werden — die Diskontinuität am Roll wird dadurch
eliminiert, nicht verschoben.

**Implementierung (vektorisiert statt zeilenweise, O(n)):**
1. `raw = create_continuous_raw(...)` als Basis.
2. `gaps_df = _compute_roll_gaps(...)` liefert die Gap-Werte an den
   Roll-Zeitpunkten.
3. Left-Join der Gaps auf die Rohserie, fehlende Werte (alle
   Nicht-Roll-Zeitpunkte) werden mit `0.0` gefüllt.
4. **Rückwärts-kumulative Summe:** `gap.reverse().cum_sum().shift(1).fill_null(0.0).reverse()`.
   Das ist der Kerntrick: Weil ein Gap am Roll-Datum X alle Preise **vor** X
   verschieben soll, aber nicht X selbst, wird die Serie umgedreht, kumuliert,
   um eine Position verschoben (damit der Roll-Tag selbst noch nicht
   mitgezählt wird) und wieder zurückgedreht. Ergebnis:
   `cumulative_adjustment` an jedem Zeitpunkt = Summe aller Gaps, die **nach**
   diesem Zeitpunkt noch folgen.
5. Addiert `cumulative_adjustment` auf `open/high/low/close` → `adj_open`,
   `adj_high`, `adj_low`, `adj_close`.

**Randfälle:** Keine Rolls im Datensatz oder keine gültigen Gaps →
`cumulative_adjustment = 0.0` für die gesamte Serie (unverändert gegenüber
raw).

**Ergebnis im Notebook:** Für ES (2016–2025) beträgt die
`cumulative_adjustment` am Serienanfang rund **+625 $** — die frühesten
2016er-Preise werden um ~30 % angehoben. Der **Dollar-P&L** über Rolls hinweg
bleibt korrekt; **prozentuale** Renditen auf alten Daten werden verzerrt, je
weiter man zurückgeht.

---

## 7. `_compute_roll_ratios(individual_df, front_months) -> pl.DataFrame`

**Zweck:** Hilfsfunktion für Ratio-Adjustierung — spiegelbildlich zu
`_compute_roll_gaps`, aber mit **Verhältnis** statt Differenz:
`ratio = new_close / old_close`.

**Zusätzlicher Schutz:** Filtert `old_close != 0`, um Division durch Null zu
vermeiden (bei Preis 0 wäre ohnehin kein sinnvolles Verhältnis definierbar).

---

## 8. `create_continuous_ratio(individual_df, front_months) -> pl.DataFrame`

**Zweck:** Multiplikative ("Ratio") Back-Adjustierung — analog zu Panama, aber
mit Skalierung statt Addition: `adjusted_price = raw_price * cumulative_ratio`.

**Implementierung:** Spiegelt `create_continuous_panama` eins zu eins,
ersetzt aber:
- Summe → Produkt: `ratio.reverse().cum_prod().shift(1).fill_null(1.0).reverse()`
  (Neutralelement der Multiplikation ist `1.0`, nicht `0.0` wie bei der Summe).
- Addition der Adjustierung → Multiplikation mit `cumulative_ratio`.

**Ergebnis im Notebook:** `cumulative_ratio` am Serienanfang ≈ **1,11** (+11 %
Skalierung). Da hier multipliziert statt addiert wird, bleiben **prozentuale
Renditen** über die gesamte Historie korrekt — die richtige Wahl für
Information-Coefficient-Analysen, Momentum-Features und generell jede
statistische Auswertung, bei der Renditen (nicht Dollarbeträge) die
Zielgröße sind.

---

## 9. `construct_and_validate(product: str, min_outright_price: float = 500.0) -> dict`

**Zweck:** Kapselt den gesamten Konstruktions- und Validierungs-Ablauf in
einer produktgenerischen Funktion — Laden, Roll-Erkennung, Raw-Konstruktion
und Vergleich gegen Databentos Continuous-Serie in einem Aufruf.

**Wie:**
1. Lädt Einzelkontrakte für `product` (`load_cme_futures(..., continuous=False)`).
2. `identify_front_month(...)` → Roll-Tabelle.
3. `create_continuous_raw(...)` → eigene Rohserie.
4. Lädt Databentos vorgefertigte Continuous-Serie
   (`load_cme_futures(..., tenors=[0], continuous=True)`) zum Vergleich.
5. Inner-Join beider Serien über `timestamp`, berechnet absolute Differenz.
6. Gibt ein Dictionary mit Kennzahlen zurück: `rows`, `contracts_used`,
   `validation_rows`, `mean_abs_diff`, `max_abs_diff`.

**Warum diese Kapselung?** Die Book-Datenlieferung enthält Einzelkontrakt-Daten
nur für ES; die übrigen 29 Produkte liegen ausschließlich als vorgefertigte
Continuous-Serien vor. `construct_and_validate` ist deshalb generisch
gehalten (funktioniert für jedes Produkt, sobald Individual-Daten verfügbar
sind), wird im Notebook aber nur mit `"ES"` aufgerufen — die Kapselung zeigt
den Pfad zur Wiederverwendung, ohne ihn beim Schreiben schon für andere
Produkte auszuführen.

**Validierungsergebnis für ES:** Bei 2.581 überlappenden Bars liegt die
mittlere absolute Differenz bei ~27 $, der mediane **signierte** Unterschied
nahe null (~2,50 $ — praktisch nichts gegenüber einem Durchschnittspreis von
~3.800 $), die maximale Abweichung bei ~583 $. Die Differenzen stammen fast
ausschließlich aus **Roll-Timing-Unterschieden**: Wenn der eigene
volumenbasierte Detektor einen Tag früher oder später rollt als Databentos
Algorithmus, geben beide Serien für diese Stunden den Preis
unterschiedlicher Kontrakte wieder — die Differenz zwischen den Kontrakten
(Contango/Backwardation) erzeugt dann die Lücke. Der nahe-null-Median zeigt,
dass keiner der beiden Algorithmen systematisch hoch oder niedrig liegt.

---

## Einordnung: wann welche Funktion?

| Funktion | Rolle im Ablauf |
|---|---|
| `parse_contract_symbol` | Symbol-Parsing für die Kontraktdefinitionstabelle (nicht Teil des eigentlichen Konstruktionspfads) |
| `identify_front_month` | **Produktiv genutzte** Roll-Erkennung (volumenbasiert, mit No-Rollback) |
| `identify_front_month_calendar` | Lehrbeispiel für kalenderbasierte Alternative — nicht produktiv genutzt |
| `create_continuous_raw` | Basis-Serie, Ausgangspunkt für beide Adjustierungen und den Databento-Vergleich |
| `_compute_roll_gaps` / `create_continuous_panama` | Additive Adjustierung → korrekt für Dollar-P&L / Backtesting |
| `_compute_roll_ratios` / `create_continuous_ratio` | Multiplikative Adjustierung → korrekt für prozentuale Renditen / Statistik |
| `construct_and_validate` | Produktgenerische Kapselung von Konstruktion + Validierung |

### Empfehlung nach Anwendungsfall (aus dem Notebook-Fazit)

| Use Case | Empfohlene Methode | Grund |
|---|---|---|
| Backtesting P&L | Panama (additiv) | Erhält Dollar-Gewinne/-Verluste über Rolls hinweg |
| Statistische Analyse | Ratio | Erhält prozentuale Renditen korrekt |
| Live-Trading | Raw + Positionsmanagement | Rolls werden in der Ausführungsschicht behandelt |

### Wichtige Einschränkung beider Adjustierungsmethoden

Weder Panama- noch Ratio-Adjustierung enthalten einen **Collateral-Return**
(Zinsertrag auf die nicht gebundene Margin). Ein Future bindet nur eine
Margin, kein volles Kapital — das übrige Kapital wird typischerweise verzinst
angelegt (z. B. in T-Bills). Eine back-adjustierte Futures-Serie bildet daher
faktisch einen **Excess-Return** ab, keinen Total-Return. Beim Vergleich mit
einem Spot-Asset oder einem Total-Return-Index (z. B. in Kapitel 8 oder 16)
muss das explizit gemacht werden, sonst wird die Futures-Position um den
nicht modellierten Zinsertrag systematisch unterschätzt.

---

## Nächste Notebooks

- **Kapitel 8**: Carry- und Momentum-Features auf Basis der Continuous-Serie.
- **Kapitel 16**: Backtesting mit adjustierten P&L-Daten.
