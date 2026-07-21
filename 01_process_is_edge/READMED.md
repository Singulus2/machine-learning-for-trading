# Kapitel 1: Der Prozess ist dein Vorsprung

Das Kapitel begründet seine zentrale These: Beim Trading hängt dauerhafte Performance weniger davon ab, ein ausgeklügeltes Modell auszuwählen, als davon, einen disziplinierten Forschungsprozess aufrechtzuerhalten, der sich verändernde Märkte, verrauschte Signale und reale Reibungsverluste überstehen kann. Es vermittelt den Lesern ein brauchbares Vokabular für Marktveränderungen, zeigt, warum jüngste Schocks fragile Annahmen offengelegt haben, und interpretiert ML für das Trading neu — als ein Anpassungsproblem statt als einen Wettbewerb um die Modellauswahl.

## Lernziele

* Strukturbrüche, Regime, Data Drift, Concept Drift und Online-Erkennung unterscheiden und erklären, warum statische Trading-Modelle in sich verändernden Märkten an Qualität verlieren
* Den ML4T-Workflow als ein System von der Forschung bis zur Produktion erläutern, einschließlich seines Fundaments aus Dateninfrastruktur, seiner Scoping-Invarianten, seiner iterativen Forschungsmodule und der Rückkopplungsschleifen vom Live-Trading zurück in die Forschung
* Die Beweisgrenze zwischen Exploration und Bestätigung definieren und erklären, wie Trial-Logging, versiegelte Holdout-Daten und selektionsbewusste Auswertung die Forschungsintegrität wahren
* Beschreiben, wie kausale Inferenz und generative KI in einen disziplinierten Trading-Workflow passen, einschließlich der wesentlichen Vorteile, die sie bieten, und der neuen Fehlerarten, die sie einführen
* Regime-Denken, Umsetzbarkeitsprüfungen und Monitoring-Logik anwenden, um Strategie-Schwachstellen zu diagnostizieren und die Workflow-Disziplin über unabhängige und institutionelle Kontexte hinweg anzupassen

## Abschnitte

### 1.1 Warum Prozessdisziplin zählt

Dieser Abschnitt begründet die zentrale These des Kapitels: Beim Trading hängt dauerhafte Performance weniger davon ab, ein ausgeklügeltes Modell auszuwählen, als davon, einen disziplinierten Forschungsprozess aufrechtzuerhalten, der sich verändernde Märkte, verrauschte Signale und reale Reibungsverluste überstehen kann. Er vermittelt den Lesern ein brauchbares Vokabular für Marktveränderungen, zeigt, warum jüngste Schocks fragile Annahmen offengelegt haben, und interpretiert ML für das Trading neu — als ein Anpassungsproblem statt als einen Wettbewerb um die Modellauswahl.

### 1.2 Einführung in den ML4T-Workflow

Dieser Abschnitt stellt das Kernframework des Buches vor: einen Workflow von der Forschung bis zur Produktion, aufgebaut auf einer Point-in-Time-korrekten Dateninfrastruktur, expliziten Scoping-Regeln, iterativer Feature- und Modellentwicklung, realistischem Strategiedesign, Deployment-Disziplin und laufendem Monitoring. Der zentrale Mehrwert für die Leser besteht darin, dass er Trading-Forschung in einen gesteuerten Lebenszyklus mit auditierbaren Artefakten, klaren Übergaben und einer expliziten Grenze zwischen Exploration und Bestätigung verwandelt.

### 1.3 Kausale Inferenz und generative KI im Workflow

Dieser Abschnitt ordnet zwei moderne Methodenfamilien in den Workflow ein, statt sie als eigenständige Trends zu behandeln. Kausale Inferenz wird als ein Weg dargestellt, Mechanismen, Annahmen und Diagnosen zu schärfen; generative KI wird als ein Weg dargestellt, Forschung und die Verarbeitung unstrukturierter Daten auszuweiten, während sie zugleich neue Risiken wie Leakage, Halluzinationen und Workflow-Überfrachtung schafft. Für die Leser ist dies relevant, weil der Abschnitt deutlich macht, dass neue Werkzeuge den Wert von Disziplin erhöhen, statt sie zu ersetzen.

### 1.4 Marktregime: Veränderung ist die Konstante

Dieser Abschnitt macht Nicht-Stationarität operativ nutzbar. Er zeigt, wie Regime-Konzepte Erklärung, Robustheitsprüfungen und Live-Monitoring unterstützen können, betont aber zugleich, dass Regime in erster Linie eine Risikoperspektive und kein verlässliches Timing-Signal sind. Die Beispiele aus Faktoren und Makroökonomie machen die Idee greifbar: Regime-Methoden sind dann nützlich, wenn sie helfen, ungünstige Umfelder zu erkennen und sie mit vordefinierten Risikomaßnahmen zu verknüpfen.

- [`factor_regimes`](factor_regimes.ipynb) — Demonstriert unüberwachtes Lernen zur Erkennung von Marktregimen mithilfe von Gaussian Mixture Models (GMM) auf Faktor-Renditen aus dem Datensatz „AQR Century of Factor Premia".
- [`macro_regimes`](macro_regimes.ipynb) — Demonstriert unüberwachtes Lernen zur Erkennung von Marktregimen mithilfe makroökonomischer Indikatoren von FRED, validiert gegen die Volatilität und die Drawdowns des S&P 500.

