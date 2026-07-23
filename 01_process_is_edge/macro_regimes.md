# Erläuterungen zu `macro_regimes.py`

Dieses Dokument bündelt alle deutschen Erklärungen zum Notebook
[`macro_regimes.py`](macro_regimes.py). Es beginnt mit zwei **Konzept-Exkursen**
(PCA und Kovarianz), die für das Verständnis der Bausteine zentral sind. Danach
folgt der **Code-Durchgang** in der **Reihenfolge des py-Files** (von oben nach
unten): Ziel & Hintergrund, Imports, Helferfunktion, dann die **Core-Analyse**
(4 Indikatoren: Laden → Resampling → Standardisieren → GMM → Regime-Labels →
Volatilitäts-Validierung), die **erweiterte Analyse** (voller FRED-Panel,
hierarchisches Clustering, K-Means, PCA) und zuletzt der **Vergleich** von Core
vs. Extended vs. PCA.

Es ist das **Makro-Gegenstück** zu [`factor_regimes.py`](factor_regimes.py):
dort werden Regime aus **Faktor-Renditen** gelernt, hier aus **makroökonomischen
Indikatoren** (FRED). Konzepte, die beide teilen (GMM, `StandardScaler`,
Silhouette), sind hier knapper gehalten und verweisen auf die ausführliche
Darstellung in [`factor_regimes.md`](factor_regimes.md).

---

## Exkurs A: Was ist PCA und worauf basiert sie?

Die **PCA** (Principal Component Analysis / Hauptkomponentenanalyse) taucht unten
im Code-Durchgang (Abschnitt 16) als Vorverarbeitung vor dem Clustering auf. Hier
der konzeptionelle Hintergrund.

### Der Sinn von PCA

PCA hat im Kern **einen** Zweck: **Dimensionsreduktion unter maximalem Erhalt der
Varianz**. Aus vielen korrelierten Merkmalen werden wenige **unkorrelierte**
Achsen, die den größten Teil der Information tragen.

Reale Daten haben oft viele Features, die sich stark überlappen (korrelieren) —
genau wie der FRED-Panel hier (VIX und ICSA spiken gemeinsam, DFF und T10Y2Y
hängen zusammen). Die *effektive* Dimension ist viel kleiner als die Spaltenzahl.
PCA findet neue Achsen (**Hauptkomponenten**), die

- **orthogonal** (unkorreliert) sind und
- nach **erklärter Varianz** geordnet sind — PC1 fängt die meiste Streuung ein,
  PC2 die zweitmeiste usw.

Man behält die ersten `k` Komponenten und wirft den Rest weg → aus vielen Spalten
werden wenige, die trotzdem den Großteil der Varianz tragen.

**Wofür man das nutzt:**

| Ziel | Nutzen |
|------|--------|
| **Rauschunterdrückung** | Kleine Komponenten sind oft Rauschen; weglassen = sauberere Daten (genau der Zweck in Abschnitt 16). |
| **Kollinearität entfernen** | Für Modelle, die bei korrelierten Features instabil werden. |
| **Rechen-/Speicherersparnis** | Weniger Features = schnelleres, weniger overfittendes Modell. |
| **Visualisierung** | Hochdimensionale Daten auf 2–3 Achsen projizieren. |
| **Faktorstruktur finden** | In Finance: latente Risikofaktoren aus einem Renditepanel extrahieren. |

**Der Preis:** Die Komponenten sind **Linearkombinationen** aller
Originalfeatures → schwer interpretierbar. PCA tauscht **Interpretierbarkeit
gegen Kompaktheit**. Genau deshalb bleibt das Core-4-Modell unten trotz
PCA-Option relevant.

Merkregel: **PCA dreht das Koordinatensystem so, dass die Daten entlang möglichst
weniger Achsen maximal „ausgebreitet" sind — und lässt die uninteressanten Achsen
weg.**

### Worauf sklearns `PCA` basiert

Sklearns `PCA` basiert auf der **Singulärwertzerlegung (SVD)** der zentrierten
Datenmatrix — *nicht* auf der Eigenwertzerlegung der Kovarianzmatrix (auch wenn
beide mathematisch äquivalent sind).

1. **Zentrierung:** Von jeder Spalte wird der Mittelwert abgezogen. `PCA`
   zentriert immer, **skaliert aber nicht**. Deshalb sollte man bei Features mit
   unterschiedlichen Einheiten vorher standardisieren — im Notebook geschieht das
   über `scale` (Abschnitt 13).
2. **SVD** der zentrierten Matrix `X`:

   ```text
   X = U · Σ · Vᵀ
   ```

   - Die Zeilen von `Vᵀ` sind die **Hauptkomponenten** → `components_`
   - Die Singulärwerte `Σ` → `singular_values_`
   - Zusammenhang zur Varianz:
     `explained_variance_ = singular_values_² / (n_samples − 1)`

