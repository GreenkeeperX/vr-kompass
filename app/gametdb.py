"""GameTDB (0.10.13): Spielinfos für GameCube, Wii, DS, 3DS und PS3, ohne Netz.

GameTDB führt jedes Spiel unter seiner Spiel-ID („RMCP01“ bei Wii und GameCube, „AMKP“ bei DS und 3DS; der vierte
Buchstabe ist die Region; ab 0.10.13 auch PS3 mit der Seriennummer „BLES01017“) mit Titel und Beschreibung je Sprache, Genre, Spielerzahl, Altersfreigabe, Sprachen,
Entwickler, Verlag und Erscheinen. Die Datenbank liegt je Familie als gepackte XML-Datei vor
(`https://www.gametdb.com/wiitdb.zip?LANG=DE`, dazu `dstdb` und `3dstdb`); der Abgleich holt sie höchstens alle
DAYS Tage und behält je Spiel der Sammlung nur, was zu ihm passt („tdb“ am Spiel).

Rangfolge in der Sammlung (collection.merge_tdb): die deutsche Beschreibung vor IGDB und libretro (beide englisch),
Spielerzahl, Genre, Erscheinen, Entwickler und Verlag wie libretro (bestätigt, was zwei Quellen sagen, sonst Ersatz),
USK oder PEGI neu."""
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from . import titles

BASE = "https://www.gametdb.com/"
DBS = {"GameCube": "wiitdb", "Wii": "wiitdb", "DS": "dstdb", "3DS": "3dstdb", "PS3": "ps3tdb"}
NAMES = {"wiitdb": "Wii und GameCube", "dstdb": "DS", "3dstdb": "3DS", "ps3tdb": "PS3"}
DAYS = 30            # höchstens so oft je Datenbank
FILE = "gametdb.json"   # Stand je Datenbank: {wiitdb: {at, v, n}}
V = 1                # Stand der knappen Fassung am Spiel; ändert er sich, ordnet der Abgleich neu zu
MAX_XML = 400 << 20  # größte entpackte Datei
# Region im vierten Buchstaben der ID: deutsche Fassung zuerst, dann Europa, dann der Rest
_REGION_RANK = {"D": 0, "P": 1, "F": 2, "X": 2, "Y": 2, "Z": 2, "U": 3, "E": 4, "J": 6}
_SKIP = re.compile(r"(?i)\b(demo|kiosk|trial|preview|beta|prototype)\b")
_ARTICLE = re.compile(r"^(.+), (The|A|An|Der|Die|Das|Le|La|Les|Il|El)(\s+-\s+.*)?$")


def url(system):
    db = DBS.get(system)
    return f"{BASE}{db}.zip?LANG=DE" if db else ""


def _int(v):
    try:
        return max(0, int(str(v or "").strip()))
    except ValueError:
        return 0


def _system_ok(system, typ):
    """Gehört der Eintrag zum System? wiitdb führt Wii und GameCube zusammen (type „GameCube“), dazu WiiWare,
    Virtual Console und Kanäle, die hier nicht gemeint sind."""
    typ = (typ or "").strip()
    if system == "GameCube":
        return typ == "GameCube"
    if system == "Wii":
        return typ in ("", "Wii")
    return True


def parse(blob, system):
    """Einträge der gepackten Datenbank für ein System: [Eintrag]. Liest die XML-Datei schrittweise."""
    out = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        xmls = [i for i in z.infolist() if i.filename.lower().endswith(".xml")]
        if not xmls:
            raise ValueError("keine XML-Datei im Archiv")
        if xmls[0].file_size > MAX_XML:
            raise ValueError("XML-Datei zu groß")
        with z.open(xmls[0]) as f:
            for _, el in ET.iterparse(f, events=("end",)):
                if el.tag != "game":
                    continue
                e = _entry(el)
                el.clear()
                if e and _system_ok(system, e.pop("type")):
                    out.append(e)
    return out


