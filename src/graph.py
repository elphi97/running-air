"""Etap 2a: graf OSM i interpolacja IDW jakości powietrza na krawędziach.

Użycie:
    python -m src.pipeline prepare   # jednorazowo lokalnie: pobiera i zapisuje graf
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import osmnx as ox
import pandas as pd
from scipy.spatial import cKDTree

log = logging.getLogger("graph")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GRAPH_PATH = DATA / "krakow_graph.graphml"

# Obszar: północ i zachód Krakowa — punkt centralny + promień
AREA_LAT = 50.090   # ok. Krowodrza / Prądnik
AREA_LNG = 19.900
AREA_RADIUS_M = 7_000   # 7 km — obejmuje Błonia, Prądnik, Las Wolski

# Filtr typów dróg (bez autostrad i dróg szybkiego ruchu)
USEFUL_HIGHWAY = {
    "path", "footway", "pedestrian", "track", "cycleway",
    "living_street", "residential", "unclassified", "tertiary",
    "secondary",  # główne ulice tylko jako łączniki
}


def download_graph() -> object:
    """Pobiera graf z OSM i zapisuje lokalnie."""
    log.info("Pobieranie grafu OSM (może potrwać 2–3 min)…")
    cf = '["highway"~"' + "|".join(sorted(USEFUL_HIGHWAY)) + '"]'
    G = ox.graph_from_point(
        (AREA_LAT, AREA_LNG),
        dist=AREA_RADIUS_M,
        network_type="walk",
        custom_filter=cf,
        retain_all=False,
        simplify=True,
    )
    DATA.mkdir(exist_ok=True)
    ox.save_graphml(G, GRAPH_PATH)
    log.info("Graf zapisany: %s węzłów, %s krawędzi", len(G.nodes), len(G.edges))
    return G


def load_graph() -> object:
    """Wczytuje graf z pliku lub pobiera go, jeśli nie istnieje."""
    if GRAPH_PATH.exists():
        log.info("Wczytywanie grafu z %s", GRAPH_PATH.name)
        return ox.load_graphml(GRAPH_PATH)
    return download_graph()


# --------------------------------------------------------------------------- #
# Interpolacja IDW (Inverse Distance Weighting)
# --------------------------------------------------------------------------- #

def _edge_midpoints(G) -> tuple[np.ndarray, list]:
    """Zwraca macierz [N×2] środków krawędzi (lat, lng) i listę kluczy krawędzi."""
    mids, keys = [], []
    for u, v, k, data in G.edges(keys=True, data=True):
        geom = data.get("geometry")
        if geom is not None:
            c = geom.centroid
            lat, lng = c.y, c.x
        else:
            lat = (G.nodes[u]["y"] + G.nodes[v]["y"]) / 2
            lng = (G.nodes[u]["x"] + G.nodes[v]["x"]) / 2
        mids.append([lat, lng])
        keys.append((u, v, k))
    return np.array(mids), keys


def _idw(query_xy: np.ndarray, sensor_xy: np.ndarray,
         values: np.ndarray, k: int = 5, power: float = 2.0) -> np.ndarray:
    """IDW: dla każdego punktu w query_xy liczy ważoną średnią z k sąsiadów."""
    tree = cKDTree(sensor_xy)
    dists, idx = tree.query(query_xy, k=min(k, len(sensor_xy)))
    dists = np.where(dists == 0, 1e-9, dists)   # unikamy dzielenia przez 0
    weights = 1.0 / dists ** power
    vals = values[idx]
    weighted = (weights * vals).sum(axis=1) / weights.sum(axis=1)
    return weighted


def annotate_edges(G, measurements_path: Path) -> object:
    """Dodaje atrybut `pm25` (IDW) do każdej krawędzi grafu."""
    # Wczytaj pomiary — bierz ostatni dostępny dzień
    csv_files = sorted((measurements_path).glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"Brak plików CSV w {measurements_path}")
    df = pd.read_csv(csv_files[-1])
    df = df.dropna(subset=["pm25"])
    if df.empty:
        raise ValueError("Brak danych PM2.5 w ostatnim pliku CSV")

    # Współrzędne czujników (dołącz z selected.json)
    import json
    selected = json.loads((DATA / "selected.json").read_text())
    sensor_map = {s["id"]: (s["lat"], s["lng"]) for s in selected}

    # Uśrednij PM2.5 na czujnik (wszystkie godziny dnia)
    avg = df.groupby("installation_id")["pm25"].mean()
    sensor_ids = [sid for sid in avg.index if sid in sensor_map]
    if len(sensor_ids) < 3:
        raise ValueError("Za mało czujników z danymi PM2.5 do interpolacji")

    sensor_xy = np.array([sensor_map[sid] for sid in sensor_ids])
    pm25_vals = avg[sensor_ids].values

    log.info("Interpolacja IDW z %d czujników…", len(sensor_ids))
    mids, keys = _edge_midpoints(G)

    # Przelicz współrzędne na km (płaska aproksymacja)
    lat0 = np.radians(AREA_LAT)
    to_km = lambda ll: np.column_stack([
        ll[:, 1] * 111.32 * np.cos(lat0),
        ll[:, 0] * 110.57,
    ])
    pm25_interp = _idw(to_km(mids), to_km(sensor_xy), pm25_vals)

    for (u, v, k_), pm25 in zip(keys, pm25_interp):
        G[u][v][k_]["pm25"] = float(pm25)

    log.info("Krawędzie zanotowane (min=%.1f, max=%.1f µg/m³)",
             pm25_interp.min(), pm25_interp.max())
    return G