**Warum SVD statt Eigenzerlegung der Kovarianz?** Numerisch **stabiler und
genauer**. Die Kovarianzmatrix `XᵀX` explizit zu bilden quadriert die
Konditionszahl und verstärkt Rundungsfehler; SVD arbeitet direkt auf `X`.

**Solver-Varianten (`svd_solver='auto'` wählt automatisch):**

| Solver | Basis | Einsatz |
|--------|-------|---------|
| `full` | vollständige LAPACK-SVD | kleine/mittlere Daten |
| `covariance_eigh` | Eigenzerlegung der Kovarianzmatrix | viele Samples, wenige Features |
| `randomized` | randomisierte SVD (Halko et al. 2009) | große Matrizen, wenige Komponenten |
| `arpack` | truncated SVD via ARPACK | wenige Komponenten aus großer Matrix |

---

## Exkurs B: Was ist Kovarianz?

Kovarianz taucht implizit in mehreren Bausteinen dieses Notebooks auf (GMMs
`covariance_type="full"`, PCA, Korrelations-Heatmaps). Die ausführliche
**Kovarianz*matrix*** steht in Abschnitt 6 von
[`factor_regimes.md`](factor_regimes.md); hier die kompakte Klärung des Begriffs.

**Kovarianz misst, wie zwei Variablen gemeinsam variieren** — ob sie sich
tendenziell in dieselbe Richtung, in entgegengesetzte Richtungen oder unabhängig
bewegen.

```text
Cov(X, Y) = (1 / (n − 1)) · Σ (xᵢ − x̄)(yᵢ − ȳ)
```

Für jeden Datenpunkt: Abweichung von `X` zu seinem Mittelwert **mal** Abweichung
von `Y` zu seinem Mittelwert; dann mitteln.

**Das Vorzeichen ist der Kern** — betrachte das Produkt `(xᵢ − x̄)(yᵢ − ȳ)`:

| X über/unter Ø | Y über/unter Ø | Produkt |
|----------------|----------------|---------|
| über (+) | über (+) | **positiv** |
| unter (−) | unter (−) | **positiv** |
| über (+) | unter (−) | **negativ** |
| unter (−) | über (+) | **negativ** |

- **Cov > 0:** gleichläufig (X hoch → meist auch Y hoch)
- **Cov < 0:** gegenläufig (X hoch → meist Y niedrig)
- **Cov ≈ 0:** kein linearer Zusammenhang

**Wichtige Eigenschaften:**

- **Kovarianz mit sich selbst = Varianz:** `Cov(X, X) = Var(X)`.
- **Die Größe ist nicht interpretierbar:** Der Wert hängt von den **Einheiten**
  ab. Deshalb sagt „Cov = 4,2" für sich genommen nichts über die Stärke des
  Zusammenhangs.

**Kovarianz → Korrelation:** Um die Stärke vergleichbar zu machen, **normiert**
man durch die Standardabweichungen:

```text
Corr(X, Y) = Cov(X, Y) / (σ_X · σ_Y)     ∈ [−1, +1]
```

Das ergibt einen **einheitenlosen** Wert zwischen −1 und +1 — genau das, was die
Korrelations-Heatmap in Abschnitt 12 zeigt. Korrelation ist also nur
„standardisierte Kovarianz".

**Bezug zum Notebook:** Die **Kovarianzmatrix** sammelt die Kovarianzen aller
Indikator-Paare (Diagonale = Varianzen). Das GMM nutzt pro Regime eine eigene
solche Matrix (`covariance_type="full"`), PCA sucht die Achsen maximaler Varianz
in genau dieser Struktur, und in Finance ist die Kovarianzmatrix von Renditen das
zentrale Objekt fürs Portfoliorisiko (`Var = wᵀ Σ w`).

Merksatz: **Varianz beschreibt, wie stark eine Größe streut; Kovarianz, wie stark
zwei Größen zusammen streuen.**

---

## 1. Ziel & Hintergrund: Makro-Regime

Ein **Makro-Regime** ist eine Phase, in der sich die Volkswirtschaft strukturell
ähnlich verhält (z. B. „Expansion", „Krise", „Erholung", „Straffung/Inflation").
Anders als in `factor_regimes.py` werden die Regime hier nicht aus Marktrenditen,
sondern aus **volkswirtschaftlichen Kennzahlen** gelernt und danach an der
Realität des Aktienmarkts geprüft.

- **Datenquelle FRED:** Die Federal Reserve Bank of St. Louis stellt über die
  *Federal Reserve Economic Data* tausende Zeitreihen bereit — Arbeitslosigkeit,
  Zinsen, Inflation, Geldmenge usw. Das Notebook lädt einen aufbereiteten Auszug
  (~17 Reihen nach Qualitätsfilterung).
- **Unüberwacht:** Wie beim GMM in `factor_regimes.py` gibt es keine
  vorgegebenen Labels — die Regime werden direkt aus den Daten geclustert.
- **Zwei-Sigma-Vorbild, 4 Regime:** Wie im Faktor-Notebook orientiert sich die
  Wahl von **4 Regimen** am Two-Sigma-Ansatz. Anders als dort wird hier aber
  **kein BIC/AIC-Sweep** gefahren: Ziel ist **Interpretierbarkeit** (bekannte
  Wirtschaftsphasen wiedererkennen), nicht statistische Optimalität.
