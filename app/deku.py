"""DekuDeals (0.10.14): Spielinfos für PC-Spiele (Steam) und Konsolen der Sammlung, ohne Netz.

DekuDeals führt je Spiel eine Seite über alle Plattformen (Switch, PlayStation, Xbox, Steam) mit dem Kasten
„Details“: Genre, Spielerzahl, Entwickler, Verlag, Erscheinen, Metacritic mit Nutzerwertung, OpenCritic,
Spielzeit laut HowLongToBeat, Altersfreigabe (USK, PEGI, ESRB), Sprachen und Plattformen. Gelesen wird der sichtbare
Text, jede Angabe reicht bis zur nächsten bekannten Bezeichnung (wie im eShopKompass ab 1.6.0).

Zweite Quelle neben Steam und IGDB (Entscheidung 02.11.2026: zusätzlich alles abholen, ergänzen und bestätigen).
Ein Treffer zählt nur mit gleichem Namen und der richtigen Plattform (am PC „Steam“)."""
import html
import re
import urllib.parse

from . import titles

BASE = "https://www.dekudeals.com"
V = 1
# Plattform laut Kasten „Platforms“ je System der Sammlung
PLATFORM = {"PC": "Steam", "PS4": "PlayStation 4", "PS5": "PlayStation 5", "Xbox One": "Xbox One",
            "Xbox Series": "Xbox Series", "Switch": "Switch", "Switch 2": "Switch"}

_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_INFO_LABELS = ("MSRP", "Release date", "Genres?", "Number of players", "Developers?", "Publishers?",
                "Download size", "Metacritic", "OpenCritic", "How Long To Beat", "ESRB Rating", "PEGI Rating",
                "USK Rating", "Play modes", "Languages", "Platforms?", "Supported play modes")
_INFO_LABEL_RE = re.compile(r"(?<![\w-])(" + "|".join(_INFO_LABELS) + r")\s*:")
_INFO_OTHER_RE = re.compile(r"\s[A-Z][A-Za-z+ ]{0,24}:\s")
_MONTHS = {m: n for n, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                         "september", "october", "november", "december"), 1)}
_HLTB_KEYS = {"solo": "solo", "co-op": "coop", "coop": "coop", "main story": "main", "main": "main",
              "main + extras": "extra", "main + sides": "extra", "completionist": "complete", "vs.": "vs",
              "vs": "vs", "all styles": "all"}
_ITEM_RE = re.compile(r"""(?:href=["']|dekudeals\.com)(?:https://www\.dekudeals\.com)?/items/([A-Za-z0-9][\w-]*)(?=["'?#\s>])""")


def search_url(name):
    return f"{BASE}/search?" + urllib.parse.urlencode({"q": plain(name)})


def item_url(slug):
    return f"{BASE}/items/{urllib.parse.quote(slug)}"


def plain(n):
    """Name für Suche und Vergleich: ohne Klammern und Marken, „Legend of Pixels, The“ wie „The Legend of Pixels“."""
    n = re.sub(r"\(.*?\)|\[.*?\]|[™®©]", "", n or "").strip()
    m = re.match(r"(.+), (The|A|An|Der|Die|Das|Le|La|Les)$", n)
    return f"{m.group(2)} {m.group(1)}" if m else n


def search_slug(text, name):
    """Der passendste Treffer der Suche: gleicher Name zuerst, sonst die meisten gemeinsamen Wörter."""
    slugs = list(dict.fromkeys(_ITEM_RE.findall(text or "")))
    if not slugs:
        return ""
    want = set(re.sub(r"[^a-z0-9]+", " ", titles.norm(plain(name))).split())

    def rank(i_slug):
        i, sl = i_slug
        have = set(sl.lower().split("-"))
        return (-(have == want), -len(want & have), len(have - want), i)
    return min(enumerate(slugs), key=rank)[1]


def _hours(v):
    v = v.replace("½", ".5").replace("¼", ".25").replace("¾", ".75")
    try:
        return round(float(v), 2)
    except ValueError:
        return None


