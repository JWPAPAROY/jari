"""법정동 → 행정동 연결: data/out/bjd_dong.csv (구, 법정동, 행정동코드, 비중)

전월세 실거래는 법정동까지만 공개된다(단독·다가구는 지번도 없음). 가게 인허가 좌표(data/tmp/bjd_pts.csv: 구, 법정동, 위도, 경도, 건수)를
행정동 경계에 넣어, 법정동마다 어느 행정동에 얼마씩 걸쳐 있는지 비중을 낸다. 비중 10% 미만은 버린다.
좌표가 없는 법정동은 bjd_fix.csv(지번 표본 좌표) → 이름이 같은(숫자만 다른) 행정동 순으로 붙인다.
"""
import os, sys, csv, re, collections
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from build_stay import load_dongs, find_dong

dongs = load_dongs()
cnt = collections.defaultdict(collections.Counter)
for gu, bjd, la, lo, n in csv.reader(open('data/tmp/bjd_pts.csv', encoding='utf-8')):
    cd = find_dong(dongs, float(la), float(lo))
    if cd: cnt[(gu, bjd)][cd] += int(n)
need = {(r[0], r[1]) for r in csv.reader(open('data/out/house_rent.csv', encoding='utf-8'))}
stem = lambda s: re.sub(r'[\d·.]+|제(?=\d)', '', s).replace('동동', '동')
# 가게 좌표도 이름 짝도 없는 법정동: 지번 표본을 VWorld로 좌표 변환해 정한 비중(pipeline/geo_bjd.py로 만듦, 새로 빠진 법정동이 생기면 miss 목록 고쳐 다시 실행)
FIX = collections.defaultdict(list)
for gu, bjd, cd, sh in csv.reader(open(os.path.join(os.path.dirname(__file__), 'bjd_fix.csv'), encoding='utf-8')): FIX[(gu, bjd)].append([gu, bjd, cd, float(sh)])
out, fallback, miss = [], 0, []
for key in sorted(need | set(cnt)):
    gu, bjd = key
    c = cnt.get(key)
    if c:
        tot = sum(c.values())
        for cd, n in c.most_common():
            if n / tot >= .1: out.append([gu, bjd, cd, round(n / tot, 3)])
        continue
    if key in FIX: out += FIX[key]; fallback += 1; continue
    base = re.sub(r'\d+가$', '', bjd)   # 충정로2가 → 충정로(행정동 충정로동), 원효로1가 → 원효로1·2동
    hits = [d for d in dongs if d['gu'] == gu and (stem(d['name']) == stem(bjd) or d['name'].startswith(bjd.rstrip('동')) or (base != bjd and d['name'].startswith(base)))]
    if hits:
        fallback += 1
        for d in hits: out.append([gu, bjd, d['cd'], round(1 / len(hits), 3)])
    elif key in need: miss.append(f'{gu} {bjd}')
with open('data/out/bjd_dong.csv', 'w', encoding='utf-8', newline='') as fh: csv.writer(fh).writerows(out)
print(f'법정동→행정동 {len(out):,}줄 · 이름으로 붙임 {fallback} · 못 붙인 법정동 {len(miss)} {miss[:8]}', flush=True)
