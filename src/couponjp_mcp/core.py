"""CouponJP lookup core: find stores in Japan where the free CouponJP tourist coupon works.

Standard library only, so it can be reused outside the MCP server (for example by a chat bot).
Data comes from the public files on https://couponjp.com/ (data.json, coupon-api.json, stations.json),
cached in memory for an hour. Set COUPONJP_DATA_DIR to read the same files from a local folder instead.
"""
from __future__ import annotations

import json
import math
import os
import re
import ssl
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

BASE = os.environ.get("COUPONJP_BASE", "https://couponjp.com").rstrip("/")
DATA_DIR = os.environ.get("COUPONJP_DATA_DIR")
TTL = int(os.environ.get("COUPONJP_TTL", "3600"))
UA = "couponjp-mcp/0.1 (+https://couponjp.com/)"
DEFAULT_UTM = os.environ.get("COUPONJP_UTM", "mcp")

try:                      # python.org builds on macOS ship without root certificates; certifi is a declared dependency
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL = ssl.create_default_context()

LANG_ALIASES = {"zh": "zh-CN", "zh-hans": "zh-CN", "zh-cn": "zh-CN", "zh-sg": "zh-CN", "zh-hant": "zh-TW", "zh-tw": "zh-TW",
                "zh-hk": "zh-TW", "zh-mo": "zh-TW", "tl": "fil", "jp": "ja", "kr": "ko", "in": "id"}
CATEGORY_NAMES = {"drug": "drugstore", "elec": "electronics store", "dept": "department store", "duty": "duty-free shop",
                  "disc": "discount store"}


class Store:
    """In-memory copy of the public data, refreshed after TTL seconds."""

    def __init__(self):
        self._lock = threading.Lock()
        self._at = 0.0
        self.api: dict = {}
        self.data: dict = {}
        self.stations: list = []

    def _load(self, name: str):
        if DATA_DIR:
            with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
                return json.load(f)
        req = urllib.request.Request(f"{BASE}/{name}", headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
            return json.loads(r.read().decode("utf-8"))

    def get(self) -> "Store":
        with self._lock:
            if time.time() - self._at < TTL and self.api:
                return self
            api, data = self._load("coupon-api.json"), self._load("data.json")
            try:
                stations = self._load("stations.json").get("stations") or []
            except Exception:          # stations are optional (place search by station name only)
                stations = self.stations
            self.api, self.data, self.stations, self._at = api, data, stations, time.time()
            self._index()
            return self

    def _index(self):
        self.langs = [x["code"] for x in self.api.get("langs") or []] or ["en"]
        self.brands = self.api["brands"]
        self.brand_by_key = {b["key"]: b for b in self.brands}
        self.store_rows = [s for s in self.data.get("stores") or [] if s[5] is not None and s[6] is not None]
        self.store_by_id = {s[0]: s for s in self.data.get("stores") or []}
        self.store_pages = self.api.get("store_pages") or {}
        names = {}
        for b in self.brands:
            for v in (b.get("name") or {}).values():
                names.setdefault(norm(v), b["key"])
            names.setdefault(norm(b["key"]), b["key"])
        for alias, key in (("donki", "donki"), ("donkihote", "donki"), ("ドンキ", "donki"), ("bic", "bic"), ("biccamera", "bic"),
                           ("sugi", "sugi"), ("tsuruha", "tsuruha"), ("cosmos", "cosmos"), ("kokumin", "kokumin"), ("sundrug", "sundrug")):
            if key in self.brand_by_key:
                names.setdefault(norm(alias), key)
        self.brand_names = names


DB = Store()


# ---------------------------------------------------------------- helpers
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"(train station|station|sta\.|駅|车站|車站|站|역)$", "", s.strip())
    return re.sub(r"[\s・·,.'\-–—_()（）/&]+", "", s)


def lang_of(lang: str | None) -> str:
    db = DB.get()
    if not lang:
        return "en"
    l = lang.strip()
    l = LANG_ALIASES.get(l.lower(), l)
    for code in db.langs:
        if code.lower() == l.lower():
            return code
    base = l.split("-")[0].lower()
    for code in db.langs:
        if code.lower() == base:
            return code
    return "en"


def km(a_lat, a_lng, b_lat, b_lng) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def with_utm(url: str, source: str | None = None) -> str:
    src = source or DEFAULT_UTM
    if not url or not src:
        return url
    return url + ("&" if "?" in url else "?") + "utm_source=" + urllib.parse.quote(src)


