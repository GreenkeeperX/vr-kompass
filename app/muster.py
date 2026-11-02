"""Preismuster aus dem eigenen Verlauf (0.10.0), ohne Netz und ohne feste Zahlen im Code: Alle Angebote bei Steam
(Verlauf der VR-Titel in history.json, Läden der PC-Wünsche von IsThereAnyDeal in pcwish.json) ergeben

- je Alter des Spiels (Monate seit Erscheinen bei Steam) den üblichen Rabatt (Median der Angebote),
- die Monate, in denen sich Angebote häufen (große Sales),
- die übliche Dauer eines Angebots.

Daraus die Marke „üblich −x %“: Liegt ein laufendes Angebot bei Steam deutlich unter dem, was für das Alter des Spiels
üblich war, zeigt sie die Zahl, auf der das beruht (sonst steht der übliche Rabatt nur in den Einzelheiten). Eine Prognose ist das nicht; der Tooltip sagt, woher die Zahl kommt.
"""
import re
import statistics
from datetime import date

from . import verlauf

# Altersstufen in Monaten seit Erscheinen [von, bis)
BANDS = [(0, 6), (6, 12), (12, 18), (18, 30), (30, 48), (48, None)]
MIN_N = 6            # so viele Angebote braucht eine Stufe, sonst keine Aussage
GAP = 10             # Prozentpunkte unter dem Üblichen, ab denen die Marke erscheint
MIN_USUAL = 15       # unter diesem üblichen Rabatt keine Marke
MONTH_NAMES = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
               "November", "Dezember"]