- **Zentrale Erkenntnis (steht schon im Header):** Makro-Regime decken sich
  sauberer mit **Volatilitäts-Umgebungen** als mit durchschnittlichen Renditen.
  Deshalb taugen Makro-Indikatoren eher fürs **Risikomanagement**
  (Volatilitäts-Verschiebungen antizipieren) als für die **Rendite-Prognose**.

> **Scope-Hinweis (wie im Faktor-Notebook):** Die Modelle werden auf der
> *gesamten* Historie gefittet und die Labels rückwirkend zugewiesen — eine
> **deskriptive** (ex-post) Charakterisierung, **kein** prädiktiver
> Klassifikator. Ein Kommentar im Code weist zusätzlich auf einen kleinen
> **Backward-Fill** an der Panel-Grenze hin, der einen Ein-Perioden-Look-ahead
> einführt: für ein Demo akzeptabel, für einen Backtest nicht.

---

## 2. Imports — was neu ist gegenüber `factor_regimes.py`

Die Basis (`polars`, `pandas`, `numpy`, `GaussianMixture`, `StandardScaler`,
`silhouette_score`) ist dieselbe wie im Faktor-Notebook. **Neu** hinzu kommen:

| Import | Zweck |
|--------|-------|
| `from sklearn.cluster import KMeans` | **K-Means**-Clustering als Vergleichsverfahren zum GMM (harte statt weiche Zuordnung). |
| `from sklearn.decomposition import PCA` | **Hauptkomponentenanalyse** — Dimensionsreduktion/Rauschfilterung vor dem Clustering. |
| `from scipy.cluster.hierarchy import cophenet, dendrogram, linkage` | **Hierarchisches (agglomeratives) Clustering**: Linkage-Matrix, Dendrogramm, Cophenetische Korrelation. |
| `from scipy.spatial.distance import pdist` | paarweise Distanzen (Eingabe für `cophenet`). |
| `from sklearn.preprocessing import StandardScaler, scale` | zusätzlich zur `StandardScaler`-Klasse die **Funktion** `scale` (Standardisierung in einem Aufruf, ohne Objekt zum Merken von μ/σ). |
| `seaborn as sns`, `matplotlib.gridspec.GridSpec` | Heatmaps/Clustermaps und das mehrspaltige Swim-Lane-Layout für Abbildung 1.6. |
| `load_macro`, `load_sp500_index` | Projekt-Loader für den FRED-Panel bzw. den S&P-500-Index. |
| `set_global_seeds` | setzt alle Zufalls-Seeds zentral → **Reproduzierbarkeit**. |

`SEED = 42` steht in einer mit `tags=["parameters"]` markierten Zelle:
**Papermill** kann diesen Wert beim automatisierten Ausführen (Tests)
überschreiben.

---

## 3. Die Helferfunktion `plot_regime_heatmap`

Eine wiederverwendbare Funktion, die Regime-Zuordnungen als **Heatmap** zeichnet.
Sie wird für GMM **und** K-Means genutzt, damit beide Ergebnisse **im selben
Format** vergleichbar sind.

**Kernparameter:**

- `assignments` — entweder eine **Wahrscheinlichkeitsmatrix**
  `(n_monate × n_regime)` (GMM) **oder** ein Vektor **harter Labels**
  `(n_monate,)` (K-Means).
- `is_probability` — steuert genau diese Unterscheidung.

**Der entscheidende Trick (One-Hot-Kodierung):** Sind es harte Labels, werden sie
in eine 0/1-Matrix umgewandelt, damit sie dasselbe Bildformat wie die
GMM-Wahrscheinlichkeiten haben:

```python
one_hot = np.zeros((len(assignments), n_regimes))
one_hot[np.arange(len(assignments)), assignments] = 1
```

Für jede Zeile (Monat) wird genau in der Spalte des zugewiesenen Regimes eine `1`
gesetzt. So ergibt eine harte Zuordnung eine „harte" Heatmap (nur 0 oder 1),
während das GMM Graustufen zwischen 0 und 1 zeigt (Unsicherheit).

**Darstellung:** `ax.imshow(data.T, …, cmap="Blues", vmin=0, vmax=1)` —
transponiert, sodass **Zeit auf der x-Achse** (Jahre) und **Regime auf der
y-Achse** liegen. Die x-Ticks werden auf **Jahreswechsel** gesetzt (jeder zweite
beschriftet).

---

## 4. FRED-Daten laden

```python
macro_raw = load_macro()
if macro_raw["timestamp"].dtype == pl.Date:
    macro_raw = macro_raw.with_columns(pl.col("timestamp").cast(pl.Datetime))
```

- Lädt den vollständigen FRED-Panel als **Polars**-DataFrame.
- Der Cast von `Date` auf `Datetime` ist **technisch nötig**: das später
  verwendete `group_by_dynamic` (zeitbasiertes Resampling) verlangt einen
  `Datetime`-Typ, nicht `Date`.