def pick(d: dict, lang: str, fallback: str = "en"):
    return (d or {}).get(lang) or (d or {}).get(fallback) or next(iter((d or {}).values()), None)


def brand_off_at(b: dict, amount_jpy: int) -> int | None:
    """Coupon discount (%) for a purchase of amount_jpy yen before tax; None while the coupon is being renewed."""
    if b.get("coupon_renewal"):
        return None
    tiers = b.get("tiers") or []
    if tiers:
        ok = [t["off_pct"] for t in tiers if t["min_jpy"] <= (amount_jpy * 1.1 if t["basis"] == "tax_included" else amount_jpy)]
        return max(ok) if ok else 0
    cats = b.get("category_offs") or []
    if cats:
        return max(c["off_pct"] for c in cats)
    return b.get("max_off_pct")


def fee_text(fee: dict) -> str:
    k = fee.get("kind")
    if k == "pct":
        return f"{fee['value_pct']:g}% of the price before tax"
    if k == "pctmax":
        return f"up to {fee['value_pct']:g}% of the price before tax"
    if k == "flat":
        return f"¥{fee['value_jpy']:,} per purchase"
    return {"none": "no refund fee", "full": "full tax amount refunded (per the store)", "ask": "not published by the store",
            "na": "no refund needed (sold without tax)"}.get(k, "unknown")


# ---------------------------------------------------------------- places
def resolve_place(query: str, limit: int = 5) -> list[dict]:
    """Shopping area, city or train station name (any language) → candidate centres."""
    db = DB.get()
    q = norm(query)
    if not q:
        return []
    out = []
    for a in db.api.get("areas") or []:
        names = [norm(v) for v in (a.get("name") or {}).values()] + [norm(a["key"])]
        parts = [norm(p) for v in (a.get("name") or {}).values() for p in re.split(r"[・·,&、]| and | & ", v)]
        if q in names or q in parts or any(q and q in n for n in names):
            out.append({"type": "area", "key": a["key"], "name": a.get("name"), "lat": a["lat"], "lng": a["lng"], "radius_km": a["radius_km"]})
    for c in db.api.get("cities") or []:
        names = [norm(v) for v in (c.get("name") or {}).values()] + [norm(c["key"])]
        if q in names and c.get("lat") is not None:
            out.append({"type": "city", "key": c["key"], "name": c.get("name"), "lat": c["lat"], "lng": c["lng"], "radius_km": 2.0})
    if len(out) < limit and db.stations:
        exact, prefix = [], []
        for row in db.stations:
            ns = [norm(x) for x in row[2:] if x]
            if q in ns:
                exact.append(row)
            elif len(q) >= 3 and any(n.startswith(q) for n in ns):
                prefix.append(row)
        seen = []
        for row in exact + prefix:
            if len(out) >= limit:
                break
            if any(row[2] == r[2] and km(row[0], row[1], r[0], r[1]) < 1.0 for r in seen):   # same station, other line
                continue
            seen.append(row)
            out.append({"type": "station", "name": {"ja": row[2], "en": row[3], "zh-CN": row[4], "zh-TW": row[5], "ko": row[6]},
                        "lat": row[0], "lng": row[1], "radius_km": 1.0})
    return out[:limit]


# ---------------------------------------------------------------- stores
def store_name(s, lang: str) -> str:
    n = s[8] if len(s) > 8 and isinstance(s[8], dict) else {}
    if lang == "ja":
        return n.get("ja") or s[3]
    if lang == "zh-TW":
        return n.get("tw") or s[3]
    if lang == "zh-CN":
        return s[3]
    return n.get("en") or n.get("ja") or s[3]


def store_addr(s, lang: str) -> str:
    n = s[8] if len(s) > 8 and isinstance(s[8], dict) else {}
    if lang == "ja":
        return n.get("addr_ja") or s[4]
    if lang == "zh-CN":
        return n.get("addr_zh") or s[4]
    if lang == "zh-TW":
        return n.get("addr_tw") or n.get("addr_zh") or s[4]
    return n.get("addr_en") or n.get("addr_ja") or s[4]


def maps_url(s, b) -> str:
    n = s[8] if len(s) > 8 and isinstance(s[8], dict) else {}
    q = f"{pick(b['name'], 'ja')} {n.get('ja') or s[3] or ''} {n.get('addr_q') or n.get('addr_ja') or s[4] or ''}".strip()
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(q)


