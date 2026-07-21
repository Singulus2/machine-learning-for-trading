# Docker-Compose-Konfiguration für ML4T

Diese Konfiguration gehört zum Buch **„Machine Learning for Algorithmic Trading" (ML4T) — 3rd Edition**. Sie stellt sicher, dass Leser alle Code-Beispiele (Jupyter Notebooks, Datenbank-Benchmarks, GPU-beschleunigtes Machine Learning) direkt ausführen können, ohne tagelang Abhängigkeiten auf dem eigenen PC installieren zu müssen.

Hier ist die verständliche Aufschlüsselung, was dieser Code im Einzelnen tut:

## 1. Die Basis-Konfiguration (`x-common: &common`)

Ganz oben wird ein sogenannter YAML-Anchor (`&common`) definiert. Das ist eine Schablone mit Einstellungen, die später von fast allen Containern wiederverwendet wird, um Schreibarbeit zu sparen:

- **User & Verzeichnisse:** Der Container läuft mit deiner lokalen User-ID (UID), damit erstellte Dateien dir und nicht `root` gehören. Dein aktueller Projektordner wird als `/app` in den Container gespiegelt (Änderungen am Code sind sofort wirksam). Ein Datenverzeichnis (`/data`) wird für den Download von Marktdaten bereitgestellt.
- **Umgebungsvariablen:** Pfade für Python, Numba- und Matplotlib-Caches werden gesetzt, damit der Container performant läuft.

## 2. Die Haupt-Anwendungen (Services)

Die Konfiguration teilt die Werkzeuge in verschiedene Container auf, die du je nach Kapitel im Buch startest:

### `ml4t` & `ml4t-gpu` (Der Standard-Arbeitsplatz)

Das ist die Hauptumgebung für die meisten Kapitel (Ch01–Ch27).

- Sie startet einen **Jupyter Lab Server**, den du im Browser unter [http://localhost:8888](http://localhost:8888) aufrufst.
- Nutzt topaktuell **Python 3.14** und **PyTorch** (für Deep Learning).
- Die `ml4t-gpu`-Variante reicht deine physische NVIDIA-Grafikkarte in den Container durch, damit neuronale Netze per CUDA beschleunigt berechnet werden können.

### `benchmark` & `benchmark-full` (Datenbank-Tests)

In Kapitel 2 geht es um die Performance-Unterschiede bei der Speicherung riesiger Finanzdaten.

- **`benchmark`:** Läuft überall (auch auf Apple Silicon Macs) und testet Formate wie Parquet, HDF5 oder die performante Embedded-Datenbank DuckDB. Es bindet bei Bedarf auch die kommerzielle Zeitreihendatenbank kdb+ (`.kx`) ein, falls du dafür eine Lizenz besitzt.
- **`benchmark-full`:** Nur für Windows/Linux (x86_64). Schließt zusätzlich ArcticDB ein, wofür es keine Version für Mac-Prozessoren gibt.

### `rapids` & `py312` (Spezial-Szenarien)

- **`rapids`:** Ein isolierter Container für Kapitel 12, der NVIDIA RAPIDS nutzt, um Gradient Boosting Modelle (wie XGBoost oder LightGBM) komplett auf der GPU zu trainieren.
- **`py312`:** Da manche im Buch genutzte Bibliotheken (wie gensim oder tfcausalimpact) noch nicht bereit für das brandneue Python 3.14 sind, friert dieser Container eine ältere **Python 3.12**-Umgebung ein, um die Kompatibilität für bestimmte Unterkapitel zu sichern.

## 3. Die Infrastruktur (Wissensgraph & Datenbanken)

Wenn du Benchmarks fährst oder mit fortgeschrittenen Datenstrukturen arbeitest, laufen im Hintergrund eigenständige Datenbank-Server als Container:

- **`neo4j`:** Eine Graphdatenbank für „Knowledge Graphs" (Wissensgraphen) – nützlich, um z.B. Lieferkettenbeziehungen oder Firmenverflechtungen zu analysieren.
- **Klassische & Zeitreihen-Datenbanken:** Für die Benchmarks zieht Docker vollautomatisch vorkonfigurierte Instanzen von **TimescaleDB** (auf PostgreSQL-Basis), ein nacktes **PostgreSQL**, **ClickHouse** (extrem schnell für Analysen), **QuestDB** und **InfluxDB** (beides spezialisierte Zeitreihendatenbanken für Tick- und Marktdaten) hoch. Alle sind mit Passwörtern wie `benchmark` direkt miteinander vernetzt.

## Zusammenfassung: Wie nutzt man das?

Durch die Definition von `profiles` (wie `gpu`, `benchmark`, `kg`, `databases`) verbraucht diese riesige Konfiguration nicht sofort deinen ganzen Arbeitsspeicher. Es startet immer nur das, was du explizit anforderst.

**Einfach starten (Hauptumgebung):**

```bash
docker compose up ml4t
```

**Mit Grafikkarte starten:**

```bash
docker compose --profile gpu up ml4t-gpu
```

**Die Datenbanken für die Benchmarks im Hintergrund starten:**

```bash
docker compose --profile databases up -d
```