_DE_MON = {"jan": 1, "feb": 2, "mär": 3, "mar": 3, "mrz": 3, "apr": 4, "mai": 5, "may": 5, "jun": 6, "jul": 7, "aug": 8,
           "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12}


def steam_date(s):
    """Erscheinungstag aus den Steam-Details: „30. Apr. 2018“, „3. März 2021“, „Apr 30, 2018“ oder ISO. Sonst ""."""
    s = str(s or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.match(r"(\d{1,2})\.?\s+([A-Za-zäÄ]{3})[a-zä]*\.?,?\s+(\d{4})", s) or None
    if m:
        d, mon, y = int(m.group(1)), _DE_MON.get(m.group(2).casefold()), int(m.group(3))
    else:
        m = re.match(r"([A-Za-zäÄ]{3})[a-zä]*\.?\s+(\d{1,2}),?\s+(\d{4})", s)
        if not m:
            return ""
        mon, d, y = _DE_MON.get(m.group(1).casefold()), int(m.group(2)), int(m.group(3))
    if not mon:
        return ""
    try:
        return date(y, mon, d).isoformat()
    except ValueError:
        return ""


def months_between(a, b):
    """Ganze Monate von Tag a bis Tag b (ISO)."""
    da, db = date.fromisoformat(a), date.fromisoformat(b)
    return (db.year - da.year) * 12 + db.month - da.month - (db.day < da.day)


def band_of(age):
    for i, (lo, hi) in enumerate(BANDS):
        if age >= lo and (hi is None or age < hi):
            return i
    return None


def band_label(i):
    lo, hi = BANDS[i]
    return f"ab {lo} Monaten" if hi is None else f"{lo}–{hi - 1} Monate"


def _steam_series(data, pw_items, hist):
    """(App-ID, Erscheinungstag, Punkte, Normalpreis) je Spiel mit Steam-Verlauf, jede App-ID einmal."""
    seen = set()
    for t in (data.get("titles") or {}).values():
        app = str(t.get("steam_appid") or "")
        pts = ((hist or {}).get("steam") or {}).get(app)
        if not app or not pts or app in seen:
            continue
        seen.add(app)
        yield app, steam_date((t.get("sdet") or {}).get("date")), pts, ((t.get("live") or {}).get("steam") or {}).get("base")
    for e in (pw_items or {}).values():
        app = str(e.get("appid") or "")
        pts = (e.get("sh") or {}).get("Steam")
        if not pts or (app and app in seen):
            continue
        seen.add(app)
        reg = next((s.get("r") for s in (e.get("itad") or {}).get("shops") or [] if s.get("s") == "Steam"), None)
        yield app, steam_date((e.get("steam") or {}).get("date")), pts, reg


def stats(data, pw_items, hist, today=None):
    """Kennzahlen über alle Steam-Angebote im eigenen Verlauf."""
    today = today or date.today().isoformat()
    by_band = [[] for _ in BANDS]
    months = [0] * 12
    days, games, n = [], 0, 0
    for _app, rel, pts, reg in _steam_series(data, pw_items, hist):
        s = verlauf.series("Steam", pts, today, reg, "steam")
        if not s or not s["sales"]:
            continue
        games += 1
        for sale in s["sales"]:
            n += 1
            months[int(sale["start"][5:7]) - 1] += 1
            if sale["end"]:
                days.append(sale["days"])
            if rel and rel <= sale["start"]:
                b = band_of(months_between(rel, sale["start"]))
                if b is not None:
                    by_band[b].append(sale["pct"])
    avg = sum(months) / 12 if n else 0
    peak = [i + 1 for i, c in enumerate(months) if c >= 5 and c >= 1.2 * avg]
    return {"games": games, "sales": n, "today": today,
            "bands": [{"label": band_label(i), "n": len(v), "pct": round(statistics.median(v)) if len(v) >= MIN_N else None}
                      for i, v in enumerate(by_band)],
            "months": months, "peak": peak, "days": round(statistics.median(days)) if days else None}


def next_peak(st, today=None):
    """Der nächste Monat, in dem sich Angebote bisher häuften (ab dem laufenden), oder None."""
    if not st.get("peak"):
        return None
    m = date.fromisoformat(today or st.get("today") or date.today().isoformat()).month
    return min(st["peak"], key=lambda p: (p - m) % 12)


def usual(st, rel, now_pct, today=None):
    """Üblicher Steam-Rabatt für einen Wunsch: Erscheinungstag rel (ISO), Rabatt bei Steam gerade now_pct (0 ohne
    Angebot). None, wenn die Stufe zu wenige Angebote hat. mark: ein laufendes Angebot liegt mindestens GAP Punkte
    darunter (dann die Marke „üblich −x %“ neben dem Namen)."""
    today = today or st.get("today") or date.today().isoformat()
    if not rel or rel > today:
        return None
    b = band_of(months_between(rel, today))
    band = st["bands"][b] if b is not None else None
    if not band or band["pct"] is None or band["pct"] < MIN_USUAL:
        return None
    out = {"pct": band["pct"], "now": now_pct or 0, "band": band["label"], "n": band["n"]}
    # Marke nur bei einem laufenden Angebot, das deutlich unter dem Üblichen liegt; sonst steht es nur in den Einzelheiten
    out["mark"] = bool(now_pct) and band["pct"] - now_pct >= GAP
    nx = next_peak(st, today)
    if nx:
        out["peak"] = MONTH_NAMES[nx - 1]
    return out


def rhythm(pts, today, regular=None):
    """Steam-Angebote eines Spiels aus dem eigenen Verlauf (0.10.2): {"n", "last" (Beginn des letzten), "on" (läuft noch),
    "gap" (übliche Tage zwischen zwei Angeboten, ab drei Angeboten)} oder None ohne Angebot. Keine Vorhersage."""
    s = verlauf.series("Steam", pts, today, regular, "steam") if pts else None
    if not s or not s["sales"]:
        return None
    last = s["sales"][-1]
    return {"n": len(s["sales"]), "last": last["start"], "on": not last["end"], "gap": s["gap"]}


PC_NEAR = 0.05       # „Tief-Nähe“ am PC: so viel über dem Tief aus Händlern und Keyshops


def worth_pc(u, regular, r):
    """Für einen PC-Wunsch: Ein Steam-Angebot in der üblichen Höhe läge unter dem günstigsten Preis jetzt und höchstens
    PC_NEAR über dem Tief (Händler und Keyshops). Trägt den Preis dann als u["price"] ein."""
    if not regular:
        return False
    price = round(regular * (1 - u["pct"] / 100), 2)
    now = min((x for x in (r.get("retail"), r.get("keyshops")) if x is not None), default=None)
    low = r.get("low")
    if (now is not None and price >= now) or (low is not None and price > low * (1 + PC_NEAR) + 0.005):
        return False
    u["price"] = price
    return True


def annotate(view, pcview, data, pw_items, st, hist=None):
    """Hängt „usual“ an VR-Wünsche (view["wishlist"]) und PC-Wünsche (pcview["rows"]), die einen Steam-Preis haben, ab
    0.10.2 dazu „rhythm“ (Steam-Angebote des Spiels selbst)."""
    today = st.get("today") or date.today().isoformat()
    for r in view.get("wishlist") or []:
        if r.get("where"):
            continue
        t = data["titles"].get(r["key"]) or {}
        live = (t.get("live") or {}).get("steam") or {}
        rh = rhythm(((hist or {}).get("steam") or {}).get(str(t.get("steam_appid") or "")), today, live.get("base"))
        if rh:
            r["rhythm"] = rh
        if live.get("price") is None:
            continue
        u = usual(st, steam_date((t.get("sdet") or {}).get("date")), live.get("discount") or 0)
        if u:
            r["usual"] = u
    for r in (pcview or {}).get("rows") or []:
        if r.get("owned"):
            continue
        e = pw_items.get(r["key"]) or {}
        top = next((s for s in (e.get("itad") or {}).get("shops") or [] if s.get("s") == "Steam"), None)
        if not top or top.get("p") is None:
            continue
        u = usual(st, steam_date((e.get("steam") or {}).get("date")), top.get("c") or 0)
        # 0.10.3 (Entscheidung 02.11.2026): am PC zählt ein Steam-Angebot nur, wenn es den günstigsten Preis jetzt
        # (meist ein Keyshop) unterbietet und ans Tief heranreicht; sonst kauft man ohnehin anderswo
        if u and worth_pc(u, top.get("r"), r):
            r["usual"] = u
            rh = rhythm((e.get("sh") or {}).get("Steam"), today, top.get("r"))
            if rh:
                r["rhythm"] = rh