def store_out(s, d_km: float | None, lang: str, utm: str | None) -> dict:
    db = DB.get()
    b = db.brands[s[1]]
    page = (db.store_pages.get(str(s[0])) or {}).get(lang)
    off = None if b.get("coupon_renewal") else b.get("max_off_pct")
    return {
        "brand": pick(b["name"], lang), "brand_key": b["key"], "category": CATEGORY_NAMES.get(b["category"], b["category"]),
        "store": store_name(s, lang), "address": store_addr(s, lang),
        "distance_m": None if d_km is None else int(round(d_km * 1000, -1)),
        "max_discount_pct": off,
        "coupon_note": "coupon being renewed" if b.get("coupon_renewal") else ("paper coupon needed at this store" if s[7] else
                                                                               "show the coupon on your phone at checkout"),
        "coupon_page": with_utm(page or pick(b["page"], lang), utm),
        "map": maps_url(s, b),
    }


def find_stores(place: str | None = None, lat: float | None = None, lng: float | None = None, radius_km: float = 1.0,
                brand: str | None = None, lang: str = "en", limit: int = 10, utm: str | None = None) -> dict:
    db = DB.get()
    lang = lang_of(lang)
    center = None
    if lat is not None and lng is not None:
        center = {"type": "point", "lat": float(lat), "lng": float(lng), "radius_km": radius_km}
    elif place:
        cands = resolve_place(place)
        if not cands:
            return {"error": f"Unknown place: {place!r}. Try a shopping area (Namba, Shinjuku, Ginza…), a city or a train station name, "
                             "or pass latitude and longitude.", "stores": []}
        center = cands[0]
        if radius_km == 1.0:
            radius_km = center.get("radius_km") or 1.0
    else:
        return {"error": "Give a place name or latitude and longitude.", "stores": []}
    bkey = None
    if brand:
        bkey = find_brand_key(brand)
        if not bkey:
            return {"error": f"Unknown brand: {brand!r}.", "brands": [b["key"] for b in db.brands], "stores": []}
    radius_km = max(0.1, min(float(radius_km), 20.0))
    limit = max(1, min(int(limit), 30))
    near = []
    for s in db.store_rows:
        if bkey and db.brands[s[1]]["key"] != bkey:
            continue
        d = km(center["lat"], center["lng"], s[5], s[6])
        if d <= radius_km:
            near.append((d, s))
    near.sort(key=lambda x: x[0])
    c_name = center.get("name")
    return {
        "center": {"type": center["type"], "name": pick(c_name, lang) if isinstance(c_name, dict) else c_name,
                   "lat": center["lat"], "lng": center["lng"], "radius_km": radius_km},
        "found": len(near), "stores": [store_out(s, d, lang, utm) for d, s in near[:limit]],
        "how_to_use": "Free, no app or sign-up: open the coupon page on your phone and show it at checkout. "
                      "Tax-free shopping is separate (show your passport). Distances are straight-line.",
        "data_updated": db.api.get("updated"),
    }


# ---------------------------------------------------------------- brands
def find_brand_key(q: str) -> str | None:
    db = DB.get()
    n = norm(q)
    if n in db.brand_names:
        return db.brand_names[n]
    for name, key in db.brand_names.items():
        if len(n) >= 3 and (n in name or name in n):
            return key
    return None


def brand_out(b: dict, lang: str, utm: str | None, detail: bool = False) -> dict:
    o = {"key": b["key"], "name": pick(b["name"], lang), "category": CATEGORY_NAMES.get(b["category"], b["category"]),
         "max_discount_pct": None if b.get("coupon_renewal") else b["max_off_pct"], "stores": b["stores"],
         "coupon_page": with_utm(pick(b["page"], lang), utm)}
    if b.get("coupon_renewal"):
        o["note"] = "The coupon is being renewed; the page shows the latest status."
    if detail:
        o["discount_by_amount"] = [{"from_jpy": t["min_jpy"], "basis": t["basis"], "off_pct": t["off_pct"]} for t in b.get("tiers") or []]
        o["discount_by_category"] = b.get("category_offs") or []
        o["valid_until"] = b.get("valid_until")
        o["tax_refund_fee"] = fee_text(b.get("refund_fee") or {})
        if (b.get("refund_fee") or {}).get("source"):
            o["tax_refund_fee_source"] = b["refund_fee"]["source"]
    return o


