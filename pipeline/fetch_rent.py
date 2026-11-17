"""한국부동산원 상업용부동산 임대동향(R-ONE) → data/out/rent.csv, data/out/area_rent.csv

- 소규모·중대형 상가의 ㎡당 월 임대료(천원)와 공실률(%), 분기별. 서울 조사 상권 약 70곳 + 서울 전체.
- 조사 상권은 경계가 공개되지 않아, 상권마다 대표 서울시 상권(ANCHORS)의 중심을 위치로 삼고
  서울시 상권 1,650곳을 가장 가까운 조사 상권(MAX_KM 안)에 붙인다. 화면에는 '가까운 조사 상권' 값으로만 보여 준다.
사용: RONE_KEY=... python -I pipeline/fetch_rent.py   (data/out/area.csv 필요 → build.py 뒤)
"""
import os, sys, csv, json, math, time, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

KEY = os.environ.get('RONE_KEY') or open(os.path.expanduser('~/.secrets/rone-key.txt')).read().strip()
OUT = 'data/out'
MAX_KM = 1.5
# (종류, 항목, 표 ID 목록: 계열이 2024년 3분기·2026년 3분기에 나뉨)
TABLES = [('소규모', 'rent', ['T248223134698125', 'T269273143698159']), ('중대형', 'rent', ['T244363134858603', 'T269343143745470']),
          ('소규모', 'vac', ['T241833134686576', 'T262053143683833']), ('중대형', 'vac', ['T249633134845544', 'T267693143622612'])]
# 조사 상권 → 위치를 대표하는 서울시 상권 이름(여러 개면 중심의 평균)
ANCHORS = {
 '강남대로': ['강남역'], '교대역': ['교대역(법원.검찰청)'], '남부터미널': ['남부터미널역'], '논현역': ['논현역', '신논현역'],
 '도산대로': ['도산공원교차로'], '신사역': ['신사역'], '압구정': ['압구정역', '압구정로데오역(압구정로데오)'],
 '청담': ['청담사거리(청담동명품거리)'], '테헤란로': ['역삼역', '선릉역'], '학동/강남구청역': ['학동역', '강남구청역'],
 '서래마을': ['서래마을카페거리(서래마을)'], '방배역/내방역': ['방배역', '내방역'], '양재역': ['양재역'], '양재말죽거리': ['양재역'],
 '가락시장': ['가락시장'], '건대입구': ['건대입구역(건대)'], '경희대': ['경희대학교(경희대)'], '군자': ['군자역'], '구의역': ['구의역'],
 '까치산역': ['까치산역'], '노량진': ['노량진역(노량진)'], '독산/시흥': ['독산동', '서울시흥동우체국(홈플러스시흥점)'], '뚝섬': ['뚝섬역'],
 '목동': ['목동역 8번출구'], '미아사거리': ['미아사거리역'], '불광역': ['불광역'], '사당': ['사당역(사당)'], '상계역': ['상계백병원'],
 '상봉역': ['상봉역'], '서울대입구역': ['서울대입구역'], '낙성대': ['낙성대역 1번(관악구민 종합체육센터)'], '성신여대': ['성신여대'],
 '수유': ['수유역'], '숙명여대': ['숙대입구역(남영역, 남영동)'], '신림역': ['신림역(신림)'], '약수역': ['약수역'], '연신내': ['연신내역'],
 '오류동역': ['오류동역'], '왕십리': ['왕십리역(왕십리)'], '용산역': ['신용산역(용산역)'], '이태원': ['이태원(이태원역)'],
 '잠실/송파': ['잠실역', '송파사거리(송파역)'], '잠실새내역': ['잠실새내역(신천)'], '장안동': ['장안동사거리'], '천호': ['천호역'],
 '청량리': ['청량리역(청량리)'], '혜화동': ['대학로(혜화역)'], '화곡': ['화곡역'], '구로디지털단지역': ['구로디지털단지역'],
 '쌍문역': ['쌍문역1번(쌍리단길)'], '광화문': ['광화문역'], '남대문': ['남대문시장(자유상가)'], '동대문': ['동대문역사문화공원역'],
 '명동': ['명동(명동거리)'], '방산시장': ['방산종합시장(방산시장)'], '북촌': ['북촌(안국역)'], '서촌': ['서촌(경복궁역)'],
 '시청': ['서울시청'], '을지로': ['을지로3가역'], '종로': ['종로3가역'], '충무로': ['충무로역'], '공덕역': ['공덕역(공덕오거리)'],
 '당산역': ['당산역'], '동교/연남': ['연남동(홍대)'], '망원역': ['망원역'], '신촌/이대': ['신촌역(신촌역, 신촌로터리)', '이화여대(이대역, 이대)'],
 '영등포역': ['영등포역(영등포)'], '홍대/합정': ['홍대입구역(홍대)', '합정역', '서교동(홍대)'],
}