Die Markdown-Tabelle im Notebook listet die verfügbaren Indikatoren nach
Kategorie (Arbeitsmarkt, Zinsen, Preise, Volatilität, Kredit, Immobilien,
Geldmenge). Für die **Core-Analyse** werden daraus nur **vier** ausgewählt.

---

## 5. Core-Analyse: Auswahl der 4 Indikatoren

```python
CORE_INDICATORS = ["unrate", "dff", "t10y2y", "cpiaucsl"]
```

Vier fundamentale Indikatoren, die reale Wirtschaftsbedingungen abbilden:

| Kürzel | Indikator | Was er misst |
|--------|-----------|--------------|
| **UNRATE** | Arbeitslosenquote (%) | Gesundheit des Arbeitsmarkts |
| **DFF** | Federal Funds Rate (%) | geldpolitischer Kurs der Fed |
| **T10Y2Y** | 10J-2J-Treasury-Spread | Steigung der Zinskurve → **Rezessionssignal** (invertiert = Warnung) |
| **CPIAUCSL** | Verbraucherpreisindex | wird später in **Inflationsrate (YoY)** umgerechnet |

Die Auswahl erfolgt **case-insensitive** (`col.lower() == indicator`), damit
unterschiedliche Groß-/Kleinschreibung in den Spaltennamen nicht stört —
dasselbe robuste Muster wie die Spaltenprüfung in `factor_regimes.py`.

---

## 6. Resampling auf Monatsbasis (`group_by_dynamic`)

```python
macro_monthly = (
    macro_raw.select([DATE_COL] + core_cols)
    .sort(DATE_COL)
    .group_by_dynamic(DATE_COL, every="1mo", label="right")
    .agg([pl.col(c).last() for c in core_cols])
    .fill_null(strategy="forward")
    .fill_null(strategy="backward")
    .drop_nulls(subset=core_cols)
)
```

- **`group_by_dynamic(..., every="1mo", label="right")`** gruppiert die (teils
  täglichen/wöchentlichen) Reihen in **Monatsfenster**; `label="right"` datiert
  jedes Fenster auf sein **Monatsende**.
- **`.agg(pl.col(c).last())`** nimmt pro Monat den **letzten** Wert (jüngste
  Beobachtung des Monats).
- **`fill_null("forward")`** trägt den letzten bekannten Wert über
  **Veröffentlichungs-Lücken** hinweg (Makrodaten erscheinen verzögert und in
  unterschiedlichen Frequenzen).
- **`fill_null("backward")`** füllt führende Nullwerte in frühen Monaten. Der
  Code-Kommentar ist ehrlich: Dieser Rückwärts-Fill erzeugt einen
  **Ein-Perioden-Look-ahead** an der Panel-Grenze — für ein Regime-Demo okay,
  für einen Backtest nicht.

Anschließend wird auf **ab 2002** gefiltert, weil dort die meisten FRED-Reihen
gute Abdeckung haben.

### Exkurs: Was ist Resampling?

**Resampling** heißt, eine Zeitreihe von **einer zeitlichen Frequenz in eine
andere** zu überführen — die Datenpunkte werden auf ein **neues Zeitraster**
umgerechnet. Genau das tut `group_by_dynamic` hier: aus (teils täglichen,
wöchentlichen) FRED-Reihen werden **Monatswerte**.

Zwei Richtungen:

| Richtung | Was passiert | Beispiel |
|----------|--------------|----------|
| **Downsampling** | fein → grob; mehrere Werte werden **aggregiert** | täglich → monatlich (viele Tage → ein Wert) |
| **Upsampling** | grob → fein; es entstehen **Lücken**, die gefüllt werden | monatlich → täglich (fehlende Tage füllen/interpolieren) |

Das Notebook macht **Downsampling** (fein → monatlich). Der entscheidende Punkt
dabei: Man muss eine **Aggregationsregel** wählen — es gibt nicht *die eine*
richtige:

- **`last()`** — letzter Wert der Periode; passt zu **Bestandsgrößen** wie
  Zinsen, Preisen, Arbeitslosenquote → **das nutzt das Notebook**.
- **`mean()`** — Periodendurchschnitt (glättet stärker).
- **`sum()`** — Summe; sinnvoll für **Flussgrößen** (Volumen, Umsätze).
- **`first()` / `min()` / `max()`** — je nach Zweck.

**Zuordnung zum Code:**

| Baustein | Bedeutung |
|----------|-----------|
| `every="1mo"` | neues Raster = **Monatsfenster** |
| `label="right"` | jedes Fenster wird auf sein **Monatsende** datiert (`label="left"` wäre der Monatsanfang) |
| `.agg(pl.col(c).last())` | Aggregationsregel: pro Monat der **letzte** Wert |

Dasselbe passiert später für den S&P 500 in pandas-Syntax:
`sp500_raw["close"].resample("ME").last()` (`"ME"` = *month end*).

