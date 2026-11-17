"""서울시 상권분석서비스(OpenAPI) 분기 자료 → data/out/area_q.csv, area_sales.csv

- 추정매출-상권(VwsmTrdarSelngQq): 외식 10개 + 생활서비스·소매 일부(OTHER) 업종 (jari 업종 이름으로 바꿈) + 모든 업종 합계(ALL)
- 길단위인구(VwsmTrdarFlpopQq), 상주인구(VwsmTrdarRepopQq), 직장인구(VwsmTrdarWrcPopltnQq), 상권변화지표(VwsmTrdarIxQq)
사용: SEOUL_API_KEY=... python -I pipeline/fetch_trend.py [이미 있는 분기 ...]
  인자로 받은 분기는 건너뜀(단, 가장 최근 2개 분기는 수정될 수 있어 항상 다시 받음).
"""
import os, sys, csv, json, time, urllib.request, collections
sys.stdout.reconfigure(encoding='utf-8')

KEY = os.environ.get('SEOUL_API_KEY') or open(os.path.expanduser('~/.secrets/seoul-openapi-key.txt')).read().strip()
OUT = 'data/out'
FIRST = 20223                     # 3년 전 같은 4개 분기와 비교하려면 최근 16개 분기가 필요
FOOD = {'CS100001': '한식', 'CS100002': '중식', 'CS100003': '일식', 'CS100004': '양식', 'CS100005': '제과',
        'CS100006': '패스트푸드', 'CS100007': '치킨', 'CS100008': '분식', 'CS100009': '호프·주점', 'CS100010': '커피·음료'}
# 외식 밖 업종(매출만, '전체'=외식 합에는 안 넣음). 헬스장=스포츠클럽, 약국=의약품, 체육도장=스포츠 강습은 가장 가까운 업종
OTHER = {'CS200006': '의원', 'CS200007': '치과', 'CS200008': '한의원', 'CS200028': '미용실', 'CS200029': '네일', 'CS200030': '피부관리',
         'CS200031': '세탁소', 'CS200037': '노래방', 'CS200019': 'PC방', 'CS200016': '당구장', 'CS200024': '헬스장', 'CS200005': '체육도장',
         'CS300001': '슈퍼마켓', 'CS300002': '편의점', 'CS300016': '안경점', 'CS300018': '약국',
         'CS200001': '학원', 'CS200002': '학원', 'CS200003': '학원'}

def call(svc, a, b, q, tries=5):
    url = f'http://openapi.seoul.go.kr:8088/{KEY}/json/{svc}/{a}/{b}/{q}'
    for i in range(tries):
        try:
            d = json.loads(urllib.request.urlopen(url, timeout=60).read().decode('utf-8'))
            if svc not in d:
                code = d.get('RESULT', {}).get('CODE', '')
                if code == 'INFO-200': return 0, []          # 자료 없음
                raise RuntimeError(d)
            return d[svc]['list_total_count'], d[svc]['row']
        except Exception as e:
            err = e; time.sleep(3 * (i + 1))
    raise RuntimeError(f'{svc} {q} {a}-{b}: {err}')

def rows(svc, q):
    n, first = call(svc, 1, 1000, q)
    out = list(first)
    for a in range(1001, n + 1, 1000):
        out += call(svc, a, a + 999, q)[1]
    return out

def quarters(start, end):
    y, k = divmod(start, 10)
    while y * 10 + k <= end:
        yield y * 10 + k
        k += 1
        if k == 5: y, k = y + 1, 1

def latest():
    y = time.gmtime().tm_year
    for q in sorted((yy * 10 + k for yy in (y, y - 1) for k in (1, 2, 3, 4)), reverse=True):
        if call('VwsmTrdarIxQq', 1, 1, q)[0]: return q
    raise RuntimeError('최근 분기를 찾지 못함')

if __name__ == '__main__':
    have = {int(x) for x in sys.argv[1:] if x.isdigit()}
    last = latest()
    qs = list(quarters(FIRST, last))
    todo = [q for q in qs if q not in have or q in qs[-2:]]
    print(f'최근 분기 {last}, 받을 분기 {todo}', flush=True)
    os.makedirs(OUT, exist_ok=True)
    fq = open(f'{OUT}/area_q.csv', 'w', encoding='utf-8', newline=''); wq = csv.writer(fq)
    fs = open(f'{OUT}/area_sales.csv', 'w', encoding='utf-8', newline=''); ws = csv.writer(fs)
    num = lambda r, k: float(r.get(k) or 0)
    for q in todo:
        rec = collections.defaultdict(dict)
        for r in rows('VwsmTrdarFlpopQq', q):
            rec[r['TRDAR_CD']].update(flpop=num(r, 'TOT_FLPOP_CO'), flpop2030=num(r, 'AGRDE_20_FLPOP_CO') + num(r, 'AGRDE_30_FLPOP_CO'))
        for r in rows('VwsmTrdarRepopQq', q):
            rec[r['TRDAR_CD']]['repop'] = num(r, 'TOT_REPOP_CO')
        for r in rows('VwsmTrdarWrcPopltnQq', q):
            rec[r['TRDAR_CD']]['wrc'] = num(r, 'TOT_WRC_POPLTN_CO')
        for r in rows('VwsmTrdarIxQq', q):
            rec[r['TRDAR_CD']].update(ix=r['TRDAR_CHNGE_IX'], ix_nm=r['TRDAR_CHNGE_IX_NM'], opr=num(r, 'OPR_SALE_MT_AVRG'), cls=num(r, 'CLS_SALE_MT_AVRG'))
        for code, v in rec.items():
            wq.writerow([code, q] + [v.get(k, '') for k in ('flpop', 'flpop2030', 'repop', 'wrc', 'ix', 'ix_nm', 'opr', 'cls')])
        agg = collections.defaultdict(lambda: [0.0, 0.0, 0.0])   # (상권, 업종) → 금액, 건수, 20·30대 금액
        for r in rows('VwsmTrdarSelngQq', q):
            amt, cnt, yng = num(r, 'THSMON_SELNG_AMT'), num(r, 'THSMON_SELNG_CO'), num(r, 'AGRDE_20_SELNG_AMT') + num(r, 'AGRDE_30_SELNG_AMT')
            keys = ['ALL']
            if r['SVC_INDUTY_CD'] in FOOD: keys += [FOOD[r['SVC_INDUTY_CD']], '전체']
            elif r['SVC_INDUTY_CD'] in OTHER: keys.append(OTHER[r['SVC_INDUTY_CD']])
            for k in keys:
                a = agg[(r['TRDAR_CD'], k)]; a[0] += amt; a[1] += cnt; a[2] += yng
        for (code, svc), (amt, cnt, yng) in agg.items():
            ws.writerow([code, q, svc, round(amt), round(cnt), round(yng)])
        print(f'{q}: 상권 {len(rec)}, 매출 {len(agg)}행', flush=True)
    fq.close(); fs.close()
    open(f'{OUT}/trend_quarters.txt', 'w').write(' '.join(map(str, todo)))