def _entry(el):
    gid = (el.findtext("id") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{4,6}|[A-Z]{4}\d{5}", gid):
        return None
    loc = {}
    for lo in el.findall("locale"):
        lang = (lo.get("lang") or "").upper()
        loc[lang] = {"t": " ".join((lo.findtext("title") or "").split())[:200],
                     "s": " ".join((lo.findtext("synopsis") or "").split())[:1200]}
    en = (loc.get("EN") or {}).get("t") or (el.get("name") or "").strip()
    if not en or _SKIP.search(en):
        return None
    d = el.find("date")
    date = ""
    if d is not None and _int(d.get("year")) > 1970:
        y, m, dd = _int(d.get("year")), _int(d.get("month")), _int(d.get("day"))
        date = f"{y}" + (f"-{m:02d}" if 1 <= m <= 12 else "") + (f"-{dd:02d}" if 1 <= m <= 12 and 1 <= dd <= 31 else "")
    rating = el.find("rating")
    inp, wifi = el.find("input"), el.find("wi-fi")
    de, en_l = loc.get("DE") or {}, loc.get("EN") or {}
    e = {"id": gid, "type": (el.findtext("type") or "").strip(), "en": en[:200],
         "de_t": de.get("t") or "", "desc": de.get("s") or en_l.get("s") or "",
         "desc_lang": "de" if de.get("s") else "en",
         "genre": [x.strip() for x in (el.findtext("genre") or "").split(",") if x.strip()][:8],
         "dev": " ".join((el.findtext("developer") or "").split())[:120],
         "pub": " ".join((el.findtext("publisher") or "").split())[:120], "date": date,
         "langs": [x.strip().upper() for x in (el.findtext("languages") or "").split(",") if x.strip()][:20],
         "players": _int(inp.get("players")) if inp is not None else 0,
         "online": _int(wifi.get("players")) if wifi is not None else 0}
    if rating is not None and (rating.get("type") or "").upper() in ("USK", "PEGI") and (rating.get("value") or "").strip():
        e["rating"] = [(rating.get("type") or "").upper(), rating.get("value").strip()[:6]]
    return e


def _rank(e):
    gid = e["id"]
    if len(gid) == 9:           # PS3 „BLES01017“: der dritte Buchstabe ist die Region (E Europa, U Amerika)
        return ({"E": 1, "U": 4}.get(gid[2], 6), "DE" not in e["langs"], gid)
    return (_REGION_RANK.get(gid[3], 5) if len(gid) > 3 else 5, "DE" not in e["langs"], gid)


def index(entries):
    """{"id": {ID: Eintrag}, "name": {Titel: [Einträge, beste Region zuerst]}}; Titel englisch und deutsch, ohne
    Leerzeichen gleich."""
    by_id, by_name = {}, {}
    for e in entries:
        by_id[e["id"]] = e
        for t in {e["en"], e["de_t"]} - {""}:
            for k in {titles.norm(t), titles.norm(t).replace(" ", "")}:
                by_name.setdefault(k, []).append(e)
    for v in by_name.values():
        v.sort(key=_rank)
    return {"id": by_id, "name": by_name}


def _code(g):
    """Spiel-ID aus dem Dateinamen: „ID-RMCP“ (Wii, GameCube) oder der Produktcode „CTR-P-AMKP“ (3DS),
    „NTR-AMKP“ (DS); nur die ersten vier Zeichen."""
    s = str(g.get("serial") or "").strip().upper()
    if s.startswith("ID-"):
        return s[3:7]
    m = re.fullmatch(r"([A-Z]{4})-?(\d{5})", s)
    if m:
        return m.group(1) + m.group(2)       # PS3 (0.10.13): GameTDB schreibt „BLES01017“
    m = re.search(r"(?:CTR|KTR|NTR|TWL)-(?:[A-Z]-)?([A-Z0-9]{4})", s)
    return m.group(1) if m else ""


def _names(g):
    """Namen, unter denen das Spiel gesucht wird: deiner aus der Ordner-Liste, der Name, IGDB und libretro."""
    out = []
    for n in [(g.get("own") or {}).get("title"), g.get("name"), (g.get("igdb") or {}).get("name"), (g.get("lr") or {}).get("n")]:
        n = re.sub(r"\s*\([^)]*\)", "", str(n or "")).strip()
        if not n:
            continue
        m = _ARTICLE.match(n)
        for x in ([f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"] if m else []) + [n, n.replace(" - ", ": ")]:
            k = titles.norm(x)
            if k and k not in out:
                out.append(k)
    return out


def find(g, idx):
    """Der passende Eintrag: über die Spiel-ID aus dem Dateinamen (dieselbe Region zuerst), sonst über den Namen."""
    code = _code(g)
    if len(code) > 6 and code in idx["id"]:
        return idx["id"][code], "id"
    if len(code) == 4:
        hits = sorted((e for k, e in idx["id"].items() if k[:4] == code), key=_rank)
        if hits:
            return hits[0], "id"
    for k in _names(g):
        hits = idx["name"].get(k) or idx["name"].get(k.replace(" ", ""))
        if hits:
            return hits[0], "name"
    return None, ""


def compact(e, via):
    """Was am Spiel gespeichert wird."""
    out = {k: e[k] for k in ("id", "en", "de_t", "desc", "desc_lang", "genre", "dev", "pub", "date", "langs", "players", "online", "rating")
           if e.get(k)}
    out["via"] = via
    return out


def mark(col, system, idx, stamp):
    """Alle Spiele eines Systems neu zuordnen. Gibt (gefunden, gesamt) zurück."""
    got = n = 0
    for g in (col.get("games") or {}).values():
        if g.get("system") != system:
            continue
        e, via = find(g, idx)
        g["tdb"] = dict(compact(e, via), at=stamp, v=V) if e else {"none": True, "at": stamp, "v": V}
        n += 1
        got += bool(e)
    return got, n


def due(col, system, last, old):
    """Datenbank neu holen? Wenn sie älter als DAYS ist oder ein Spiel des Systems noch nicht zugeordnet ist."""
    games = [g for g in (col.get("games") or {}).values() if g.get("system") == system]
    if not games:
        return False
    if not last or (last.get("at") or "") < old or last.get("v") != V:
        return True
    return any((g.get("tdb") or {}).get("v") != V for g in games)