**Warum überhaupt resampeln?**

1. **Frequenzen angleichen:** Die FRED-Reihen kommen in **gemischten Frequenzen**
   (Arbeitslosenquote monatlich, Fed Funds Rate/VIX täglich …). Fürs gemeinsame
   Clustering braucht man **ein einheitliches Raster** — hier Monatsende.
2. **Signal passend zur Fragestellung machen:** Makro-Regime bewegen sich über
   Monate, nicht über Tage — Tagesrauschen wäre kontraproduktiv.
3. **Alignment:** Erst auf gemeinsamer Frequenz lassen sich die Reihen
   zusammenführen und mit dem S&P 500 abgleichen (Abschnitt 10,
   `reindex(..., method="nearest")`).

**Die Resampling-Falle (relevant fürs Trading):** Der `last()`-Wert gilt am
**Monatsende**, aber Makrodaten werden oft **verzögert veröffentlicht** (der
„Januar-Wert" der Arbeitslosenquote ist real erst Anfang Februar bekannt). Genau
deshalb der Hinweis oben zum **Backward-Fill**: Er kann Information aus der
Zukunft ans Monatsende ziehen → **Look-ahead-Bias**. Für ein deskriptives Demo
akzeptabel, für einen Backtest nicht.

Merksatz: **Resampling = dieselbe Zeitreihe auf ein neues Zeitraster bringen —
beim Vergröbern musst du aggregieren (wie?), beim Verfeinern auffüllen (womit?).**

---

## 7. Standardisieren fürs Clustering — und CPI → YoY

```python
macro_df["cpi_yoy"] = macro_df["cpiaucsl"].pct_change(12) * 100
macro_df = macro_df.drop(columns=["cpiaucsl"]).dropna()
macro_scaled = StandardScaler().fit_transform(macro_df)
```

Zwei Schritte:

1. **CPI-Level → Inflationsrate (YoY):** `pct_change(12)` bildet die prozentuale
   Veränderung zum **Vorjahresmonat**. Das ist entscheidend, denn der
   **CPI-Level trendet ständig nach oben** (nicht-stationär). Würde man auf dem
   Level clustern, erfasste das Modell „**früh vs. spät**" statt „**inflationär
   vs. nicht-inflationär**". Dieselbe Logik wie „Raten statt Levels" aus den Key
   Takeaways.
2. **`StandardScaler`:** z-Transformation `(x − μ)/σ` **pro Spalte**, sodass alle
   Indikatoren Mittelwert 0 und Std 1 haben. Ohne das würde der Indikator mit der
   größten numerischen Streuung die Cluster dominieren. (Ausführliche Begründung:
   Abschnitt 8 in [`factor_regimes.md`](factor_regimes.md).)

---

## 8. GMM mit 4 Regimen

```python
gmm_macro = GaussianMixture(
    n_components=4, covariance_type="full",
    random_state=SEED, n_init=10, reg_covar=1e-6,
)
gmm_macro.fit(macro_scaled)
macro_labels = gmm_macro.predict(macro_scaled)       # harte Labels
macro_probs  = gmm_macro.predict_proba(macro_scaled) # weiche Wahrscheinlichkeiten
```

Identische Konfiguration wie im Faktor-Notebook (siehe dort Abschnitt 2 & 6):

- **`n_components=4`** — vier Regime, fest gewählt (kein Sweep).
- **`covariance_type="full"`** — jedes Regime bekommt eine **eigene,
  vollständige Kovarianzmatrix** (beliebig geformte/gekippte Ellipse). Exkurs
  Kovarianz(matrix): Exkurs B oben bzw. Abschnitt 6 in
  [`factor_regimes.md`](factor_regimes.md).
- **`n_init=10`** — 10 Neustarts gegen lokale EM-Optima.
- **`reg_covar=1e-6`** — numerische Stabilität (keine singuläre Kovarianz).

Der **Silhouette-Score** (`> 0.25` = brauchbare Struktur) misst die
Cluster-Trennung. Der bewusste **Verzicht auf BIC/AIC** hier ist im Notebook
begründet: Ziel ist das Wiedererkennen bekannter Wirtschaftsphasen, nicht die
statistisch optimale Cluster-Anzahl.

### Exkurs: Was misst der Silhouette-Score?

Der **Silhouette-Score** (`silhouette_score(...)`, taucht im Notebook mehrfach
auf) misst, **wie gut ein Clustering ist** — konkret, wie **klar getrennt** und
**in sich kompakt** die Cluster sind. Er ist ein rein **geometrisches** Gütemaß
(nur Distanzen) und **modellunabhängig** — egal, ob GMM oder K-Means die Cluster
erzeugt hat.

**Idee — zwei Distanzen pro Punkt** (hier: pro Monat):

- **a** = mittlere Distanz zu den Punkten im **eigenen** Cluster → **Kompaktheit**
- **b** = mittlere Distanz zum **nächstgelegenen fremden** Cluster → **Trennung**

Daraus der Wert je Punkt; der Gesamt-Score ist der **Durchschnitt** über alle
Punkte:

```text
s = (b − a) / max(a, b)
```

**Interpretation** (Bereich **−1 bis +1**, **höher = besser**):

| Wert | Bedeutung |
|------|-----------|
| nahe **+1** | viel näher am eigenen als am fremden Cluster → gut getrennt, dicht |
| nahe **0** | auf der Grenze zweier Cluster → Cluster überlappen |
| **negativ** | näher an einem fremden Cluster → wahrscheinlich falsch zugeordnet |

Grobe (selbst heuristische) Faustregeln: **> 0,5** deutlich, **0,25–0,5**
brauchbar (die Schwelle im Notebook), **nahe 0** schwach, **negativ** daneben.

**Wozu im Notebook:** Der Score ist das **Vergleichskriterium** zwischen den
Ansätzen — Core ~0,25, Extended ~0,42, GMM vs. K-Means 0,42 vs. 0,45 (Abschnitt
17, Key Takeaways).

**Einschränkungen:**

1. **Undefiniert bei einem Cluster** (`n < 2`) → `NaN`.
2. **Für ein GMM nur ein Zusatz-Check:** Die Silhouette kennt das
   GMM-Wahrscheinlichkeitsmodell nicht; die eigentlich passenden Kriterien wären
   **BIC/AIC** (siehe Abschnitt 9 in [`factor_regimes.md`](factor_regimes.md)) —
   die hier aber bewusst zugunsten der Interpretierbarkeit weggelassen werden.
3. **Bevorzugt kugelförmige, gleich große Cluster** — sie „bestraft" tendenziell
   die beliebig geformten Ellipsen, die `covariance_type="full"` gerade zulässt.
   Ein GMM kann also inhaltlich gut sein und trotzdem eine mäßige Silhouette
   haben.

Merksatz: **Silhouette = „passt jeder Punkt besser zu seinem eigenen als zum
nächsten fremden Cluster?" — gemittelt über alle Punkte, von −1 (falsch) über 0
(Grenzfall) bis +1 (sauber getrennt).**

---

## 9. Regime-Charakteristik & interpretierbare Labels

```python
regime_means = regime_chars.groupby("regime").mean()
```

Zunächst werden je Cluster die **Mittelwerte** der (Roh-)Indikatoren berechnet —
so wird ein anonymes Cluster (0, 1, 2, 3) wirtschaftlich lesbar.

`create_regime_labels` vergibt dann **sprechende Namen** über eine
**Prioritäts-Kaskade** auf den Cluster-Mittelwerten:

```python
if   c["unrate"] > 10:                          "Crisis"
elif c["unrate"] > 6 and c["dff"] < 0.5:        "Recovery"
elif c["dff"] > 3 and c["t10y2y"] < 0.5:        "Tightening"
elif c["cpi_yoy"] > 4:                          "Inflation"
elif c["unrate"] < 5 and c["dff"] < 2:          "Expansion"
else:                                           "Transition"
```

- Die Reihenfolge ist wichtig: Die **erste zutreffende** Bedingung gewinnt (z. B.
  schlägt „Crisis" bei sehr hoher Arbeitslosigkeit alles andere).
- Die Schwellenwerte sind **heuristisch** und auf das **US-Makroumfeld
  2002–2025** abgestimmt (der Docstring sagt das offen).
- Ein Nachlauf sichert **eindeutige Labels**: Kollidieren zwei Cluster auf
  demselben Namen, wird das mit höherer Arbeitslosigkeit mit dem Zusatz
  `(High Unemp.)` versehen.

Anders als das rein datengetriebene GMM ist dies eine **domänenwissen-basierte
Nachbeschriftung** — sie macht die Regime für Leser interpretierbar.

---

## 10. Validierung gegen den Aktienmarkt (S&P 500)

Der Kern-Test der Eingangs-Hypothese: **Passen die Makro-Regime zu
unterschiedlichen Volatilitäts- und Drawdown-Umgebungen?**

```python
sp500_monthly["returns"] = sp500_monthly["close"].pct_change()
...
sp500_aligned = sp500_df.reindex(macro_df.index, method="nearest",
                                 tolerance=pd.Timedelta("5D"))
sp500_aligned["drawdown"]   = (close − peak) / peak
sp500_aligned["volatility"] = returns.rolling(12).std() * np.sqrt(12)
```

- **`reindex(..., method="nearest", tolerance="5D")`** richtet die monatlichen
  S&P-500-Werte an den Makro-Datumsstempeln aus (nächster Handelstag, max. 5 Tage
  Toleranz).
- **Drawdown:** Abstand vom bisherigen Höchststand (`cummax`) — misst den
  maximalen Verlust.
- **Annualisierte Volatilität:** rollierende 12-Monats-Standardabweichung der
  Renditen, mit `√12` aufs Jahr skaliert.

Dann werden je **Regime-Label** Statistiken aggregiert (mittlere Rendite, Vol,
Monatszahl, max. Drawdown) und **nach Volatilität sortiert**. Ergebnis (siehe Key
Takeaways): Die Regime ordnen sich sauber entlang der Volatilität — von
**Expansion (~12 %)** bis **Crisis (~16 %)** — was die These „Makro ⇒ Risiko,
nicht Rendite" stützt.

---

## 11. Abbildung 1.6: Swim-Lane-Timeline

`plot_regime_timeline_validation()` baut die **publikationsreife Abbildung 1.6**
des Kapitels: pro Regime eine **Swim Lane** (Zeitband, das die aktiven Monate
einfärbt), daneben **Balken für Volatilität und Max-Drawdown**.

- **`GridSpec`** legt das mehrspaltige Raster an (Swim Lane | Vol | Drawdown).
- **`axvspan`** färbt die Monate, in denen ein Regime aktiv ist.
- Die Palette (`REGIME_COLORS`, hellgrau → schwarz) ist bewusst
  **graustufentauglich** (für den S/W-Druck) und **von hell nach dunkel entlang
  steigender Volatilität** geordnet.
- Vertikale Linien markieren die **Krisen-Ereignisse** GFC (2008), COVID (2020),
  Inflation (2022).

**Persistenz statt Neuberechnung:** Die Rohdaten der Abbildung werden per
`np.savez(... inputs.npz)` gespeichert. Ein separates Buch-Build-Skript
(`generate_figure_1_6_...py`) rendert daraus die finale Grafik, **ohne** die
gesamte Clustering-Pipeline erneut zu fitten — schneller und reproduzierbar.

---

## 12. Korrelations-Heatmap der Core-Indikatoren

```python
sns.heatmap(macro_df.corr(), annot=True, cmap="RdBu_r", center=0, ...)
```

Zeigt die paarweisen Korrelationen der vier Indikatoren. Die Interpretation im
Notebook:

- **UNRATE ↔ T10Y2Y positiv (~0,70):** Verschlechtert sich der Arbeitsmarkt,
  versteilt sich meist die Zinskurve (die Fed senkt das kurze Ende).
- **DFF ↔ T10Y2Y negativ (~−0,73):** Zinserhöhungszyklen verflachen oder
  invertieren die Kurve.
- **CPI YoY weitgehend orthogonal** zu den anderen dreien — Inflationsphasen
  können mit Rezession *und* Expansion koexistieren.

Kernbotschaft: Weil einzelne Indikatoren verrauschte Signale sind, lohnt sich das
**gemeinsame Clustering** aller Indikatoren (statt einer Einzelregel).

---

## 13. Erweiterte Analyse: der volle FRED-Panel

Jetzt werden **alle** FRED-Reihen mit ausreichender Abdeckung genutzt (~17–25
Indikatoren) — ein **reicheres, aber verrauschteres** Bild.

```python
null_fractions = { col: <Anteil Nullwerte> for col in value_cols_full }
good_cols = [col for col, frac in null_fractions.items()
             if frac < 0.5 and col not in {"sp500", "SP500"}]
```

- **Qualitätsfilter:** Reihen mit **> 50 % fehlenden Werten** fliegen raus.
- **Markt-Ausschluss:** Die S&P-500-Spalte wird **explizit ausgeschlossen** — sie
  ist das **Validierungsziel**, dürfte also nicht als Input ins Clustering
  fließen (sonst würde man teils zirkulär auf dem Markt selbst clustern).
- **Standardisierung** hier über die **Funktion** `.apply(scale)` (spaltenweise
  z-Transformation) statt über ein `StandardScaler`-Objekt — funktional
  äquivalent, nur ohne gemerkte μ/σ.

Ein Gitter aus Liniencharts visualisiert die standardisierten Reihen. Die
Interpretation hebt hervor, dass vor allem **VIX, ICSA (Erstanträge), DFF und
T10Y2Y** die Regime tragen, während träge Reihen (Immobilien, Geldmenge) wenig
Regime-Information liefern.

---

## 14. Hierarchisches Clustering (Cophenetische Korrelation)

Zwei verschiedene hierarchische Sichten:

**a) Auf Indikatoren (Clustermap):**

```python
sns.clustermap(macro_data_full.corr(), cmap="RdBu_r", center=0, ...)
```

Clustert die **Korrelationsmatrix** und offenbart **Blöcke** verwandter
Indikatoren (Arbeitsmarkt/Zinskurve, Stress-Block VIX/ICSA/High-Yield,
Wachstum/Preise, Kurzfristzinsen).

**b) Auf Beobachtungen (Monaten):**

