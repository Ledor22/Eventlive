#!/usr/bin/env python3
"""
Raccoglie eventi VERI in Sardegna e genera data/eventi.json, che l'app (index.html) legge all'apertura.

Fonti (configurabili in data/sources.json):
  - calendari iCal (.ics) pubblici di comuni, Pro Loco, musei, teatri...
  - Ticketmaster Discovery API (concerti, teatro, sport) se è impostata la chiave TICKETMASTER_KEY
  - data/eventi_manuali.json (opzionale): eventi inseriti a mano nello stesso formato

Solo libreria standard di Python.
Uso:  python3 scripts/build_eventi.py
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

TODAY = dt.date.today()
HORIZON = TODAY + dt.timedelta(days=120)   # eventi dei prossimi 4 mesi
MAX_SESSION_DAYS = 14                      # eventi lunghi (mostre): al massimo 14 giorni elencati
BBOX = (38.8, 41.4, 8.1, 9.9)              # lat min/max, lng min/max della Sardegna


def log(*a):
    print(*a, flush=True)


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()).strip()


def http_get(url, headers=None, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eventlive-eventi/1.0", **(headers or {})})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(str(last))


# ---------------------------------------------------------------- località
TOWNS = json.load(open(os.path.join(DATA, "towns.json"), encoding="utf-8"))
TOWN_BY_NAME = {norm(t["name"]): t for t in TOWNS}
TOWN_NAMES_LONGEST_FIRST = sorted(TOWN_BY_NAME, key=len, reverse=True)


def in_sardinia(lat, lng):
    return BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lng <= BBOX[3]


def town_from_text(text):
    """Cerca il nome di un comune dentro un testo (luogo/indirizzo): vince il nome più lungo."""
    n = " " + norm(text) + " "
    for name in TOWN_NAMES_LONGEST_FIRST:
        if len(name) >= 4 and f" {name} " in n:
            return TOWN_BY_NAME[name]
    return None


# ---------------------------------------------------------------- categorie
def category_from_text(text):
    n = norm(text)
    rules = [
        ("Sagre", ("sagra", "degustazion", "enogastron", "street food", "vino", "olio", "gusto", "cena")),
        ("Mostre", ("mostra", "esposizion", "museo", "galleria")),
        ("Cinema", ("cinema", "film", "proiezion", "cineforum")),
        ("Concerti", ("concerto", "live", "musica", "jazz", "rock", "band", "orchestra", "dj ", "tour")),
        ("Festival", ("festival", "festa", "carnevale", "fiera", "mercatino", "sfilata", "cavalcata")),
    ]
    for cat, words in rules:
        if any(w in n for w in words):
            return cat
    return "Cultura"


# ---------------------------------------------------------------- sessioni
def build_sessions(start, end):
    """start/end: datetime. Restituisce [{date,start,end}] (una per giorno), solo da oggi in poi."""
    out = []
    d0 = max(start.date(), TODAY)
    last = min(end.date() if end else start.date(), HORIZON)
    if end and end <= start:
        last = start.date()
    d = d0
    while d <= last and len(out) < MAX_SESSION_DAYS:
        if d == start.date():
            s = start.strftime("%H:%M")
            e = end.strftime("%H:%M") if end and end.date() == d else (start + dt.timedelta(hours=2)).strftime("%H:%M")
            if e <= s:
                e = "23:59"
        else:
            s, e = "10:00", "18:00"
        out.append({"date": d.isoformat(), "start": s, "end": e})
        d += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------- iCal
def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text)


def unescape(v):
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def parse_ics_dt(value, params):
    v = value.strip()
    try:
        if "VALUE=DATE" in params.upper() or re.fullmatch(r"\d{8}", v):
            d = dt.datetime.strptime(v[:8], "%Y%m%d")
            return d, True
        d = dt.datetime.strptime(v[:15], "%Y%m%dT%H%M%S")
        if v.endswith("Z"):   # UTC -> ora di Roma (approssimata: +1 inverno, +2 estate)
            offset = 2 if 4 <= d.month <= 10 else 1
            d += dt.timedelta(hours=offset)
        return d, False
    except Exception:  # noqa: BLE001
        return None, False


def parse_ics(text):
    text = unfold(text)
    events, cur = [], None
    for line in text.splitlines():
        if line.startswith("BEGIN:VEVENT"):
            cur = {}
        elif line.startswith("END:VEVENT"):
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, _, value = line.partition(":")
            name, _, params = key.partition(";")
            cur[name.upper()] = (value, params)
    return events


def from_ics(src):
    raw = http_get(src["url"]).decode("utf-8", "replace")
    default_town = TOWN_BY_NAME.get(norm(src.get("town", "")))
    out = []
    for ev in parse_ics(raw):
        if "SUMMARY" not in ev or "DTSTART" not in ev:
            continue
        start, allday = parse_ics_dt(*ev["DTSTART"])
        if not start:
            continue
        end = None
        if "DTEND" in ev:
            end, _ = parse_ics_dt(*ev["DTEND"])
            if end and allday:           # DTEND dei giorni interi è "esclusivo"
                end -= dt.timedelta(days=1)
                end = end.replace(hour=18)
        if allday:
            start = start.replace(hour=10)
        title = unescape(ev["SUMMARY"][0]).strip()
        desc = unescape(ev.get("DESCRIPTION", ("", ""))[0]).strip()
        loc = unescape(ev.get("LOCATION", ("", ""))[0]).strip()
        town = None
        if "GEO" in ev:
            try:
                la, ln = [float(x) for x in ev["GEO"][0].split(";")]
                town = nearest_town(la, ln)
            except Exception:  # noqa: BLE001
                town = None
        town = town or town_from_text(loc) or town_from_text(title) or default_town
        if not town:
            continue
        sessions = build_sessions(start, end)
        if not sessions:
            continue
        url = ev.get("URL", ("", ""))[0].strip() or src["url"]
        out.append({
            "title": title,
            "category": category_from_text(title + " " + desc),
            "town": town["id"],
            "venue": loc.split(",")[0][:80] or town["name"],
            "desc": re.sub(r"<[^>]+>", " ", desc)[:400].strip() or f"Evento a {town['name']}.",
            "sessions": sessions,
            "price": None,
            "url": url,
            "organizer": src.get("name", "Organizzatore locale"),
            "source": src.get("name", "iCal"),
        })
    return out


# ---------------------------------------------------------------- Ticketmaster
def haversine_km(lat1, lng1, lat2, lng2):
    import math
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def nearest_town(lat, lng, max_km=15):
    best, bd = None, 1e9
    for t in TOWNS:
        d = haversine_km(lat, lng, t["lat"], t["lng"])
        if d < bd:
            best, bd = t, d
    return best if bd <= max_km else None


TM_SEGMENT = {"Music": "Concerti", "Arts & Theatre": "Cultura", "Film": "Cinema", "Sports": "Festival"}


def from_ticketmaster(key):
    base = os.environ.get("TM_URL_TEMPLATE") or (
        "https://app.ticketmaster.com/discovery/v2/events.json?apikey={key}&countryCode=IT"
        "&latlong=40.1,9.0&radius=220&unit=km&size=200&sort=date,asc&page={page}"
        "&startDateTime={start}&endDateTime={end}&locale=*")
    out = []
    for page in range(0, 5):
        url = base.format(key=key, page=page,
                          start=TODAY.strftime("%Y-%m-%dT00:00:00Z"), end=HORIZON.strftime("%Y-%m-%dT23:59:59Z"))
        data = json.loads(http_get(url).decode("utf-8"))
        evs = (data.get("_embedded") or {}).get("events") or []
        for e in evs:
            try:
                venue = ((e.get("_embedded") or {}).get("venues") or [{}])[0]
                loc = venue.get("location") or {}
                lat, lng = float(loc["latitude"]), float(loc["longitude"])
                if not in_sardinia(lat, lng):
                    continue
                town = nearest_town(lat, lng)
                if not town:
                    continue
                st = e["dates"]["start"]
                if "localTime" in st:
                    start = dt.datetime.strptime(st["localDate"] + " " + st["localTime"][:5], "%Y-%m-%d %H:%M")
                else:
                    start = dt.datetime.strptime(st["localDate"], "%Y-%m-%d").replace(hour=21)
                sessions = build_sessions(start, None)
                if not sessions:
                    continue
                pr = (e.get("priceRanges") or [{}])[0]
                price = {"min": pr.get("min"), "max": pr.get("max")} if pr.get("min") is not None else None
                seg = ((e.get("classifications") or [{}])[0].get("segment") or {}).get("name", "")
                out.append({
                    "title": e["name"].strip(),
                    "category": TM_SEGMENT.get(seg) or category_from_text(e["name"]),
                    "town": town["id"],
                    "venue": venue.get("name", town["name"])[:80],
                    "desc": (e.get("info") or e.get("pleaseNote") or f"{e['name']} · {venue.get('name', town['name'])}")[:400],
                    "sessions": sessions,
                    "price": price,
                    "url": e.get("url", ""),
                    "organizer": "Ticketmaster",
                    "source": "Ticketmaster",
                })
            except Exception:  # noqa: BLE001
                continue
        if len(evs) < 200:
            break
    return out


# ---------------------------------------------------------------- unione
def main():
    sources = json.load(open(os.path.join(DATA, "sources.json"), encoding="utf-8"))
    collected, ok, errors = [], [], []

    for src in sources.get("ics", []):
        if not src.get("enabled", True) or not src.get("url") or "SITO-DEL-COMUNE" in src["url"]:
            continue
        try:
            items = from_ics(src)
            collected += items
            ok.append(f"{src.get('name', src['url'])}: {len(items)}")
            log(f"iCal {src.get('name')}: {len(items)} eventi")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{src.get('name', src['url'])}: {e}")
            log(f"!! iCal {src.get('name')} non leggibile: {e}")

    key = os.environ.get("TICKETMASTER_KEY", "").strip()
    if sources.get("ticketmaster") and key:
        try:
            items = from_ticketmaster(key)
            collected += items
            ok.append(f"Ticketmaster: {len(items)}")
            log(f"Ticketmaster: {len(items)} eventi")
        except Exception as e:  # noqa: BLE001
            errors.append(f"Ticketmaster: {e}")
            log(f"!! Ticketmaster non leggibile: {e}")
    elif sources.get("ticketmaster"):
        log("Ticketmaster saltato: manca il Secret TICKETMASTER_KEY")

    manual = os.path.join(DATA, "eventi_manuali.json")
    if os.path.exists(manual):
        try:
            items = json.load(open(manual, encoding="utf-8")).get("events", [])
            collected += items
            ok.append(f"Manuali: {len(items)}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"Manuali: {e}")

    if not ok:
        log("\nNessuna fonte ha restituito dati: lascio invariato data/eventi.json")
        sys.exit(0 if not errors else 1)

    # niente doppioni (stesso titolo, stesso comune, stessa prima data), eventi passati già esclusi
    seen, events = set(), []
    for e in sorted(collected, key=lambda x: x["sessions"][0]["date"]):
        k = (norm(e["title"]), e["town"], e["sessions"][0]["date"])
        if k in seen:
            continue
        seen.add(k)
        e["id"] = "r-" + hashlib.sha1("|".join(map(str, k)).encode()).hexdigest()[:10]
        events.append(e)

    result = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sources": ok,
        "errors": errors,
        "events": events,
    }
    with open(os.path.join(DATA, "eventi.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    log(f"\nOK: {len(events)} eventi veri salvati in data/eventi.json")


if __name__ == "__main__":
    main()