def table(tid):
    rows, p = [], 1
    while True:
        url = f'https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do?KEY={KEY}&Type=json&pIndex={p}&pSize=1000&STATBL_ID={tid}&DTACYCLE_CD=QY'
        for i in range(4):
            try: d = json.loads(urllib.request.urlopen(url, timeout=60).read().decode('utf-8')); break
            except Exception as e: err = e; time.sleep(3 * (i + 1))
        else: raise RuntimeError(f'{tid}: {err}')
        if 'SttsApiTblData' not in d: raise RuntimeError(f'{tid}: {d}')
        r = d['SttsApiTblData'][1]['row']; rows += r
        if len(r) < 1000: return rows
        p += 1

if __name__ == '__main__':
    val = {}   # (조사 상권, 분기, 종류) → {rent, vac}
    for kind, item, tids in TABLES:
        for tid in tids:
            for r in table(tid):
                f = r.get('CLS_FULLNM') or ''
                if not (f == '서울' or f.startswith('서울>')) or r.get('DTA_VAL') is None: continue
                reg = '서울' if f == '서울' else f.split('>')[-1] if f.count('>') == 2 else None
                if not reg: continue   # 권역(도심·강남 …)은 쓰지 않음
                q = int(r['WRTTIME_IDTFR_ID'][:4]) * 10 + int(r['WRTTIME_IDTFR_ID'][4:])
                val.setdefault((reg, q, kind), {})[item] = float(r['DTA_VAL'])
    regions = sorted({k[0] for k in val} - {'서울'})
    miss = [r for r in regions if r not in ANCHORS]
    if miss: print('위치를 모르는 조사 상권(ANCHORS에 추가 필요):', miss, flush=True)
    with open(f'{OUT}/rent.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        for (reg, q, kind), v in sorted(val.items()):
            w.writerow([reg, q, kind, round(v['rent'], 3) if 'rent' in v else '', round(v['vac'], 2) if 'vac' in v else ''])
    areas = list(csv.DictReader(open(f'{OUT}/area.csv', encoding='utf-8')))
    by_name = {a['name']: a for a in areas}
    pos = {}
    for reg in regions:
        pts = [(float(by_name[n]['lat']), float(by_name[n]['lon'])) for n in ANCHORS.get(reg, []) if n in by_name and by_name[n]['lat']]
        if pts: pos[reg] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        elif reg in ANCHORS: print('대표 상권 이름이 없음:', reg, ANCHORS[reg], flush=True)
    km = lambda a, b: math.hypot((a[0] - b[0]) * 111, (a[1] - b[1]) * 88.2)
    n = 0
    with open(f'{OUT}/area_rent.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        for a in areas:
            if not a['lat']: continue
            p = (float(a['lat']), float(a['lon']))
            d, reg = min((km(p, q), r) for r, q in pos.items())
            if d <= MAX_KM: w.writerow([a['code'], reg, round(d * 1000)]); n += 1
    qs = sorted({k[1] for k in val})
    print(f'조사 상권 {len(regions)}곳(위치 {len(pos)}), 분기 {qs[0]}~{qs[-1]}, 서울시 상권 연결 {n:,}/{len(areas):,}', flush=True)