```python
Z_full = linkage(macro_data_full, "ward")
c, _ = cophenet(Z_full, pdist(macro_data_full))
```

- **`linkage(..., "ward")`** baut den hierarchischen Baum; **Ward** minimiert die
  Varianzzunahme beim Verschmelzen von Clustern.
- **Cophenetische Korrelation `c`:** misst, wie **treu das Dendrogramm die
  ursprünglichen paarweisen Distanzen** bewahrt. Faustregel: **> 0,7 = gut**;
  hier **0,71** → der Baum ist eine verlässliche Zusammenfassung, die
  Block-Struktur ist **echte Hierarchie**, kein Artefakt der Linkage-Wahl.
- Das **Dendrogramm** (`no_labels=True`) illustriert den Baum; die Kernaussage
  steht im Titel (Cophenetische Korrelation).

---

## 15. GMM vs. K-Means

Beide Verfahren finden 4 Regime — der Unterschied:

| Aspekt | GMM | K-Means |
|--------|-----|---------|
| Zuordnung | **weich** (Wahrscheinlichkeiten, Unsicherheit quantifiziert) | **hart** (jeder Monat genau ein Regime) |
| Clusterform | beliebige Ellipsen (`covariance_type="full"`) | kugelförmig, gleich groß |
| Ausgabe | `predict_proba` (Graustufen-Heatmap) | `fit_predict` (0/1-Heatmap) |

