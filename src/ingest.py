"""Etap 1: pobieranie i archiwizacja pomiarów Airly dla Krakowa.

Użycie:
    python -m src.ingest discover   # lista instalacji + wybór podzbioru czujników
    python -m src.ingest collect    # pomiary (current + 24 h historii) -> data/measurements/
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BASE_URL = "https://airapi.airly.eu/v2"
LOCAL_TZ = "Europe/Warsaw"

log = logging.getLogger("airly")


class BudgetExceeded(Exception):
    """Wyczerpany dzienny limit requestów."""


class AirlyClient:
    """Cienki klient API z lokalnym licznikiem requestów (limit dobowy)."""

    def __init__(self, api_key: str, daily_budget: int):
        self.session = requests.Session()
        self.session.headers.update({"apikey": api_key, "Accept": "application/json"})
        self.budget = daily_budget
        self.usage_path = DATA / "api_usage.json"
        self.usage: dict[str, int] = (
            json.loads(self.usage_path.read_text()) if self.usage_path.exists() else {}
        )

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def used_today(self) -> int:
        return self.usage.get(self._today(), 0)

    def _bump(self) -> None:
        self.usage[self._today()] = self.used_today() + 1
        recent = dict(sorted(self.usage.items())[-30:])  # trzymamy ostatnie 30 dni
        self.usage_path.write_text(json.dumps(recent, indent=2))

    def get(self, path: str, **params):
        if self.used_today() >= self.budget:
            raise BudgetExceeded(f"Budżet {self.budget} requestów/dobę wyczerpany")
        resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        self._bump()
        remaining = resp.headers.get("X-RateLimit-Remaining-day")
        if remaining is not None:
            log.info("Airly: pozostało dziś %s requestów", remaining)
        if resp.status_code == 429:
            raise BudgetExceeded("Airly zwróciło 429 (limit)")
        resp.raise_for_status()
        return resp.json()


# --------------------------------------------------------------------------- #
# Discover: lista instalacji i wybór równomiernie rozłożonego podzbioru
# --------------------------------------------------------------------------- #
def farthest_point_sample(xy: np.ndarray, k: int, start: int) -> list[int]:
    """Greedy k-center: kolejne punkty maksymalnie oddalone od już wybranych."""
    k = min(k, len(xy))
    chosen = [start]
    dist = np.linalg.norm(xy - xy[start], axis=1)
    while len(chosen) < k:
        nxt = int(dist.argmax())
        chosen.append(nxt)
        dist = np.minimum(dist, np.linalg.norm(xy - xy[nxt], axis=1))
    return chosen


def discover(client: AirlyClient, cfg: dict) -> list[dict]:
    c = cfg["area"]
    items = client.get(
        "/installations/nearest",
        lat=c["center_lat"],
        lng=c["center_lng"],
        maxDistanceKM=c["radius_km"],
        maxResults=-1,
    )
    installations = [
        {
            "id": i["id"],
            "lat": i["location"]["latitude"],
            "lng": i["location"]["longitude"],
            "elevation": i.get("elevation"),
            "airly": i.get("airly"),
        }
        for i in items
    ]
    log.info("Znaleziono %d instalacji w promieniu %s km", len(installations), c["radius_km"])
    (DATA / "installations.json").write_text(json.dumps(installations, indent=2))

    # rzut na płaszczyznę w km (wystarczająco dokładny dla skali miasta)
    lat0 = np.radians(c["center_lat"])
    xy = np.array(
        [[i["lng"] * 111.32 * np.cos(lat0), i["lat"] * 110.57] for i in installations]
    )
    center = np.array([c["center_lng"] * 111.32 * np.cos(lat0), c["center_lat"] * 110.57])
    start = int(np.linalg.norm(xy - center, axis=1).argmin())
    idx = farthest_point_sample(xy, cfg["limits"]["n_sensors"], start)
    selected = [installations[i] for i in idx]
    (DATA / "selected.json").write_text(json.dumps(selected, indent=2))
    log.info("Wybrano %d czujników", len(selected))
    return selected


# --------------------------------------------------------------------------- #
# Collect: pomiary current + history (24 h) dla wybranych czujników
# --------------------------------------------------------------------------- #
def parse_measurements(installation_id: int, payload: dict) -> list[dict]:
    rows = []
    blocks = [payload.get("current")] + list(payload.get("history") or [])
    for block in blocks:
        if not block or not block.get("values"):
            continue
        vals = {v["name"]: v["value"] for v in block["values"]}
        caqi = next(
            (i.get("value") for i in block.get("indexes", []) if i.get("name") == "AIRLY_CAQI"),
            None,
        )
        rows.append(
            {
                "installation_id": installation_id,
                "from_dt": block["fromDateTime"],
                "till_dt": block["tillDateTime"],
                "pm1": vals.get("PM1"),
                "pm25": vals.get("PM25"),
                "pm10": vals.get("PM10"),
                "temperature": vals.get("TEMPERATURE"),
                "humidity": vals.get("HUMIDITY"),
                "pressure": vals.get("PRESSURE"),
                "caqi": caqi,
            }
        )
    return rows


def save_measurements(df: pd.DataFrame) -> None:
    """Zapis do plików dziennych (data lokalna), z deduplikacją."""
    out_dir = DATA / "measurements"
    out_dir.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["from_dt"] = pd.to_datetime(df["from_dt"], utc=True)
    df["till_dt"] = pd.to_datetime(df["till_dt"], utc=True)
    df["date"] = df["from_dt"].dt.tz_convert(LOCAL_TZ).dt.strftime("%Y-%m-%d")

    for date, part in df.groupby("date"):
        part = part.drop(columns="date")
        path = out_dir / f"{date}.csv"
        if path.exists():
            old = pd.read_csv(path)
            old["from_dt"] = pd.to_datetime(old["from_dt"], utc=True)
            old["till_dt"] = pd.to_datetime(old["till_dt"], utc=True)
            part = pd.concat([old, part], ignore_index=True)
        part = (
            part.drop_duplicates(["installation_id", "from_dt"], keep="last")
            .sort_values(["from_dt", "installation_id"])
        )
        part.to_csv(path, index=False)
        log.info("Zapisano %s (%d wierszy)", path.name, len(part))


def collect(client: AirlyClient, cfg: dict) -> None:
    selected_path = DATA / "selected.json"
    if not selected_path.exists():
        discover(client, cfg)
    selected = json.loads(selected_path.read_text())

    rows: list[dict] = []
    for inst in selected:
        try:
            payload = client.get("/measurements/installation", installationId=inst["id"])
        except BudgetExceeded as exc:
            log.warning("%s - przerywam, zapisuję to, co mam", exc)
            break
        except requests.HTTPError as exc:
            log.warning("Instalacja %s: %s", inst["id"], exc)
            continue
        rows.extend(parse_measurements(inst["id"], payload))

    if not rows:
        log.error("Brak danych do zapisania")
        sys.exit(1)
    save_measurements(pd.DataFrame(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["discover", "collect"])
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = yaml.safe_load(Path(args.config).read_text())
    api_key = os.environ.get("AIRLY_API_KEY")
    if not api_key:
        sys.exit("Ustaw zmienną środowiskową AIRLY_API_KEY")

    DATA.mkdir(exist_ok=True)
    client = AirlyClient(api_key, cfg["limits"]["daily_request_budget"])
    {"discover": discover, "collect": collect}[args.command](client, cfg)


if __name__ == "__main__":
    main()
