"""Besitz mit zweiter Quelle (0.10.2), ohne Netz: Was eine Quelle als gekauft meldet, bestätigt eine zweite oder
widerspricht ihr. Widersprüche stehen in „Zu erledigen“ als Meldung, ohne Frage; der Besitz bleibt, wie er ist.

- Steam: das Steam-Konto (data["steam_play"], alle Spiele des Kontos) gegen Sharenite (Laden „Steam“) und die
  gg.deals-Sammlung (Launcher „Steam“). Das Konto gilt; listet eine andere Quelle das Spiel aus Steam, das Konto aber
  nicht, ist das ein Widerspruch (Familienbibliothek, anderes Konto, erstattet oder eine falsche Steam-ID).
- Meta: die eingelesenen Meta-Käufe gegen Sharenite (Laden Oculus oder Meta) und die gg.deals-Sammlung (Launcher
  „Meta“). Nennt eine zweite Quelle das Spiel bei Meta, die Meta-Käufe aber nicht, ist das ein Widerspruch.

Sharenite und die gg.deals-Sammlung führen nicht jedes Spiel (Sharenite nur mit VR-Schlagwort), deshalb ist ihr
Fehlen kein Widerspruch, nur „eine Quelle“. VRDB und QuestStoreDB kennen keinen Besitz.
"""
import re

from . import titles

META_SRC = re.compile(r"\b(?:oculus|meta)\b", re.I)


def _sn(data):
    """Sharenite zuletzt gelesen: {Grundform des Namens: Laden} oder None."""
    s = data.get("sharenite_seen")
    return (s.get("names") or {}) if isinstance(s, dict) else None


def _gg(data):
    """gg.deals-Sammlung zuletzt gelesen: {Grundform: [Launcher]} oder None."""
    g = data.get("gg_coll")
    if not isinstance(g, dict):
        return None
    out = {}
    for it in g.get("items") or []:
        out.setdefault(titles.norm(it.get("name") or ""), []).extend(it.get("stores") or [])
    return out


def check(data):
    """Je VR-Titel, was die Quellen zum Besitz sagen. Liefert {"steam": {"both", "one"}, "meta": {...},
    "doubt": [{key, name, kind, why}]}."""
    sp = data.get("steam_play") or {}
    sn, gg = _sn(data), _gg(data)
    meta_read = bool((data.get("imports") or {}).get("meta"))
    out = {"steam": {"both": 0, "one": 0}, "meta": {"both": 0, "one": 0}, "doubt": [],
           "read": {"steam": bool(sp), "sharenite": sn is not None, "gg": gg is not None, "meta": meta_read}}
    for k, t in data["titles"].items():
        n = titles.norm(t["name"])
        s_src = (sn or {}).get(n)
        g_src = (gg or {}).get(n) or []
        app = str(t.get("steam_appid") or "")
        # Steam
        others = [x for x, ok in (("Sharenite", s_src == "Steam"), ("gg.deals-Sammlung", "Steam" in g_src)) if ok]
        acct = bool(sp) and app in sp
        if acct:
            out["steam"]["both" if others else "one"] += 1
        elif others and sp and app and t.get("steam_sure"):
            out["doubt"].append({"key": k, "name": t["name"], "kind": "steam",
                                 "why": f"laut {' und '.join(others)} aus Steam, im Steam-Konto nicht "
                                        "(Familienbibliothek, anderes Konto, erstattet oder falsche Steam-ID?)"})
        # Meta
        others = [x for x, ok in (("Sharenite", bool(s_src and META_SRC.search(s_src))), ("gg.deals-Sammlung", "Meta" in g_src)) if ok]
        bought = bool((t.get("owned") or {}).get("meta"))
        if bought:
            out["meta"]["both" if others else "one"] += 1
        elif others and meta_read:
            out["doubt"].append({"key": k, "name": t["name"], "kind": "meta",
                                 "why": f"laut {' und '.join(others)} bei Meta, in den Meta-Käufen nicht "
                                        "(Meta-Käufe neu lesen, Geschenk oder anderes Konto?)"})
    out["doubt"].sort(key=lambda x: (x["kind"], titles.norm(x["name"])))
    return out