### 1.5 In der Praxis: Unabhängig vs. institutionell

Dieser Abschnitt überträgt den Workflow in reale Betriebskontexte. Er erläutert, wie Institutionen von eingebauter Reibung und Prüfung profitieren, während unabhängige Forscher ihre eigene Governance durch Dokumentation, Checkpoints und explizite Abbruchkriterien schaffen müssen. Der praktische Nutzen ist groß: Er hilft den Lesern zu erkennen, wo Einzelakteure verwundbar sind, wo sie dennoch mithalten können und wie wiederverwendbare Infrastruktur die Forschungsqualität über die Zeit potenziert.

## Ausführen der Notebooks

```bash
# Vom Repository-Root aus
uv run python 01_process_is_edge/<notebook>.py

# Testmodus (reduzierte Daten via Papermill)
uv run pytest tests/test_notebooks.py -v -k "01_process_is_edge"
```

## Literaturverzeichnis

- **Andrew Ang and Geert Bekaert** (2002). [International Asset Allocation With Regime Shifts](https://doi.org/10.1093/rfs/15.4.1137). *Review of Financial Studies*.
- **Robert D. Arnott et al.** (2018). [A Backtesting Protocol in the Era of Machine Learning](https://doi.org/10.2139/ssrn.3275654).
- **Darrell Duffie** (2020). [Still the World's Safe Haven? Redesigning the U.S. Treasury Market After the COVID-19 Crisis](https://www.brookings.edu/wp-content/uploads/2020/05/WP62_Duffie_v2.pdf).
- **David Easley et al.** (2012). [The Volume Clock: Insights into the High Frequency Paradigm](https://doi.org/10.2139/ssrn.2034858).
- **Frank J. Fabozzi et al.** (2024). [Paradigm Shift: Embracing Holism in Causal Modeling for Investment Applications](https://doi.org/10.3905/jpm.2024.51.1.159). *The Journal of Portfolio Management*.
- **Frank J. Fabozzi and Caleb C. Stenholm** (2025). [Strategic Discipline: How Asset Management Mirrors Military Operations](https://doi.org/10.3905/jpm.2025.1.769). *The Journal of Portfolio Management*.
- **Ziang Fang and Jason Moore** (2025). What AI Can (and Can't Yet) Do for Alpha.
- **Stefano Giglio et al.** (2022). [Factor Models, Machine Learning, and Asset Pricing](https://doi.org/10.1146/annurev-financial-101521-104735). *Annual Review of Financial Economics*.
- **Campbell R. Harvey et al.** (2016). [...and the Cross-Section of Expected Returns](https://doi.org/10.1093/rfs/hhv059). *Review of Financial Studies*.
- **Blanka Horvath et al.** (2021). [Clustering Market Regimes Using the Wasserstein Distance](https://doi.org/10.2139/ssrn.3947905).
- **Antti Ilmanen et al.** (2021). [How Do Factor Premia Vary Over Time? A Century of Evidence](https://doi.org/10.2139/ssrn.3400998).
- **Justina Lee** (2025). [Man Group Says Agentic AI Is Now Devising Quant Trading Signals](https://www.bloomberg.com/news/articles/2025-07-10/man-group-says-agentic-ai-is-now-devising-quant-trading-signals). *Bloomberg.com*.
- **Andrew W. Lo** (2004). [The Adaptive Markets Hypothesis: Market Efficiency from an Evolutionary Perspective](https://papers.ssrn.com/abstract=602222).
- **Martin Luk** (2023). [Generative AI: Overview, Economic Impact, and Applications in Asset Management](https://doi.org/10.2139/ssrn.4574814).
- **Judea Pearl** (2019). [The seven tools of causal inference, with reflections on machine learning](https://doi.org/10.1145/3241036). *Communications of the ACM*.
- **Marcos López de Prado** (2018). The 10 Reasons Most Machine Learning Funds Fail. *The Journal of Portfolio Management*.
- **Marcos Lopez de Prado et al.** (2024). [The Case for Causal Factor Investing](https://doi.org/10.2139/ssrn.4774522).
- **Marcos López de Prado and Vincent Zoonekynd** (2025). [Correcting the Factor Mirage: A Research Protocol for Causal Factor Investing](https://doi.org/10.3905/jpm.2025.1.794). *The Journal of Portfolio Management*.
- **James Ryseff et al.** (2024). [The Root Causes of Failure for Artificial Intelligence Projects and How They Can Succeed: Avoiding the Anti-Patterns of AI](https://www.rand.org/pubs/research_reports/RRA2680-1.html).
- **Bernhard Schölkopf et al.** (2021). [Towards Causal Representation Learning](https://doi.org/10.48550/arXiv.2102.11107).
- **Stefan Studer et al.** (2021). [Towards CRISP-ML(Q): A Machine Learning Process Model with Quality Assurance Methodology](https://doi.org/10.3390/make3020020). *Machine Learning and Knowledge Extraction*.
- **A. Sinem Uysal and John M. Mulvey** (2021). [A Machine Learning Approach in Regime-Switching Risk Parity Portfolios](https://doi.org/10.3905/jfds.2021.1.057). *The Journal of Financial Data Science*.
