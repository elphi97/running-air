"""Etap 2b: generowanie i scoring pętli biegowych.

Dla zadanego punktu startowego i docelowej długości:
  1. Losuje punkty „zwrotne" w odpowiedniej odległości.
  2. Buduje pętlę: start → punkt zwrotny → start (najkrótsza ścieżka z kosztem pm25).
  3. Filtruje trasy o złej długości lub słabe geometrycznie.
  4. Rankinguje według jakości powietrza i zieleni.
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import numpy as np
import osmnx as ox

log = logging.getLogger("routes")

# Wagi scoringu (suma = 1.0)
W_PM25 = 0.60     # im niższe PM2.5, tym lepiej
W_GREEN = 0.25    # udział krawędzi przez tereny zielone
W_LENGTH = 0.15   # kara za odchylenie od docelowej długości


@dataclass
class Route:
    nodes: list[int]
    length_m: float
    avg_pm25: float
    green_ratio: float
    score: float = 0.0
    edges_data: list[dict] = field(default_factory=list)


def _edge_cost(data: dict, pm25_weight: float = 1.5) -> float:
    """Koszt krawędzi: długość × (1 + k × znorm_pm25)."""
    length = data.get("length", 1.0)
    pm25 = data.get("pm25", 20.0)   # fallback: typowa wartość miejska
    norm = min(pm25 / 100.0, 1.0)   # normalizacja do [0,1], WHO limit 25 µg/m³
    return length * (1.0 + pm25_weight * norm)


def _build_cost_graph(G) -> nx.MultiDiGraph:
    """Klonuje graf z kosztem jako wagą krawędzi."""
    H = G.copy()
    for u, v, k, data in H.edges(keys=True, data=True):
        H[u][v][k]["cost"] = _edge_cost(data)
    return H


def _green_ratio(nodes: list[int], G) -> float:
    """Szacuje udział 'zielonych' krawędzi (ścieżki, parki, lasy)."""
    GREEN_TYPES = {"path", "footway", "track", "cycleway", "pedestrian"}
    total, green = 0.0, 0.0
    for u, v in zip(nodes[:-1], nodes[1:]):
        data = min(G[u][v].values(), key=lambda d: d.get("length", 9999))
        length = data.get("length", 1.0)
        hw = data.get("highway", "")
        if isinstance(hw, list):
            hw = hw[0]
        total += length
        if hw in GREEN_TYPES:
            green += length
    return green / total if total > 0 else 0.0


def _sample_waypoints(G, origin_node: int, target_dist_m: float,
                      n_candidates: int = 20, seed: int = 42) -> list[int]:
    """Losuje węzły w odległości ~target_dist_m/2 od punktu startowego."""
    rng = random.Random(seed)
    origin_lat = G.nodes[origin_node]["y"]
    origin_lng = G.nodes[origin_node]["x"]
    lat0 = math.radians(origin_lat)

    half = target_dist_m / 2.0   # chcemy pętlę, więc punkt w połowie dystansu
    tol = 0.35                    # ±35%

    candidates = []
    for node, data in G.nodes(data=True):
        if node == origin_node:
            continue
        dlat = (data["y"] - origin_lat) * 110570
        dlng = (data["x"] - origin_lng) * 111320 * math.cos(lat0)
        dist = math.hypot(dlat, dlng)
        if half * (1 - tol) <= dist <= half * (1 + tol):
            candidates.append(node)

    if len(candidates) < 5:
        log.warning("Mało kandydatów na punkt zwrotny (%d), rozszerzam tolerancję", len(candidates))
        candidates = [
            n for n, d in G.nodes(data=True)
            if n != origin_node and
            half * 0.2 <= math.hypot(
                (d["y"] - origin_lat) * 110570,
                (d["x"] - origin_lng) * 111320 * math.cos(lat0)
            ) <= half * 1.8
        ]

    return rng.sample(candidates, min(n_candidates, len(candidates)))


def generate_routes(G, origin: tuple[float, float],
                    target_km: float,
                    n_routes: int = 5,
                    n_waypoints: int = 25) -> list[Route]:
    """
    Generuje i rankinguje n_routes pętli biegowych.

    Args:
        G: graf OSM z atrybutem pm25 na krawędziach
        origin: (lat, lng) punktu startowego
        target_km: docelowa długość trasy w km
        n_routes: ile tras zwrócić (najlepsze)
        n_waypoints: ile punktów zwrotnych sprawdzić
    """
    target_m = target_km * 1000
    H = _build_cost_graph(G)

    origin_node = ox.nearest_nodes(G, X=origin[1], Y=origin[0])
    log.info("Punkt startowy: węzeł %d", origin_node)

    waypoints = _sample_waypoints(G, origin_node, target_m, n_waypoints)
    log.info("Sprawdzam %d punktów zwrotnych dla %.1f km…", len(waypoints), target_km)

    routes: list[Route] = []
    for wp in waypoints:
        try:
            path_out = nx.shortest_path(H, origin_node, wp, weight="cost")
            path_back = nx.shortest_path(H, wp, origin_node, weight="cost")
        except nx.NetworkXNoPath:
            continue

        nodes = path_out + path_back[1:]
        length = sum(
            min(G[u][v].values(), key=lambda d: d.get("length", 9999)).get("length", 0)
            for u, v in zip(nodes[:-1], nodes[1:])
        )

        # Odrzuć trasy o złej długości (±25%)
        if not (target_m * 0.75 <= length <= target_m * 1.25):
            continue

        # PM2.5 ważone długością krawędzi
        pm25_vals, lengths = [], []
        for u, v in zip(nodes[:-1], nodes[1:]):
            data = min(G[u][v].values(), key=lambda d: d.get("length", 9999))
            pm25_vals.append(data.get("pm25", 20.0))
            lengths.append(data.get("length", 1.0))
        avg_pm25 = np.average(pm25_vals, weights=lengths)

        green = _green_ratio(nodes, G)
        routes.append(Route(nodes=nodes, length_m=length,
                            avg_pm25=avg_pm25, green_ratio=green))

    if not routes:
        log.warning("Brak tras dla %.1f km — spróbuj innej długości", target_km)
        return []

    # Normalizacja i scoring
    pm25_arr = np.array([r.avg_pm25 for r in routes])
    green_arr = np.array([r.green_ratio for r in routes])
    len_arr = np.array([r.length_m for r in routes])

    def norm01(x: np.ndarray) -> np.ndarray:
        rng = x.max() - x.min()
        return (x - x.min()) / rng if rng > 1e-9 else np.zeros_like(x)

    pm25_score = 1.0 - norm01(pm25_arr)   # niższe PM2.5 = lepszy wynik
    green_score = norm01(green_arr)
    len_penalty = 1.0 - norm01(np.abs(len_arr - target_m))

    for i, route in enumerate(routes):
        route.score = (W_PM25 * pm25_score[i]
                       + W_GREEN * green_score[i]
                       + W_LENGTH * len_penalty[i])

    routes.sort(key=lambda r: r.score, reverse=True)
    log.info("Wygenerowano %d tras, zwracam top %d", len(routes), n_routes)
    return routes[:n_routes]
