"""Etap 2: główny punkt wejścia — przygotowanie grafu i generowanie tras.

Użycie:
    python -m src.pipeline prepare          # jednorazowo: pobierz i zapisz graf OSM
    python -m src.pipeline run              # generuj mapy dla wszystkich długości
    python -m src.pipeline run --km 5 10   # tylko 5 km i 10 km
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "output"

log = logging.getLogger("pipeline")

# Dostępne długości tras w km
DEFAULT_DISTANCES = [3, 5, 8, 10]

# Punkt startowy: północ/zachód Krakowa (Krowodrza, okolice Błoni)
ORIGIN = (50.0650, 19.9100)


def cmd_prepare(args) -> None:
    """Pobiera graf OSM i zapisuje do data/krakow_graph.graphml."""
    from src.graph import download_graph
    download_graph()
    log.info("Graf gotowy. Wrzuć plik data/krakow_graph.graphml do repo (git add data/krakow_graph.graphml).")


def cmd_run(args) -> None:
    from src.graph import load_graph, annotate_edges
    from src.routes import generate_routes
    from src.visualize import build_map, export_gpx

    distances = args.km if args.km else DEFAULT_DISTANCES
    OUT.mkdir(exist_ok=True)

    # Wczytaj graf i dodaj PM2.5 z ostatniego CSV
    G = load_graph()
    G = annotate_edges(G, DATA / "measurements")

    # Przygotuj dane czujników do mapy
    selected = json.loads((DATA / "selected.json").read_text())
    sensor_map = {s["id"]: s for s in selected}
    csv_files = sorted((DATA / "measurements").glob("*.csv"))
    df = pd.read_csv(csv_files[-1])
    avg_pm25 = df.groupby("installation_id")["pm25"].mean()
    sensors_for_map = []
    for sid, pm25 in avg_pm25.items():
        if sid in sensor_map and not pd.isna(pm25):
            s = dict(sensor_map[sid])
            s["pm25"] = float(pm25)
            sensors_for_map.append(s)

    date = datetime.now().strftime("%Y-%m-%d")
    results_summary = []

    for km in distances:
        log.info("═══ Generowanie tras: %.0f km ═══", km)
        routes = generate_routes(G, ORIGIN, target_km=km,
                                 n_routes=5, n_waypoints=30)
        if not routes:
            log.warning("Brak tras dla %.0f km — pomijam", km)
            continue

        best = routes[0]
        log.info("Najlepsza trasa %.0f km: PM2.5=%.1f µg/m³, zieleń=%.0f%%, wynik=%.3f",
                 km, best.avg_pm25, best.green_ratio * 100, best.score)

        # Mapa HTML
        m = build_map(G, routes, sensors_for_map, ORIGIN, date)
        map_path = OUT / f"map_{km}km_{date}.html"
        m.save(str(map_path))
        log.info("Mapa zapisana: %s", map_path.name)

        # GPX najlepszej trasy
        gpx_path = OUT / f"best_{km}km_{date}.gpx"
        export_gpx(best, G, gpx_path)

        results_summary.append({
            "km": km,
            "length_m": round(best.length_m),
            "avg_pm25": round(best.avg_pm25, 1),
            "green_pct": round(best.green_ratio * 100, 1),
            "score": round(best.score, 3),
            "map": map_path.name,
            "gpx": gpx_path.name,
        })

    # Podsumowanie JSON (przydatne do README / badge)
    summary_path = OUT / f"summary_{date}.json"
    summary_path.write_text(json.dumps(results_summary, indent=2, ensure_ascii=False))
    log.info("Podsumowanie: %s", summary_path.name)

    if results_summary:
        log.info("\n%-6s %-10s %-10s %-8s %-8s", "km", "długość", "PM2.5", "zieleń", "wynik")
        for r in results_summary:
            log.info("%-6.0f %-10s %-10s %-8s %-8s",
                     r["km"],
                     f"{r['length_m']}m",
                     f"{r['avg_pm25']} µg/m³",
                     f"{r['green_pct']}%",
                     r["score"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("prepare", help="Pobierz i zapisz graf OSM (jednorazowo)")

    p_run = sub.add_parser("run", help="Generuj mapy i GPX")
    p_run.add_argument("--km", type=float, nargs="+",
                       help="Długości tras w km (domyślnie: 3 5 8 10)")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    DATA.mkdir(exist_ok=True)
    {"prepare": cmd_prepare, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
