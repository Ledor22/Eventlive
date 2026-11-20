#!/usr/bin/env python3
"""
Scarica gli orari ufficiali (GTFS open data) di ARST e Trenitalia Sardegna e genera data/orari.json,
che l'app (index.html) usa al posto degli orari simulati.

Solo libreria standard di Python (nessun pip install).

Uso:   python3 scripts/build_orari.py
Test:  FEEDS_JSON='[["TEST","file:///percorso/test.zip"]]' python3 scripts/build_orari.py
"""
import csv
import datetime as dt
import io
import json
import math
import os
import statistics
import sys
import tempfile
import time
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# Fonti ufficiali (open data). Si possono cambiare/aggiungere con la variabile FEEDS_JSON.
DEFAULT_FEEDS = [
    ["ARST", "https://www.arstspa.info/arst-cagliari-it.zip"],
    ["Trenitalia", "http://www.sardegnamobilita.it/opendata/dati_trenitalia.zip"],
]
FEEDS = json.loads(os.environ.get("FEEDS_JSON", "null")) or DEFAULT_FEEDS

DAYTYPES = ("wd", "sa", "su")  # feriale, sabato, festivo


def log(*a):
    print(*a, flush=True)


def norm(s):
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()


def haversine_km(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def download(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eventlive-orari/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    tmp.write(chunk)
                tmp.close()
                return tmp.name
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"download fallito: {last}")


def rows(zf, name):
    if name not in zf.namelist():
        return
    with zf.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))


def to_min(t):
    """'HH:MM:SS' -> minuti dalla mezzanotte (può superare 1440 oltre mezzanotte)."""
    try:
        h, m, _ = t.strip().split(":")
        return int(h) * 60 + int(m)
    except Exception:  # noqa: BLE001
        return None


def target_dates():
    """Prossimo martedì, sabato e domenica (da domani in poi)."""
    today = dt.date.today()
    want = {"wd": 1, "sa": 5, "su": 6}  # weekday(): lun=0 ... dom=6
    out = {}
    for k, wd in want.items():
        d = today + dt.timedelta(days=1)
        while d.weekday() != wd:
            d += dt.timedelta(days=1)
        out[k] = d
    return out


def active_services(zf, date):
    ymd = date.strftime("%Y%m%d")
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    active = set()
    for r in rows(zf, "calendar.txt"):
        if r["start_date"] <= ymd <= r["end_date"] and r.get(days[date.weekday()]) == "1":
            active.add(r["service_id"])
    for r in rows(zf, "calendar_dates.txt"):
        if r["date"] == ymd:
            if r["exception_type"] == "1":
                active.add(r["service_id"])
            elif r["exception_type"] == "2":
                active.discard(r["service_id"])
    return active


def mode_of(route_type):
    try:
        rt = int(route_type)
    except Exception:  # noqa: BLE001
        return "bus"
    return "train" if rt == 2 or 100 <= rt < 200 else "bus"


