"""주택 전월세 실거래(국토교통부) → data/out/house_rent.csv

연립·다세대, 단독·다가구, 오피스텔의 최근 24개월 계약을 법정동 × 주택 종류 × 면적대 × 기간(최근 1년/그 전 1년)으로 묶어
월세 중앙값·보증금 중앙값·전세 보증금 중앙값을 낸다. 개별 계약은 저장하지 않는다.
- 단독·다가구는 지번이 공개되지 않아 법정동까지만 안다 → 행정동 연결은 load_house.sh(bjd_dong)에서.
- 면적: 연립·다세대·오피스텔은 전용면적, 단독·다가구는 계약면적(totalFloorAr).
- 계약은 신고까지 최대 30일 늦게 올라오므로 최근 3개월은 매번 다시 받고, 그보다 오래된 달은 받아 둔 파일을 쓴다.
사용: DATA_GO_KR_KEY=... python -I pipeline/fetch_house.py
"""
import os, sys, csv, json, time, statistics, collections, datetime as dt, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from fetch import SEOUL

KEY = os.environ.get('DATA_GO_KR_KEY') or open(os.path.expanduser('~/.secrets/datagokr-api-key.txt')).read().strip()
RAW, OUT = 'data/raw/house', 'data/out'
GU5 = {'종로구': '11110', '중구': '11140', '용산구': '11170', '성동구': '11200', '광진구': '11215', '동대문구': '11230', '중랑구': '11260',
       '성북구': '11290', '강북구': '11305', '도봉구': '11320', '노원구': '11350', '은평구': '11380', '서대문구': '11410', '마포구': '11440',
       '양천구': '11470', '강서구': '11500', '구로구': '11530', '금천구': '11545', '영등포구': '11560', '동작구': '11590', '관악구': '11620',
       '서초구': '11650', '강남구': '11680', '송파구': '11710', '강동구': '11740'}
TYPES = {'연립다세대': ('RTMSDataSvcRHRent/getRTMSDataSvcRHRent', 'excluUseAr'),
         '단독다가구': ('RTMSDataSvcSHRent/getRTMSDataSvcSHRent', 'totalFloorAr'),
         '오피스텔': ('RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent', 'excluUseAr')}
MONTHS = 24
BANDS = (('원룸급', 0, 30), ('투룸급', 30, 60), ('60㎡ 이상', 60, 1e9))

def num(s):
    try: return float((s or '').replace(',', '').strip())
    except ValueError: return None

def month(svc, gu5, ym):
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({'serviceKey': KEY, 'LAWD_CD': gu5, 'DEAL_YMD': ym, 'pageNo': page, 'numOfRows': 1000})
        for i in range(4):
            try:
                root = ET.fromstring(urllib.request.urlopen(f'https://apis.data.go.kr/1613000/{svc}?{q}', timeout=60).read()); break
            except Exception as e: err = e; time.sleep(3 * (i + 1))
        else: raise RuntimeError(f'{svc} {gu5} {ym}: {err}')
        code = root.findtext('.//resultCode')
        if code not in ('000', '00'): raise RuntimeError(f'{svc} {gu5} {ym}: {code} {root.findtext(".//resultMsg")}')
        items = root.findall('.//item'); rows += [{c.tag: (c.text or '').strip() for c in it} for it in items]
        total = int(root.findtext('.//totalCount') or 0)
        if page * 1000 >= total or not items: return rows
        page += 1

if __name__ == '__main__':
    os.makedirs(RAW, exist_ok=True)
    today = dt.date.today()
    yms = [(today.replace(day=1) - dt.timedelta(days=1) * 0).replace(day=1)]
    for _ in range(MONTHS - 1): yms.append((yms[-1] - dt.timedelta(days=1)).replace(day=1))
    yms = [d.strftime('%Y%m') for d in yms]           # 이번 달 포함 24개월(이번 달은 아직 일부)
    fresh = set(yms[:3]); calls = 0
    deals = []   # (gu, 법정동, 종류, 기간, 면적, 보증금, 월세)
    for t, (svc, area_col) in TYPES.items():
        for gu, g5 in GU5.items():
            for idx, ym in enumerate(yms):
                p = f'{RAW}/{t}_{g5}_{ym}.json'
                if ym in fresh or not os.path.exists(p):
                    rows = month(svc, g5, ym); calls += 1
                    json.dump([[r.get('umdNm', ''), r.get(area_col, ''), r.get('deposit', ''), r.get('monthlyRent', '')] for r in rows], open(p, 'w', encoding='utf-8'), ensure_ascii=False)
                per = 0 if idx < 12 else 1
                for bjd, ar, dep, mr in json.load(open(p, encoding='utf-8')):
                    a, d, m = num(ar), num(dep), num(mr)
                    if not bjd or not a or d is None or m is None: continue
                    deals.append((gu, bjd, t, per, a, d, m))
        print(f'{t} 받음 (지금까지 호출 {calls})', flush=True)
    for f in os.listdir(RAW):   # 24개월 밖 파일 정리
        if f.rsplit('_', 1)[-1][:6] < yms[-1]: os.remove(f'{RAW}/{f}')
    g = collections.defaultdict(lambda: {'w': [], 'j': []})
    for gu, bjd, t, per, a, d, m in deals:
        for band, lo, hi in (('전체', 0, 1e9),) + BANDS:
            if lo <= a < hi:
                k = (gu, bjd, t, band, per)
                if m > 0: g[k]['w'].append((m, d, a))
                else: g[k]['j'].append(d)
    med = lambda xs: round(statistics.median(xs), 1) if xs else ''
    with open(f'{OUT}/house_rent.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        for (gu, bjd, t, band, per), v in sorted(g.items()):
            ws = v['w']
            w.writerow([gu, bjd, t, band, per, len(ws), med([x[0] for x in ws]), med([x[1] for x in ws]), med([x[2] for x in ws]),
                        med([x[0] / x[2] * 3.3058 for x in ws]), len(v['j']), med(v['j'])])
    n1 = sum(1 for x in deals if x[3] == 0)
    print(f'전월세 계약 {len(deals):,}건(최근 1년 {n1:,}) · 법정동 {len({(x[0], x[1]) for x in deals}):,} · 호출 {calls}', flush=True)
