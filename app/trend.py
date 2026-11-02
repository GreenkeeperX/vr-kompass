"""Trend und Pflege (0.8.18) ohne Netz: Steam-Rezensionen der letzten 30 Tage gegen alle, letztes Update.

Die letzten 30 Tage kommen aus dem Bewertungsdiagramm des Steam-Stores (appreviewhistogram, Feld „recent“,
Stimmen je Tag). Antwortet Steam dort nicht, rechnet der Trend mit den eigenen Messungen: Zahl und positive
Rezensionen bei jedem Abruf (hist), der Unterschied zwischen zwei Messungen sind die neuen Rezensionen."""
import json
from datetime import date

HIST_MAX = 8            # so viele Messungen je Spiel bleiben
MIN_RECENT = 10         # so viele Rezensionen braucht ein Zeitraum für einen Trend
MIN_ALL = 50            # Gesamtwertung erst ab so vielen Rezensionen (wie in Entdecken)
STEP = 8                # Punkte Abstand für steigend oder fallend
GAP_MIN, GAP_MAX = 20, 120   # Abstand zweier eigener Messungen in Tagen
FRESH_DAYS = 90         # Update jünger: gepflegt
MRH_MAX = 40            # Messungen der Zahl der Meta-Bewertungen je Quelle (0.10.1)
GROW_MIN_DAYS = 14      # so viele Tage muss der Vergleich mindestens umfassen
GROW_WINDOW = 90        # Vergleich mit der ältesten Messung höchstens so weit zurück
STALE_DAYS = 365        # Update älter: ruht


def histogram(text):
    """appreviewhistogram: Stimmen der letzten 30 Tage {"up", "down"}; None ohne gültige Antwort."""
    try:
        d = json.loads(text)
    except ValueError:
        return None
    res = d.get("results") if isinstance(d, dict) and d.get("success") == 1 else None
    if not isinstance(res, dict) or not isinstance(res.get("recent"), list):
        return None
    up = down = 0
    for x in res["recent"]:
        if isinstance(x, dict):
            up += int(x.get("recommendations_up") or 0)
            down += int(x.get("recommendations_down") or 0)
    return {"up": up, "down": down}


def keep(old, new):
    """Neue Rezensionszahl mit den bisherigen Messungen (hist: [[Tag, Zahl, positiv]]). Alte Einträge ohne
    hist laden wie bisher."""
    old, new = old or {}, dict(new)
    h = [x for x in (old.get("hist") or []) if isinstance(x, list) and len(x) == 3]
    # Nur mit genauer Zahl positiver Rezensionen; aus dem gerundeten Anteil wäre der Unterschied zweier
    # Messungen bei vielen Rezensionen bloßes Rauschen
    if isinstance(new.get("n"), int) and new["n"] > 0 and isinstance(new.get("pos"), int):
        day = str(new.get("at") or "")[:10]
        h = [x for x in h if x[0] != day] + [[day, new["n"], new["pos"]]]
    if h:
        new["hist"] = h[-HIST_MAX:]
    return new


def _days(a, b):
    try:
        return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days
    except (TypeError, ValueError):
        return None


def trend(rev):
    """{"dir": up, down oder flat, "recent": Anteil positiv, "n": Rezensionen im Zeitraum, "all": gesamt,
    "src": steam oder own, "since": Tag der älteren Messung}; None, wenn die Zahlen nicht reichen."""
    rev = rev or {}
    n, pct = rev.get("n"), rev.get("pct")
    if not isinstance(n, int) or n < MIN_ALL or pct is None:
        return None
    out = None
    r = rev.get("recent") or {}
    rn = int(r.get("up") or 0) + int(r.get("down") or 0)
    if rn >= MIN_RECENT:
        out = {"recent": round(100 * int(r.get("up") or 0) / rn), "n": rn, "src": "steam", "since": ""}
    else:
        h = rev.get("hist") or []
        if len(h) >= 2:
            last = h[-1]
            for x in reversed(h[:-1]):
                gap = _days(x[0], last[0])
                if gap is None or gap < GAP_MIN:
                    continue
                dn, dp = last[1] - x[1], last[2] - x[2]
                if gap <= GAP_MAX and dn >= MIN_RECENT and 0 <= dp <= dn:
                    out = {"recent": round(100 * dp / dn), "n": dn, "src": "own", "since": x[0]}
                break
    if not out:
        return None
    d = out["recent"] - pct
    out.update(all=pct, dir="up" if d >= STEP else "down" if d <= -STEP else "flat")
    return out


def care(day, today=None):
    """Pflege nach dem letzten Update laut Steam-Neuigkeiten: {"state": fresh, ok oder stale, "days", "date"};
    None ohne Datum."""
    if not day:
        return None
    d = _days(day, today or date.today().isoformat())
    if d is None:
        return None
    return {"state": "fresh" if d <= FRESH_DAYS else "stale" if d > STALE_DAYS else "ok", "days": max(0, d), "date": day[:10]}


def note_meta_n(t, src, n, day):
    """Zahl der Meta-Bewertungen je Quelle (vrdb, qsdb) mit Tag vermerken, nur bei Änderung (0.10.1). Meta nennt keine
    Spielerzahlen; wie schnell neue Bewertungen kommen, ist ein grober Hinweis, ob ein Spiel noch gekauft und gespielt
    wird. Die Quellen bleiben getrennt, weil sie verschieden zählen."""
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0 or not day:
        return
    mrh = t.setdefault("mrh", {})
    h = [x for x in (mrh.get(src) or []) if isinstance(x, list) and len(x) == 2]
    if h and h[-1][1] == n:
        return
    mrh[src] = ([x for x in h if x[0] != day] + [[day[:10], n]])[-MRH_MAX:]


def meta_growth(mrh, today=None):
    """Neue Meta-Bewertungen je 30 Tage aus der längsten Messreihe: {"per30", "days", "since", "src"} oder None,
    solange die Messungen weniger als GROW_MIN_DAYS umfassen."""
    today = (today or date.today().isoformat())[:10]
    best = None
    for src, h in (mrh or {}).items():
        h = [x for x in h or [] if isinstance(x, list) and len(x) == 2 and _days(x[0], today) is not None]
        if len(h) < 2:
            continue
        last = h[-1]
        base = next((x for x in h if _days(x[0], today) <= GROW_WINDOW), None)
        if base is None or base is last:
            base = h[-2]
        d = _days(base[0], last[0])
        if d is None or d < GROW_MIN_DAYS:
            continue
        if best is None or d > best["days"]:
            best = {"per30": max(0, round((last[1] - base[1]) * 30 / d)), "days": d, "since": base[0], "src": src}
    return best