def main():
    towns = json.load(open(os.path.join(DATA, "towns.json"), encoding="utf-8"))
    links = json.load(open(os.path.join(DATA, "links.json"), encoding="utf-8"))
    link_by_pair = {}
    for l in links:
        link_by_pair[(l["a"], l["b"], l["mode"])] = (l["a"], l["b"], l["mode"], 1)   # a -> b
        link_by_pair[(l["b"], l["a"], l["mode"])] = (l["a"], l["b"], l["mode"], -1)  # b -> a

    dates = target_dates()
    log("Date di riferimento:", {k: v.isoformat() for k, v in dates.items()})

    # griglia delle località per l'assegnazione fermata -> località più vicina
    CELL = 0.05
    grid = defaultdict(list)
    for t in towns:
        grid[(round(t["lat"] / CELL), round(t["lng"] / CELL))].append(t)

    def town_for(lat, lng):
        best, bd = None, 1e9
        cx, cy = round(lat / CELL), round(lng / CELL)
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for t in grid.get((cx + dx, cy + dy), ()):
                    d = haversine_km(lat, lng, t["lat"], t["lng"])
                    if d <= t["r"] and d < bd:
                        best, bd = t["id"], d
        return best

    # dati per collegamento: key -> dir -> daytype -> set(minuti) ; durate
    deps = defaultdict(lambda: {"fwd": {d: set() for d in DAYTYPES}, "rev": {d: set() for d in DAYTYPES}})
    durs = defaultdict(list)
    used = []

    for name, url in FEEDS:
        log(f"\n== {name}: {url}")
        try:
            path = download(url)
            zf = zipfile.ZipFile(path)
        except Exception as e:  # noqa: BLE001
            log(f"!! {name} non scaricabile ({e}): lo salto")
            continue

        stop_town = {}
        for r in rows(zf, "stops.txt"):
            try:
                lat, lng = float(r["stop_lat"]), float(r["stop_lon"])
            except Exception:  # noqa: BLE001
                continue
            tid = town_for(lat, lng)
            if tid:
                stop_town[r["stop_id"]] = tid
        log(f"   fermate associate a una località: {len(stop_town)}")

        route_mode = {r["route_id"]: mode_of(r.get("route_type")) for r in rows(zf, "routes.txt")}

        services = {k: active_services(zf, d) for k, d in dates.items()}
        trip_info = {}  # trip_id -> (mode, set(daytypes))
        for r in rows(zf, "trips.txt"):
            dts = {k for k in DAYTYPES if r["service_id"] in services[k]}
            if dts:
                trip_info[r["trip_id"]] = (route_mode.get(r["route_id"], "bus"), dts)
        log(f"   corse attive nei giorni di riferimento: {len(trip_info)}")
        if not trip_info:
            log("   (nessuna corsa attiva: il feed potrebbe essere scaduto)")

        visits = defaultdict(list)  # trip_id -> [(seq, town, arr, dep)]
        for r in rows(zf, "stop_times.txt"):
            tid = r["trip_id"]
            if tid not in trip_info:
                continue
            town = stop_town.get(r["stop_id"])
            if not town:
                continue
            dep = to_min(r.get("departure_time") or r.get("arrival_time") or "")
            arr = to_min(r.get("arrival_time") or r.get("departure_time") or "")
            if dep is None or arr is None:
                continue
            try:
                seq = int(r["stop_sequence"])
            except Exception:  # noqa: BLE001
                continue
            visits[tid].append((seq, town, arr, dep))

        n_pairs = 0
        for tid, vs in visits.items():
            mode, dts = trip_info[tid]
            vs.sort()
            # prima visita di ogni località lungo la corsa
            first = []
            seen = set()
            for seq, town, arr, dep in vs:
                if town not in seen:
                    seen.add(town)
                    first.append((town, arr, dep))
            for i in range(len(first)):
                for j in range(i + 1, len(first)):
                    ta, _, dep_a = first[i]
                    tb, arr_b, _ = first[j]
                    hit = link_by_pair.get((ta, tb, mode))
                    if not hit:
                        continue
                    a, b, m, sign = hit
                    key = f"{a}|{b}|{m}"
                    d = "fwd" if sign == 1 else "rev"
                    if not (0 <= dep_a < 1440) or arr_b <= dep_a:
                        continue
                    for k in dts:
                        deps[key][d][k].add(dep_a)
                    durs[key].append(arr_b - dep_a)
                    n_pairs += 1
        log(f"   tratte (corsa x collegamento) trovate: {n_pairs}")
        used.append(name)
        zf.close()
        os.unlink(path)

    if not used:
        log("\nNessuna fonte scaricata: lascio invariato data/orari.json")
        sys.exit(1)

    out_links = {}
    for key, d in deps.items():
        if not durs[key]:
            continue
        out_links[key] = {
            "min": int(round(statistics.median(durs[key]))),
            "fwd": {k: sorted(v) for k, v in d["fwd"].items()},
            "rev": {k: sorted(v) for k, v in d["rev"].items()},
        }

    result = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "dates": {k: v.isoformat() for k, v in dates.items()},
        "sources": used,
        "stats": {"links_total": len(links), "links_with_real_data": len(out_links)},
        "links": out_links,
    }
    with open(os.path.join(DATA, "orari.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    log(f"\nOK: {len(out_links)} collegamenti su {len(links)} hanno orari ufficiali.")
    log("Gli altri restano con orari stimati nell'app.")


if __name__ == "__main__":
    main()
