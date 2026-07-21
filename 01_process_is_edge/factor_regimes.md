# Erläuterungen zu `factor_regimes.py`

Dieses Dokument bündelt alle deutschen Erklärungen zum Notebook
[`factor_regimes.py`](factor_regimes.py). Die Abschnitte folgen der **Reihenfolge im
py-File** (von oben nach unten): zuerst die Imports (`polars`, `GaussianMixture`),
dann der Hintergrund, danach die Code-Bausteine (`GmmFitResult`, `fit_gmm_grid`) und
zuletzt der Exkurs zur Kovarianzmatrix (die im `covariance_type`-Parameter auftaucht).

---

## 1. `polars` — die Datenbibliothek

**Polars** ist eine moderne DataFrame-Bibliothek (Python/Rust), die als schnellere,
speichereffizientere Alternative zu **pandas** gilt. Im Notebook wird sie beim
Laden der AQR-Faktordaten genutzt (`AQRFactorProvider().fetch(...)`, `pl.col(...)`).

**Was Polars bietet:**

- **Geschwindigkeit:** In **Rust** geschrieben, **multi-threaded** standardmäßig,
  nutzt das spaltenweise **Apache-Arrow**-Speicherformat → oft 5–30× schneller als
  pandas.
- **Zwei Ausführungsmodi:** *Eager* (sofort) und *Lazy* (`.lazy()` / `scan_*`), wobei
  Lazy den **gesamten Abfrageplan optimiert** (Predicate/Projection Pushdown) und
  erst bei `.collect()` ausführt.
- **Ausdrucksstarke Expression-API:** komponierbare `pl.col(...)`-Ausdrücke, z. B.

  ```python
  aqr_raw_pl.select(
      pl.col("timestamp").min().alias("min"),
      pl.col("timestamp").max().alias("max"),
  )
  ```

- **Weiteres:** kein Index (konsistentere Semantik), strenges Typsystem mit echtem
  Null-Handling, Streaming für größer-als-RAM-Daten, guter Parquet/CSV/Arrow-I/O,
  interoperabel via `.to_pandas()` / `.to_numpy()`.

| Aspekt | pandas | Polars |
|--------|--------|--------|
| Sprache | C/Python | Rust |
| Parallelität | überwiegend single-threaded | multi-threaded standardmäßig |
| Lazy-Optimierung | nein | ja (Query Planner) |
| Index | ja (oft fehlerträchtig) | nein |
| Speicherformat | Blöcke/NumPy | Apache Arrow |
| Reifegrad/Ökosystem | sehr groß, etabliert | jünger, wächst schnell |

**Im Projekt:** Polars für die **Datenaufbereitung** (Parquet laden, filtern,
aggregieren), danach nahtloser Übergang zu **NumPy/scikit-learn** für das GMM.

---

## 2. `GaussianMixture` — das Modell

`GaussianMixture` ist die scikit-learn-Implementierung eines **Gaussian Mixture
Model (GMM)** — des zentralen Modells zur Regime-Erkennung.

**Grundidee:** Ein GMM ist ein **unüberwachtes Clustering-Verfahren**. Annahme:
Die Daten stammen aus einer **Mischung mehrerer mehrdimensionaler
Normalverteilungen** (Gauß-Glocken). Jede Komponente entspricht einem Cluster =
Marktregime und ist definiert durch:

1. einen **Mittelwert-Vektor** μ (Zentrum des Regimes im Faktorraum),
2. eine **Kovarianzmatrix** Σ (Form/Streckung/Schräglage der Punktwolke),
3. ein **Gewicht** π (Anteil des Regimes an den Gesamtdaten).

