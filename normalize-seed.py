# -*- coding: utf-8 -*-
"""Naver local-search rows -> lunch-picker seed JSON."""
import json, hashlib, importlib.util, re

_spec = importlib.util.spec_from_file_location("price_model", "price-model.py")
price_model = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(price_model)

SRC = "seed-raw.tsv"
POP = "popular-raw.tsv"   # 같은 API 의 sort=comment(리뷰 많은순) 결과
OUT = "restaurants.json"

# Ordered: first match wins, so the specific patterns precede the broad ones.
RULES = [
    ("gukbap", ("순대", "국밥", "곰탕", "설렁탕", "해장", "감자탕")),
    ("donkatsu", ("돈가스", "돈까스")),
    ("chinese", ("중식", "마라탕", "양꼬치")),   # "중식>딤섬,중식만두" 가 면으로 가지 않도록 noodle 앞
    ("noodle", ("칼국수", "국수", "만두", "냉면")),
    ("asian", ("베트남", "아시아", "태국", "인도")),
    ("salad", ("샐러드", "다이어트")),
    ("bunsik", ("분식", "김밥", "떡볶이", "토스트")),
    ("japanese", ("일식", "초밥", "우동", "소바")),
    ("western", ("양식", "이탈리아", "피자", "스페인", "스테이크", "파스타", "햄버거",
                 "브런치", "샌드위치", "패밀리레스토랑", "멕시코")),
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


def building_addr(addr):
    """도로명 + 건물번호까지만 남긴다. 층·호수는 지도 검색을 헷갈리게 하고 틀리기 쉽다.
    "서울특별시 강동구 고덕로 210 지층 5,6호" -> "서울특별시 강동구 고덕로 210"
    """
    toks = addr.split()
    for i in range(1, len(toks)):
        if re.fullmatch(r"\d+(-\d+)?", toks[i]) and re.search(r"(로|길)$", toks[i - 1]):
            return " ".join(toks[:i + 1])
    return addr


def short_id(name, addr):
    return hashlib.sha1((name + "|" + addr).encode("utf-8")).hexdigest()[:8]


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line:
                yield line.split("\t")


# 리뷰 많은순 상위에 뜬 가게. 점수가 아니라 "리뷰가 많다"는 표시만 한다.
# 쇼핑몰은 한 건물에 좌표가 같은 가게가 많아서 이름까지 같이 본다.
popular = set()
for name, cat, addr, mapx, mapy in read_tsv(POP):
    popular.update(((name, mapx, mapy), (name, building_addr(addr))))

rows, seen, dropped, added = [], set(), 0, 0
for src in (SRC, POP):
    for name, cat, addr, mapx, mapy in read_tsv(src):
        if any(d in cat for d in DROP):
            dropped += 1
            continue
        # 같은 가게가 다른 검색어로 두 번 잡히면 주소 표기만 조금 다를 수 있어서 좌표로도 거른다
        key, pos, bld = (name, addr), (name, mapx, mapy), (name, building_addr(addr))
        # 건물 기준 비교는 인기 목록에만 쓴다 (기존 시드는 같은 건물에 같은 이름 지점이 따로 있음)
        if key in seen or pos in seen or (src == POP and bld in seen):
            if src == SRC:
                dropped += 1
            continue
        seen.update((key, pos, bld))
        added += src == POP
        app_cat = classify(cat)
        lat, lng = round(int(mapy) / 1e7, 6), round(int(mapx) / 1e7, 6)
        price, _ = price_model.estimate(name, cat, lat, lng, FALLBACK[app_cat])
        row = {
            "i": short_id(name, addr),          # id 는 원본 주소 기준 (저장된 평점·기록 유지)
            "n": name,
            "c": app_cat,
            "a": building_addr(addr),
            "lat": lat,
            "lng": lng,
            "p": price,
        }
        if pos in popular or bld in popular:
            row["pop"] = 1
        # 버거집은 양식으로 묶이지만 '분위기' 있는 곳이 아니다. 앱에서 태그를 따로 준다
        if "햄버거" in cat:
            row["bg"] = 1
        rows.append(row)

ids = {r["i"] for r in rows}
assert len(ids) == len(rows), "id collision"

rows.sort(key=lambda r: (r["c"], r["n"]))
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(rows, fh, ensure_ascii=False, separators=(",", ":"))

counts, prices = {}, {}
for r in rows:
    counts[r["c"]] = counts.get(r["c"], 0) + 1
    prices.setdefault(r["c"], []).append(r["p"])
print("kept %d (popular-only %d, marked %d), dropped %d" % (
    len(rows), added, sum("pop" in r for r in rows), dropped))
print("%-10s %5s %9s %9s %9s" % ("종류", "곳", "최저", "중앙", "최고"))
for k in sorted(counts, key=lambda x: -counts[x]):
    ps = sorted(prices[k])
    print("%-10s %5d %9s %9s %9s" % (
        k, counts[k], format(ps[0], ","),
        format(ps[len(ps) // 2], ","), format(ps[-1], ",")))