def list_brands(lang: str = "en", utm: str | None = None) -> dict:
    db = DB.get()
    lang = lang_of(lang)
    bs = sorted(db.brands, key=lambda b: -b["stores"])
    return {"brands": [brand_out(b, lang, utm) for b in bs], "total_stores": sum(b["stores"] for b in bs),
            "all_coupons_page": with_utm(pick(db.api["guides"]["all_coupons"], lang), utm), "data_updated": db.api.get("updated")}


def brand_info(brand: str, lang: str = "en", utm: str | None = None) -> dict:
    db = DB.get()
    lang = lang_of(lang)
    k = find_brand_key(brand)
    if not k:
        return {"error": f"Unknown brand: {brand!r}.", "brands": [pick(b["name"], lang) for b in db.brands]}
    return brand_out(db.brand_by_key[k], lang, utm, detail=True)


# ---------------------------------------------------------------- cost comparison
def compare_cost(amount_jpy: int = 30000, lang: str = "en", utm: str | None = None) -> dict:
    """Same purchase (before tax, 10% tax) at every brand: price after the coupon plus the tax refund fee."""
    db = DB.get()
    lang = lang_of(lang)
    amount_jpy = max(1000, min(int(amount_jpy), 10_000_000))
    rows = []
    for b in db.brands:
        d = brand_off_at(b, amount_jpy)
        fee = b.get("refund_fee") or {}
        k = fee.get("kind")
        row = {"brand": pick(b["name"], lang), "category": CATEGORY_NAMES.get(b["category"], b["category"]), "coupon_off_pct": d,
               "tax_refund_fee": fee_text(fee), "coupon_page": with_utm(pick(b["page"], lang), utm)}
        if d is None:
            row.update(you_pay_jpy=None, note="coupon being renewed")
            group = 3
        else:
            base = amount_jpy * (100 - d) / 100
            if k in ("pct", "pctmax"):
                row["you_pay_jpy"] = round(base * (1 + fee["value_pct"] / 100))
                if k == "pctmax":
                    row["note"] = "at most"
                group = 0
            elif k == "flat":
                row["you_pay_jpy"] = round(base + fee["value_jpy"])
                group = 0
            elif k in ("none", "full", "na"):
                row["you_pay_jpy"] = round(base)
                group = 0
            else:
                row["you_pay_jpy"] = round(base)
                row["note"] = "plus a refund fee the store has not published"
                group = 2
            if b["category"] == "duty" or k == "na":
                group = 4
        rows.append((group, row["you_pay_jpy"] or 0, row))
    rows.sort(key=lambda x: (x[0], x[1]))
    return {
        "amount_before_tax_jpy": amount_jpy,
        "method": "Price after the coupon, plus the tax refund fee. In the store you pay the tax-inclusive price and later get the "
                  "tax back minus the fee. Shelf prices for the same product differ between stores, so this compares only the "
                  "coupon and the fee. Duty-free shops sell without tax.",
        "rows": [r for _, _, r in rows],
        "details_page": with_utm(pick(db.api["guides"].get("where_to_shop") or db.api["guides"]["all_coupons"], lang), utm),
        "data_updated": db.api.get("updated"),
    }


# ---------------------------------------------------------------- tax-free basics
TAX_FREE_FACTS = [
    "Since November 1, 2026 Japan uses a refund system: you pay the tax-inclusive price in the store and get the consumption tax back after a customs check when you leave Japan.",
    "Register the refund the way the store asks (many department stores need you at their tax-free counter on the day of purchase).",
    "Do the customs check at the departure airport before checking in your purchases, and leave Japan within 90 days of purchase.",
    "Consumables (food, drinks, cosmetics, medicine) must not be used in Japan; customs checks each receipt as a whole.",
    "Haneda Terminal 1 has no tax refund service (use Terminals 2 and 3).",
    "Some stores deduct a refund fee, and airport cash refunds cost extra; a card, Alipay or WeChat Pay refund usually leaves you more.",
    "The CouponJP discount is separate from tax-free: you get both.",
]


def tax_free_guide(lang: str = "en", utm: str | None = None) -> dict:
    db = DB.get()
    lang = lang_of(lang)
    g = db.api.get("guides") or {}
    return {"facts": TAX_FREE_FACTS,
            "pages": {k: with_utm(pick(v, lang), utm) for k, v in g.items()},
            "note": "Rules from Japan Customs and the Japan Tourism Agency; each store's refund terms can differ."}