**Weiche vs. harte Zuordnung:** Anders als K-Means (harte Zuordnung zum nächsten
Mittelpunkt) liefert GMM eine **weiche Zuordnung** — je Zeitpunkt eine
Wahrscheinlichkeit pro Regime (z. B. „70 % Krise, 30 % Erholung"):

- `model.predict(x)` → **hartes** Label (wahrscheinlichstes Regime)
- `model.predict_proba(x)` → **weiche** Wahrscheinlichkeiten je Regime

Das passt zu Märkten, deren Übergänge fließend statt scharf sind.

**Training (EM-Algorithmus):** `model.fit(x)` schätzt μ, Σ, π iterativ mit
Expectation-Maximization:

1. **E-Schritt:** Wahrscheinlichkeit jedes Punktes für jedes Cluster berechnen.
2. **M-Schritt:** Parameter anhand dieser Wahrscheinlichkeiten neu schätzen.
3. Wiederholen bis Konvergenz der Log-Likelihood.

EM kann in **lokalen Optima** landen → `n_init=10` (10 Neustarts, bester Lauf).

**Parameter im Notebook:**

```python
GaussianMixture(
    n_components=n,          # Anzahl der Regime (Cluster), hier 2–6 durchprobiert
    covariance_type="full",  # jedes Cluster: eigene, vollständige Kovarianzmatrix
    random_state=random_state,  # reproduzierbar
    n_init=10,               # 10 Neustarts gegen lokale Optima
    reg_covar=1e-6,          # numerische Stabilität (keine singuläre Kovarianz)
)
```

- **`n_components`** — Anzahl der Gauß-Komponenten = Anzahl der Regime.
- **`covariance_type="full"`** — flexibelste Variante (beliebig geformte, gekippte
  Ellipse je Cluster). Alternativen: `"tied"`, `"diag"`, `"spherical"`.
- **`n_init` / `reg_covar` / `random_state`** — Robustheit, numerische Stabilität,
  Reproduzierbarkeit.

**Modellgüte:** `model.bic(x)` und `model.aic(x)` wägen Anpassung gegen Komplexität
ab (**niedriger = besser**) und dienen zur Wahl der Regime-Anzahl.

| Aspekt | K-Means | GaussianMixture |
|--------|---------|-----------------|
| Zuordnung | hart | weich (Wahrscheinlichkeiten) |
| Clusterform | kugelförmig, gleich groß | beliebige Ellipsen (bei `full`) |
| Modellbasis | Distanzen | Wahrscheinlichkeitsverteilung |
| Güte-Kriterium | Inertia/Silhouette | BIC/AIC (+ Log-Likelihood) |

---

## 3. Hintergrund: Marktregime & der GMM-Ansatz

Ein **Marktregime** ist eine Phase, in der sich der Markt strukturell ähnlich
verhält (z. B. „ruhiges Wachstum", „Krise/Crash", „Erholung", „hohe Inflation").
Ziel ist es, solche Phasen **unüberwacht** — also ohne vorherige Labels — direkt
aus den Daten zu erkennen.

- **Vorbild Two Sigma (2021):** Der quantitative Hedgefonds Two Sigma nutzt in
  seinem [Paper](https://www.twosigma.com/articles/a-machine-learning-approach-to-regime-modeling/)
  ein **Gaussian Mixture Model (GMM)** auf einer „Factor Lens" aus **18 Faktoren**
  und leitet daraus **vier** Regime ab.
- **Unser Ansatz:** Statt der Two-Sigma-Daten verwendet dieses Notebook den
  AQR-Datensatz „Century of Factor Premia", der bis **1927** zurückreicht (fast
  100 Jahre statt weniger Jahrzehnte). Mehr Historie bedeutet mehr unterschiedliche
  Marktphasen (Weltwirtschaftskrise, Ölkrisen, 2008, COVID …) und damit eine
  robustere Regime-Erkennung. Genutzt werden die vier klassischen Faktoren
  **Value, Momentum, Carry und Defensive** über mehrere Anlageklassen hinweg —
  eine kompaktere Faktor-Auswahl als die 18 von Two Sigma, dafür mit deutlich
  längerer Zeitreihe.
- **Keine „richtige" Regime-Anzahl:** Die Anzahl der Regime ist keine objektive
  Wahrheit, sondern eine Design-Entscheidung. Deshalb probiert das Notebook
  systematisch **2 bis 6 Cluster** durch (engl. *sweep*), um zu zeigen, wie die
  **Granularität** die Regime-Karte formt: wenige Regime (z. B. 2) liefern eine
  grobe Einteilung („ruhig" vs. „gestresst"), viele Regime (z. B. 6) unterscheiden
  feiner, riskieren aber instabile Cluster und die Fehlinterpretation von Rauschen
  als eigenständiges Regime.

> **Scope-Hinweis:** Das Notebook fittet das GMM auf der *gesamten* Historie und
> weist die Regime-Labels rückwirkend zu. Das ist eine **deskriptive** (ex-post)
> Charakterisierung, **kein** prädiktiver Klassifikator — die Labels als Features
> in einer Strategie zu nutzen wäre Look-ahead. Lookahead-sichere Konstruktion
> folgt ab Kapitel 6 bzw. in den Case-Studies (Ch16–20).

---

## 4. Die `GmmFitResult`-Dataclass

`GmmFitResult` ist ein **unveränderlicher Ergebnis-Container**, der alle Ausgaben
eines einzelnen GMM-Fits bündelt. `fit_gmm_grid` erzeugt für jede getestete
Cluster-Anzahl (2–6) genau eine solche Instanz.

**Der Dekorator `@dataclass(frozen=True)`:**

- `@dataclass` generiert automatisch `__init__`, `__repr__`, `__eq__` usw. — man
  listet nur die Felder auf, kein Boilerplate-Konstruktor.
- `frozen=True` macht die Instanz **unveränderlich**: Nach der Erstellung lässt sich
  kein Feld mehr überschreiben (`result.bic = 5` wirft `FrozenInstanceError`). Bei
  einem berechneten Fit-Ergebnis erwünscht — es soll nicht versehentlich verändert
  werden.

**Die Felder:**

| Feld | Typ | Bedeutung |
|------|-----|-----------|
| `model` | `GaussianMixture` | Das **trainierte GMM-Objekt** mit gelernten Parametern (Mittelwerte, Kovarianzen, Gewichte); kann später neue Punkte vorhersagen. |
| `labels` | `np.ndarray` | Die **harte Regime-Zuordnung**: pro Zeitpunkt die Cluster-Nummer (0, 1, 2, …), via `model.predict(x)`. |
| `probabilities` | `np.ndarray` | Die **weiche Zuordnung**: Matrix `(n_zeitpunkte × n_cluster)` mit der Wahrscheinlichkeit je Regime (`model.predict_proba(x)`). |
| `bic` | `float` | **Bayesian Information Criterion** — bestraft mehr Cluster stark; **niedriger = besser**. |
| `aic` | `float` | **Akaike Information Criterion** — wie BIC, aber schwächere Komplexitätsstrafe; **niedriger = besser**. |
| `silhouette` | `float` | **Silhouetten-Score** — misst die Cluster-Trennung (−1 bis 1, **höher = besser**); bei `n < 2` nicht definiert → `NaN`. |

**Warum eine Dataclass statt eines Tupels?** Benannter Zugriff (`results[3].bic`) ist
selbsterklärend und weniger fehleranfällig als Positions-Indizes (`results[3][3]`),
und die Feldtypen dokumentieren die Ausgaben selbst.

---

## 5. Die Funktion `fit_gmm_grid`

Diese Funktion trainiert **mehrere GMMs mit unterschiedlicher Cluster-Anzahl** und
liefert für jede eine Diagnose zurück. So lässt sich die „beste" Regime-Anzahl
auswählen, statt sie willkürlich festzulegen.

**Signatur & Rückgabe:**

- `x: np.ndarray` — die (standardisierte) Faktor-Renditematrix
  `(n_zeitpunkte × n_faktoren)`.
- `n_components_list: Iterable[int]` — die zu testenden Cluster-Anzahlen (hier 2–6).
- `random_state: int = SEED` — fester Zufalls-Seed für **reproduzierbare** Ergebnisse.
- Rückgabe: `dict[int, GmmFitResult]` — bildet jede Cluster-Anzahl `n` auf ihr
  Fit-Ergebnis ab, z. B. `results[3]` = das GMM mit 3 Regimen.

**Was in der Schleife pro `n` passiert:**

1. Ein `GaussianMixture` wird konfiguriert:
   - `covariance_type="full"` — jedes Cluster erhält eine eigene, vollständige
     Kovarianzmatrix (beliebige Form/Ausrichtung), am flexibelsten.
   - `n_init=10` — 10 zufällige Neustarts; der beste Lauf wird behalten (gegen
     lokale Optima).
   - `reg_covar=1e-6` — kleine Regularisierung auf der Kovarianz-Diagonale für
     numerische Stabilität.
2. `model.fit(x)` trainiert das Modell.
3. `labels = model.predict(x)` → harte Zuordnung; `probs = model.predict_proba(x)`
   → weiche Wahrscheinlichkeiten.
4. `bic`/`aic` über `model.bic(x)` bzw. `model.aic(x)` (niedriger = besser).
5. `silhouette_score(x, labels)` misst die Trennung; bei `n < 2` → `NaN`.
6. Alles wird in einem `GmmFitResult` gebündelt und unter `results[n]` abgelegt.

Wie der Docstring betont: Für Mixture-Modelle sind **BIC und AIC** die eigentlich
passenden Auswahlkriterien; die **Silhouette** dient nur als grober Zusatz-Check
der Trennschärfe.

---

## 6. Exkurs: Was ist eine Kovarianzmatrix?

Eine **Kovarianzmatrix** beschreibt, wie mehrere Variablen gemeinsam streuen und
wie sie zusammenhängen — die Verallgemeinerung der Varianz auf mehrere Dimensionen.
Sie taucht oben im `covariance_type="full"`-Parameter auf.

**Grundidee:**

- **Varianz** (1 Variable): Streuung um den Mittelwert (ein Wert).
- **Kovarianz** (2 Variablen): Bewegen sie sich gemeinsam? Positiv → zusammen;
  negativ → gegenläufig; nahe 0 → kein linearer Zusammenhang.
- **Kovarianzmatrix** (n Variablen): fasst alle Varianzen und paarweisen
  Kovarianzen zusammen.

**Aufbau** (symmetrische `n × n`-Matrix Σ):

- **Diagonale** (Σᵢᵢ): die **Varianzen** der einzelnen Variablen.
- **Außerhalb der Diagonale** (Σᵢⱼ): die **Kovarianzen** zwischen i und j.
- **symmetrisch**: Σᵢⱼ = Σⱼᵢ.

Beispiel mit 3 Faktoren (Value, Momentum, Carry):

| Faktor | Value | Momentum | Carry |
|--------|-------|----------|-------|
| **Value** | Var(V) | Cov(V,M) | Cov(V,C) |
| **Momentum** | Cov(M,V) | Var(M) | Cov(M,C) |
| **Carry** | Cov(C,V) | Cov(C,M) | Var(C) |

**Anschaulich:** Die Kovarianzmatrix legt **Form und Ausrichtung** einer Punktwolke
fest. Große Diagonalwerte → breite Streuung entlang der Achse. Kovarianzen ≠ 0 →
die Wolke ist **schräg gekippt** (ellipsenförmig), weil die Variablen korreliert
sind.

**Bezug zum GMM:** Jedes Regime ist eine mehrdimensionale Normalverteilung, definiert
durch Mittelwert-Vektor und Kovarianzmatrix. `covariance_type="full"` gibt jedem
Cluster eine **eigene, vollständige** Kovarianzmatrix: ein „ruhiges" Regime hat eine
kleine, kompakte Matrix (geringe Streuung), ein „Krisen"-Regime eine große, breite
(hohe Volatilität, starke Korrelationen). `reg_covar=1e-6` addiert einen winzigen
Wert auf die Diagonale, damit die Matrix nicht **singulär** (nicht invertierbar)
wird und das Fitting numerisch stabil bleibt.

---

## 7. Faktor-Auswahl (`factor_cols`)

Im Abschnitt „Select Factors" legt eine einfache **Python-Liste mit Spaltennamen**
(Strings) fest, **welche Renditereihen** aus dem AQR-Datensatz ins Modell einfließen —
also die Merkmale (Features), aus denen die Marktregime gelernt werden.

Ein **Faktor** ist ein systematischer Renditetreiber (Risikoprämie), meist als
Long-Short-Portfolio konstruiert. Die neun ausgewählten Spalten gliedern sich in drei
Gruppen:

**1. Cross-Asset-Faktoren (`All asset classes …`) — über mehrere Anlageklassen hinweg:**

| Spalte | Bedeutung |
|--------|-----------|
| `All asset classes Value` | **Value**: kaufe „günstige", verkaufe „teure" Assets |
| `All asset classes Momentum` | **Momentum**: kaufe jüngste Gewinner, verkaufe Verlierer |
| `All asset classes Carry` | **Carry**: kaufe hochverzinsliche, verkaufe niedrigverzinsliche Assets |
| `All asset classes Defensive` | **Defensive**: Low-Risk-Anomalie (ruhige/stabile Titel bevorzugt) |

Das sind die vier klassischen Faktoren aus dem Kapitel-Hintergrund.

**2. Reine Aktienauswahl-Faktoren (`US Stock Selection …`):**

| Spalte | Bedeutung |
|--------|-----------|
| `US Stock Selection Value` | Value speziell innerhalb US-Aktien |
| `US Stock Selection Momentum` | Momentum speziell innerhalb US-Aktien |

**3. Markt-Faktoren (`… Market`) — Grundrendite ganzer Anlageklassen (Long-only Beta):**

| Spalte | Bedeutung |
|--------|-----------|
| `Equity indices Market` | globale Aktienmarkt-Rendite |
| `Fixed income Market` | Anleihenmarkt-Rendite |
| `Commodities Market` | Rohstoffmarkt-Rendite |

Durch die Mischung aus **Stil-Faktoren** (Value, Momentum, Carry, Defensive) und
**Markt-Faktoren** (Aktien, Anleihen, Rohstoffe) spannt die Auswahl einen breiten
„Faktorraum" auf — so kann das GMM sowohl auf Stil-Rotationen als auch auf allgemeine
Marktbewegungen reagieren.

**Weiterverarbeitung:**

```python
available_cols = [c for c in factor_cols if c in aqr_raw_pl.columns]
```

- Eine **List Comprehension**, die nur die tatsächlich im DataFrame vorhandenen
  Faktoren behält — ein **Schutzmechanismus**: Fehlt eine Spalte (Namensänderung,
  andere Datenversion), stürzt der Code nicht ab, sondern überspringt sie.

```python
for col in available_cols:
    na_count = aqr_raw_pl.select(pl.col(col).is_null().sum()).item()
    na_pct = na_count / aqr_raw_pl.height * 100
    print(f"  {col}: {na_pct:.1f}% missing")
```

- Für jeden verfügbaren Faktor wird der **Anteil fehlender Werte** (`null`) berechnet
  und ausgegeben: `pl.col(col).is_null().sum()` zählt die Nullwerte, geteilt durch
  `aqr_raw_pl.height` (Anzahl Monate) × 100 ergibt den Prozentsatz.
- Das ist eine **Datenqualitäts-Prüfung**: Faktoren mit langer Historie (ab 1927)
  sind vollständiger, jüngere Faktoren haben am Anfang Lücken. Wichtig, weil das GMM
  keine fehlenden Werte verarbeiten kann — diese werden im nächsten Schritt
  („Prepare Data for Clustering") behandelt.

---

## 8. `StandardScaler` — Standardisierung der Faktoren

Der `StandardScaler` (scikit-learn) **standardisiert** die Faktor-Daten
(z-Transformation), bevor sie ins Clustering gehen — direkt vor dem GMM.

**Was er macht:** Für **jede Spalte (jeden Faktor) einzeln**:

```
z = (x − μ) / σ
```

mit **μ** = Mittelwert und **σ** = Standardabweichung der Spalte. Ergebnis: Jeder
Faktor hat danach **Mittelwert 0** und **Standardabweichung 1**.

**Die zwei Schritte `fit` und `transform`:**

```python
scaler = StandardScaler()
factors_scaled = scaler.fit_transform(factors_df)
```

- **`fit`** — lernt μ und σ **pro Spalte** aus den Daten und merkt sie sich im
  `scaler`-Objekt.
- **`transform`** — wendet `(x − μ) / σ` an.
- **`fit_transform`** — beides in einem Aufruf. Weil beide getrennt sind, könnte man
  denselben Scaler später mit gemerkten μ/σ auf neue Daten anwenden
  (`scaler.transform(neue_daten)`).

**Warum nötig?** GMM (und K-Means) arbeiten mit **Distanzen bzw. Kovarianzen im
Merkmalsraum**. Ohne Standardisierung würden Faktoren mit **größerer Streuung den
Abstand dominieren**: Ein volatiler Markt-Faktor (z. B. `Equity indices Market`)
schwankt viel stärker als ein Long-Short-Faktor (z. B. `Carry`) und würde die Cluster
fast allein „ziehen". Nach der Standardisierung ist **jeder Faktor gleich gewichtet**
(alle σ = 1), sodass die Regime aus dem **gemeinsamen Muster aller Faktoren** entstehen
statt aus der zufälligen Maßstabsgröße einzelner Spalten. Zusätzlich sind gleichmäßig
skalierte Eingaben numerisch stabiler (passt zum `reg_covar`-Thema).

**Scope-Warnung:** Der Scaler wird — wie das GMM — auf der **gesamten Faktor-Historie**
gefittet. Das ist hier bewusst (deskriptives, ex-post Notebook). In einem **prädiktiven**
Setting wäre das **Look-ahead**, weil μ und σ Information aus der Zukunft enthielten;
lookahead-sicher müsste man den Scaler nur auf Vergangenheitsdaten fitten (walk-forward,
ab Kapitel 6).

| Aspekt | Bedeutung |
|--------|-----------|
| Operation | `z = (x − μ) / σ` pro Spalte |
| Ergebnis | jeder Faktor: Mittelwert 0, Std 1 |
| Zweck | alle Faktoren gleich gewichten, damit kein volatiler Faktor die Cluster dominiert |
| `fit` | lernt μ, σ je Spalte |
| `transform` | wendet die Formel an |
| Scope-Warnung | auf ganzer Historie gefittet → nur deskriptiv, nicht prädiktiv |

---

## 9. Modellauswahl-Kriterien: BIC, AIC & Silhouette

Diese drei Kennzahlen dienen dazu, die **optimale Anzahl der Regime (Cluster) `K`** zu
wählen. Sie werden in `fit_gmm_grid` für jede Cluster-Anzahl (2–6) berechnet und
anschließend verglichen (Abschnitt „model selection criteria").

**Das Grundproblem:** Mehr Cluster passen sich den Daten immer besser an — man könnte
`K` einfach erhöhen, bis die Anpassung „perfekt" ist. Das führt aber zu **Overfitting**
(man modelliert Rauschen statt echter Struktur). BIC und AIC lösen diesen Zielkonflikt,
indem sie **Anpassungsgüte gegen Modellkomplexität abwägen**.

### BIC — Bayesian Information Criterion

- **Idee:** `BIC = −2·(Log-Likelihood) + (Anzahl Parameter)·ln(n)` — der erste Term
  belohnt gute Anpassung, der zweite bestraft Komplexität (mehr Cluster, mehr Daten `n`).
- **`niedriger = besser`** (`np.argmin`); im Code: `model.bic(x)`.
- **Charakter:** bestraft zusätzliche Cluster **stark** (Faktor `ln(n)` ist bei ~100
  Jahren Monatsdaten groß) → tendiert zu **sparsamen** Modellen (wenige Regime), ideal
  für Interpretierbarkeit. Im Notebook bei **K=2** minimiert.

### AIC — Akaike Information Criterion

- **Idee:** `AIC = −2·(Log-Likelihood) + 2·(Anzahl Parameter)` — gleiche Struktur wie
  BIC, aber die Komplexitätsstrafe ist nur **`2` pro Parameter** statt `ln(n)`.
- **`niedriger = besser`**; im Code: `model.aic(x)`.
- **Charakter:** schwächere Strafe → **toleriert mehr Cluster**. Im Notebook **fällt AIC
  bis K=6 weiter**, würde also mehr Regime wählen als BIC.

> **BIC vs. AIC:** Beide bestrafen Komplexität, aber **BIC härter** → BIC wählt weniger,
> AIC mehr Cluster. Für interpretierbare Regime ist BIC die übliche Wahl.

### Silhouette-Score

- **Was gemessen wird:** Wie gut die Cluster **voneinander getrennt** und **in sich
  kompakt** sind — rein geometrisch, ohne Wahrscheinlichkeitsmodell.
- Pro Punkt: `s = (b − a) / max(a, b)` mit `a` = mittlere Distanz zum **eigenen**
  Cluster (Kompaktheit), `b` = mittlere Distanz zum **nächsten fremden** Cluster (Trennung).
- **Wertebereich −1 bis +1**, **`höher = besser`** (`np.argmax`):
  - nahe **+1** → gut getrennte, dichte Cluster,
  - nahe **0** → Cluster überlappen, Grenzen unklar,
  - **negativ** → Punkte liegen im Schnitt näher an einem *fremden* Cluster (schlechte
    Zuordnung).
- Im Code: `silhouette_score(x, labels)`, undefiniert bei `n < 2` → `NaN`.
- **Im Notebook:** bei **K=2** maximal (0,27), für **K≥4 negativ** (−0,02 bei K=4) →
  bei mehr als zwei Regimen überlappen die Cluster stark.

### Warum alle drei — und welche zählt?

- **BIC und AIC sind für Mixture-Modelle die eigentlich passenden Kriterien**, weil sie
  das zugrunde liegende **Wahrscheinlichkeitsmodell** (Likelihood) bewerten — genau das,
  was ein GMM ist.
- Die **Silhouette ist nur ein grober Zusatz-Check**: Sie kennt das GMM-Modell nicht,
  sondern misst nur Distanzen — ein Plausibilitäts-Signal, keine alleinige Grundlage.

| Kriterium | Misst … | Richtung | Charakter |
|-----------|---------|----------|-----------|
| **BIC** | Likelihood − starke Komplexitätsstrafe | niedriger = besser | wählt wenige Cluster (sparsam) |
| **AIC** | Likelihood − schwache Komplexitätsstrafe | niedriger = besser | toleriert mehr Cluster |
| **Silhouette** | geometrische Cluster-Trennung | höher = besser | modellunabhängiger Zusatz-Check |

**Fazit im Notebook:** BIC (K=2) und Silhouette (K=2) sind sich einig → **zwei Regime**
(„ruhig" vs. „gestresst") sind auf dem 1927–2024-Panel die robusteste Wahl. Nur AIC
würde mehr Regime nehmen — was aber Overfitting-anfälliger und schwerer zu
interpretieren wäre.