```python
gmm_full.fit(macro_data_full)
kmeans_full = KMeans(n_clusters=4, random_state=SEED, n_init=10)
```

Beide werden per **Silhouette** verglichen und über `plot_regime_heatmap`
(Abschnitt 3) im selben Format dargestellt. Ergebnis (Key Takeaways): ähnliche
Trennschärfe (0,42 vs. 0,45), aber GMM liefert zusätzlich
**Wahrscheinlichkeiten**, die Regime-**Unsicherheit** sichtbar machen.

---

## 16. PCA-Vorverarbeitung

```python
n_pca = min(10, macro_data_full.shape[1])
pca = PCA(n_components=n_pca)
reduced = pca.fit_transform(macro_data_full)
cumvar = pd.Series(pca.explained_variance_ratio_).cumsum()
```

**Idee:** Vor dem Clustering die Dimensionen reduzieren, um **Rauschen zu
filtern**. Bei ~25 stark korrelierten Indikatoren steckt die eigentliche
Information in wenigen Achsen. Die konzeptionelle Grundlage steht oben in
**Exkurs A**.

- **`PCA` (scikit-learn)** basiert auf der **Singulärwertzerlegung** der
  zentrierten Datenmatrix und dreht das Koordinatensystem so, dass die **ersten
  Komponenten die meiste Varianz** tragen. Wichtig: die Daten sind hier bereits
  standardisiert (Abschnitt 13), was für PCA auf gemischten Einheiten korrekt ist.
