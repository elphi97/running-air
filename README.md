# 🏃 running-air — Kraków Running Route Optimizer

> Automatically selects the best running route in Kraków based on real-time air quality data from Airly sensors and the OpenStreetMap road network.

---

## 📌 What it does

Every day the pipeline:
1. **Fetches air quality measurements** (PM2.5, PM10, CAQI) from up to 80 Airly sensors across Kraków via the Airly API.
2. **Archives the data** to daily CSV files stored in the repository.
3. **Builds a walkable graph** of northern and western Kraków from OpenStreetMap using OSMnx.
4. **Interpolates PM2.5 values** onto every edge of the graph using Inverse Distance Weighting (IDW).
5. **Generates loop routes** of 3, 5, 8 and 10 km and scores them by air quality, green cover and closeness to the target distance.
6. **Outputs an interactive HTML map** and a GPX file for the best route of each distance.

The whole pipeline runs automatically on GitHub Actions once a day.

---

## 🗺️ Example output

| Distance | Length | Avg PM2.5 | Green cover | Score |
|----------|--------|-----------|-------------|-------|
| 5 km | 4 805 m | 13.6 µg/m³ | 92.8 % | 0.881 |

*Starting point: Krowodrza / Błonia area (north-west Kraków)*

---

## 🧠 Method

### Air quality interpolation (IDW)
Airly sensors are point measurements. To estimate air quality along any path, the pipeline uses **Inverse Distance Weighting**: for each edge midpoint in the graph, PM2.5 is estimated as a weighted average of the k nearest sensors, where weights are the inverse squared distances.

```
PM2.5(x) = Σ(wᵢ · PM2.5ᵢ) / Σwᵢ,   wᵢ = 1 / d(x, sensorᵢ)²
```

### Route scoring
Each candidate loop is scored as:

```
score = 0.60 × air_quality + 0.25 × green_cover + 0.15 × length_accuracy
```

where `air_quality` is normalised inversely to PM2.5 (lower = better).

### Limitations
- IDW is an approximation — actual pollution at street level may differ from sensor readings.
- Sensor density in Kraków is high (~100 sensors within city limits) but not uniform.
- The graph covers north-west Kraków only (7 km radius from Krowodrza).

---

## 🛠️ Tech stack

| Layer | Tools |
|---|---|
| Air quality data | [Airly API v2](https://developer.airly.org/) |
| Road network | [OSMnx](https://osmnx.readthedocs.io/) + OpenStreetMap |
| Spatial interpolation | SciPy (`cKDTree`), NumPy |
| Routing | NetworkX (shortest path with custom edge cost) |
| Visualisation | Folium (Leaflet.js) |
| Automation | GitHub Actions (cron, daily) |
| Data storage | CSV files (daily), GraphML |

---

## 📁 Project structure

```
running-air/
├── src/
│   ├── ingest.py       # Airly API client, data collection & archiving
│   ├── graph.py        # OSM graph download, IDW edge annotation
│   ├── routes.py       # Loop generation & scoring
│   ├── visualize.py    # Folium map + GPX export
│   └── pipeline.py     # CLI entry point
├── data/
│   ├── measurements/   # Daily CSV archives (YYYY-MM-DD.csv)
│   ├── selected.json   # Active sensor subset
│   └── krakow_graph.graphml
├── output/             # Generated maps and GPX files
├── config.yaml         # Area, sensor count, API budget
├── requirements.txt
└── .github/workflows/
    └── ingest.yml      # Daily automation
```

---

## 🚀 Running locally

### 1. Clone & install

```bash
git clone https://github.com/elphi97/running-air.git
cd running-air
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Set your Airly API key

```bash
export AIRLY_API_KEY="your_key_here"   # Windows: $env:AIRLY_API_KEY="your_key_here"
```

Get a free key at [developer.airly.org](https://developer.airly.org/).

### 3. Download the OSM graph (one-time)

```bash
python -m src.pipeline prepare
```

### 4. Collect sensor data

```bash
python -m src.ingest collect
```

### 5. Generate routes & maps

```bash
python -m src.pipeline run            # all distances: 3, 5, 8, 10 km
python -m src.pipeline run --km 5    # specific distance
```

Open `output/map_5.0km_YYYY-MM-DD.html` in a browser.

---

## ⚙️ GitHub Actions setup

1. Fork or clone this repo.
2. Add a repository secret: **Settings → Secrets → Actions → New repository secret**
   - Name: `AIRLY_API_KEY`
3. Enable write permissions: **Settings → Actions → General → Workflow permissions → Read and write**
4. The workflow runs automatically every day at 05:30 UTC.

---

## 📊 Data notes

- Free Airly plan: **100 requests / day**. The pipeline uses up to 81 (1 discovery + 80 sensors).
- Each daily run collects the **current reading + 24 h of hourly history** per sensor, so one run per day is sufficient.
- Data accumulates in `data/measurements/` — after a few weeks you can analyse any past day without additional API calls.

---

## 📄 License

MIT — free to use, modify and distribute.
