"""Etap 2c: mapa Folium i eksport GPX."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import folium
import numpy as np
import pandas as pd

from src.routes import Route

log = logging.getLogger("visualize")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Kolory jakości powietrza (CAQI/PM2.5 µg/m³)


def _pm25_color(pm25: float) -> str:
    if pm25 < 10:
        return "#00b050"   # zielony
    if pm25 < 20:
        return "#92d050"   # jasna zieleń
    if pm25 < 25:
        return "#ffff00"   # żółty (WHO limit)
    if pm25 < 50:
        return "#ff9900"   # pomarańczowy
    return "#ff0000"                    # czerwony


def build_map(G, routes: list[Route],
              sensors: list[dict],
              origin: tuple[float, float],
              date: str) -> folium.Map:
    """
    Buduje mapę Folium:
      - czujniki (kółka kolorowane wg PM2.5)
      - wszystkie trasy (szare)
      - najlepsza trasa (gruba, niebieska)
    """
    m = folium.Map(location=list(origin), zoom_start=13,
                   tiles="OpenStreetMap")

    # --- Czujniki ---
    for s in sensors:
        pm25 = s.get("pm25")
        if pm25 is None:
            continue
        color = _pm25_color(pm25)
        folium.CircleMarker(
            location=[s["lat"], s["lng"]],
            radius=8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=folium.Popup(
                f"<b>ID {s['id']}</b><br>PM2.5: {pm25:.1f} µg/m³",
                max_width=200,
            ),
        ).add_to(m)

    # Legenda PM2.5
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:10px;border-radius:6px;
                box-shadow:2px 2px 6px rgba(0,0,0,.3);font-size:13px">
    <b>PM2.5 [µg/m³]</b><br>
    <span style="color:#00b050">●</span> &lt;10 (bardzo dobry)<br>
    <span style="color:#92d050">●</span> 10–20 (dobry)<br>
    <span style="color:#ffff00;-webkit-text-stroke:1px #aaa">●</span> 20–25 (WHO limit)<br>
    <span style="color:#ff9900">●</span> 25–50 (zły)<br>
    <span style="color:#ff0000">●</span> &gt;50 (bardzo zły)
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))

    # --- Trasy ---
    for i, route in enumerate(routes):
        coords = [[G.nodes[n]["y"], G.nodes[n]["x"]] for n in route.nodes]
        is_best = i == 0
        label = (f"🏆 Trasa #{i+1} (najlepsza)<br>"
                 if is_best else f"Trasa #{i+1}<br>")
        label += (f"Długość: {route.length_m/1000:.2f} km<br>"
                  f"Śr. PM2.5: {route.avg_pm25:.1f} µg/m³<br>"
                  f"Zieleń: {route.green_ratio*100:.0f}%<br>"
                  f"Wynik: {route.score:.3f}")
        folium.PolyLine(
            coords,
            color="#1565c0" if is_best else "#888888",
            weight=5 if is_best else 2.5,
            opacity=0.9 if is_best else 0.5,
            tooltip=label,
        ).add_to(m)

    # Punkt startowy
    folium.Marker(
        location=list(origin),
        tooltip="Start / Meta",
        icon=folium.Icon(color="blue", icon="flag"),
    ).add_to(m)

    # Tytuł
    title_html = f"""
    <div style="position:fixed;top:10px;left:50%;transform:translateX(-50%);
                z-index:1000;background:white;padding:8px 16px;
                border-radius:6px;box-shadow:2px 2px 6px rgba(0,0,0,.3);
                font-size:15px;font-weight:bold">
    Najlepsza trasa do biegania · Kraków · {date}
    </div>"""
    m.get_root().html.add_child(folium.Element(title_html))

    return m


def export_gpx(route: Route, G, output_path: Path) -> None:
    """Eksportuje najlepszą trasę do pliku GPX."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    trkpts = "\n".join(
        f'    <trkpt lat="{G.nodes[n]["y"]}" lon="{G.nodes[n]["x"]}"></trkpt>'
        for n in route.nodes
    )
    gpx = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="running-air"
     xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><time>{now}</time></metadata>
  <trk>
    <name>Najlepsza trasa biegowa Kraków</name>
    <trkseg>
{trkpts}
    </trkseg>
  </trk>
</gpx>"""
    output_path.write_text(gpx, encoding="utf-8")
    log.info("GPX zapisany: %s", output_path.name)
