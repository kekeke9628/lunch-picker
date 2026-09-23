# -*- coding: utf-8 -*-
"""Naver local-search rows -> lunch-picker seed JSON."""
import json, hashlib, importlib.util

_spec = importlib.util.spec_from_file_location("price_model", "price-model.py")
price_model = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(price_model)

SRC = "seed-raw.tsv"
OUT = "restaurants.json"

# Ordered: first match wins, so the specific patterns precede the broad ones.
RULES = [
    ("gukbap", ("순대", "국밥", "곰탕", "설렁탕", "해장", "감자탕")),
    ("donkatsu", ("돈가스", "돈까스")),
    ("noodle", ("칼국수", "국수", "만두")),
    ("asian", ("베트남", "아시아", "태국")),
    ("salad", ("샐러드", "다이어트")),
    ("bunsik", ("분식", "김밥", "떡볶이")),
    ("chinese", ("중식",)),
    ("japanese", ("일식", "초밥", "우동", "소바")),
    ("western", ("양식", "이탈리아", "피자", "스페인", "스테이크", "파스타", "햄버거")),
    ("korean", ("한식",)),
]
DROP = ("술집", "이자카야", "요리주점", "카페", "베이커리")


def classify(naver_cat):
    for key, needles in RULES:
        if any(n in naver_cat for n in needles):
            return key
    return "korean"


FALLBACK = {
    "korean": 10000, "gukbap": 10000, "chinese": 10000, "japanese": 14000,
    "donkatsu": 12000, "western": 16000, "bunsik": 8000, "noodle": 10000,
    "asian": 11000, "salad": 12000,
}


def short_id(name, addr):
    return hashlib.sha1((name + "|" + addr).encode("utf-8")).hexdigest()[:8]


rows, seen, dropped = [], set(), 0
with open(SRC, encoding="utf-8") as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        name, cat, addr, mapx, mapy = line.split("\t")
        if any(d in cat for d in DROP):
            dropped += 1
            continue
        key = (name, addr)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        app_cat = classify(cat)
        lat, lng = round(int(mapy) / 1e7, 6), round(int(mapx) / 1e7, 6)
        price, _ = price_model.estimate(name, cat, lat, lng, FALLBACK[app_cat])
        rows.append({
            "i": short_id(name, addr),
            "n": name,
            "c": app_cat,
            "a": addr,
            "lat": lat,
            "lng": lng,
            "p": price,
        })

ids = {r["i"] for r in rows}
assert len(ids) == len(rows), "id collision"

rows.sort(key=lambda r: (r["c"], r["n"]))
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(rows, fh, ensure_ascii=False, separators=(",", ":"))

counts, prices = {}, {}
for r in rows:
    counts[r["c"]] = counts.get(r["c"], 0) + 1
    prices.setdefault(r["c"], []).append(r["p"])
print("kept %d, dropped %d" % (len(rows), dropped))
print("%-10s %5s %9s %9s %9s" % ("종류", "곳", "최저", "중앙", "최고"))
for k in sorted(counts, key=lambda x: -counts[x]):
    ps = sorted(prices[k])
    print("%-10s %5d %9s %9s %9s" % (
        k, counts[k], format(ps[0], ","),
        format(ps[len(ps) // 2], ","), format(ps[-1], ",")))