- **`explained_variance_ratio_.cumsum()`** zeigt, wie viel Gesamtvarianz die
  ersten `k` Komponenten kumulativ erklären — die üblichen wenigen Komponenten
  reichen für den Großteil.
- Das **GMM wird dann auf `reduced`** (den PCA-Scores) gefittet statt auf allen
  Rohindikatoren, und wieder per Silhouette bewertet.

---

## 17. Vergleich: Core vs. Extended vs. PCA

```python
silhouette_compare = pd.DataFrame({
    "Model": ["Core (4 indicators)",
              f"Extended ({n} indicators)",
              "Extended + PCA"],
    "Silhouette": [core_sil, extended_sil, pca_sil],
})
```

Der abschließende Vergleich stellt die drei Ansätze anhand des
**Silhouette-Scores** gegenüber und wählt automatisch eine Interpretation:

- Ist **Core** besser → die 4 Kernindikatoren trennen sauberer, zusätzliche
  Reihen bringen Rauschen.
- Ist **Extended** besser → der breitere Panel fängt trotz Rauschen mehr echte
  wirtschaftliche Variation ein.

Eine Doppel-Heatmap zeigt Core- und Extended-Regime zusätzlich **visuell**
untereinander.

---

## 18. Key Takeaways (Zusammenfassung des Notebooks)

- **Makro-Indikatoren decken sich mit realisierter Volatilität:** Die mittlere
  annualisierte Vol steigt von ~12,0 % (Expansion, 77 Monate) bis ~16,0 %
  (Crisis, nur 4 Monate) — die Crisis-Zahl ist wegen der kleinen Stichprobe eher
  eine anekdotische Obergrenze.
- **Mehr Indikatoren verbessern die Cluster-Qualität** (Silhouette 0,42 vs.
  0,25), aber das **Core-Modell ist interpretierbarer** — ein Zielkonflikt, den
  der Anwendungsfall entscheidet.
- **Die Hierarchie ist echt:** Cophenetische Korrelation 0,71 (über der
  0,7-Marke).
- **Raten statt Levels:** CPI als **YoY-Veränderung**, nicht als Level — sonst
  clustert man „früh vs. spät" statt „inflationär vs. nicht".
- **GMM vs. K-Means:** ähnliche Güte, aber GMM quantifiziert
  **Regime-Unsicherheit**.

**Buch-Bezug:** §1.4 rahmt diese Regime als Inputs fürs **Risikomanagement**
(Exposure-Caps, Hedging-Trigger, De-Risking-Regeln) — **nicht** als
Rendite-Prognose. Abbildung 1.6 ist das oben erzeugte Makro-Regime-Panel.