def parse(page):
    """Name und Spielinfos einer Artikelseite; {} ohne Kasten „Details“."""
    page = (page or "").replace("\\/", "/")
    m = _TITLE_RE.search(page)
    name = re.sub(r"\s*\|\s*Deku Deals\s*$", "", html.unescape(m.group(1)).strip()) if m else ""
    text = re.sub(r"(?i)<(?:/?(?:li|ul|ol|dd|dt|dl|p|div|tr|td|th|h[1-6]|section)\b[^>]*|br\s*/?)>", "\n",
                  re.sub(r"\s+", " ", _SCRIPT_RE.sub(" ", page)))
    text = html.unescape(_TAG_RE.sub(" ", text))
    text = re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\s*\n\s*", "\n", text))
    marks = list(_INFO_LABEL_RE.finditer(text))
    if not marks:
        return {}
    first = marks[0].start()
    marks = [m for m in marks if m.start() - first < 3000]
    vals = {}
    for n, m in enumerate(marks):
        key = m.group(1).lower()
        key = {"genres": "genre", "developers": "developer", "publishers": "publisher", "platforms": "platform"}.get(key, key)
        end = marks[n + 1].start() if n + 1 < len(marks) else min(len(text), m.end() + 300)
        if key not in vals:
            vals[key] = text[m.end():end].strip(" ·|\n")

    def simple(key, n=80):
        v = (vals.get(key) or "").split("\n")[0]
        o = _INFO_OTHER_RE.search(" " + v)
        return (v[:o.start()] if o else v).strip(" ·|,")[:n]
    out = {"name": name[:200]}
    genre = simple("genre", 200)
    if genre:
        out["genre"] = [g.strip() for g in re.split(r"\s*[,/]\s*", genre) if g.strip()][:6]
    pl, players = vals.get("number of players") or "", {}
    for lab, a, b in re.findall(r"(?i)(offline|local wireless|local|online)\s*:\s*(\d+)(?:\s*[-–]\s*(\d+))?", pl):
        k = {"offline": "offline", "online": "online"}.get(lab.lower(), "local")
        players.setdefault(k, [int(a), int(b or a)])
    if not players:
        m = re.match(r"\s*(\d+)(?:\s*[-–]\s*(\d+))?", pl)
        if m:
            players["offline"] = [int(m.group(1)), int(m.group(2) or m.group(1))]
    if players:
        out["players"] = players
    m = re.match(r"\s*(\d{1,3})(?:\s+(\d{1,2}(?:\.\d)?))?", vals.get("metacritic") or "")
    if m and int(m.group(1)) <= 100:
        out["mc"] = int(m.group(1))
        if m.group(2) and float(m.group(2)) <= 10:
            out["mcu"] = float(m.group(2))
    m = re.match(r"\s*(\d{1,3})\b", vals.get("opencritic") or "")
    if m and int(m.group(1)) <= 100:
        out["oc"] = int(m.group(1))
    hltb = {}
    for lab, v in re.findall(r"([A-Za-z][A-Za-z +.\-]{0,20}?)\s*:\s*([\d½¼¾.]+)\s*(?:hours?|hrs?|h)\b", vals.get("how long to beat") or ""):
        k, h = _HLTB_KEYS.get(lab.strip().lower()), _hours(v)
        if k and h is not None:
            hltb.setdefault(k, h)
    if hltb:
        out["hltb"] = hltb
    rd = simple("release date", 120)
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", rd)
    if m and m.group(1).lower() in _MONTHS:
        out["released"] = f"{m.group(3)}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    elif re.search(r"\b(19|20)\d\d\b", rd):
        out["released"] = re.search(r"\b(19|20)\d\d\b", rd).group(0)
    for key in ("developer", "publisher"):
        if simple(key):
            out[key[:3]] = simple(key)
    plat = simple("platform", 300)
    if plat:
        out["platforms"] = [p.strip() for p in plat.split(",") if p.strip()][:12]
    for org in ("usk", "pegi", "esrb"):
        v = simple(org + " rating", 20)
        if v:
            out["age"] = [org.upper(), v.split()[0][:6]]
            break
    langs = simple("languages", 400)
    if langs:
        out["langs"] = [x.strip() for x in re.split(r"\s*,\s*", langs) if x.strip() and len(x.strip()) < 30][:40]
    return out


def fits(info, g):
    """Gehört die Seite zum Spiel? Gleicher Name (ohne Zusätze) und, wo DekuDeals Plattformen nennt, die des Systems."""
    if not info or not info.get("name"):
        return False
    same = titles.base_norm(plain(info["name"])) in {titles.base_norm(plain(n)) for n in _names(g)}
    want = PLATFORM.get(g.get("system") or "PC", "")
    plats = info.get("platforms")
    return same and (not plats or not want or any(want.lower() in p.lower() for p in plats))


def _names(g):
    return [n for n in (g.get("name"), (g.get("igdb") or {}).get("name"), (g.get("steam") or {}).get("name")) if n]


def wanted(g):
    """Spiele, für die DekuDeals in Frage kommt: PC (dort nur, was es bei Steam gibt), PlayStation 4 und 5, Xbox, Switch,
    aus Playnite oder dem ROM-Ordner (PS4 und PS5 kommen seit 0.10.11 nur von dort); nicht die Switch-Spiele aus dem
    eShopKompass (die bringen ihre Angaben selbst mit), nicht die älteren Systeme (GameTDB, libretro)."""
    return (g.get("system") or "PC") in PLATFORM and g.get("src") != "eshop"
