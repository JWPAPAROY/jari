"""원자료 → DB 적재용 CSV (data/out/)

license.csv  인허가 전체(2016년 이후 영업한 기록)
cohort.csv   개업 후 3년이 지난 가게(2016-01-01 이후 개업)의 3년 내 폐업 여부
area.csv     서울시 상권 영역(위경도, 단순화)
사용: python -I pipeline/build.py [구 이름 ...]   (생략 시 data/raw 안의 구 전부)
"""
import csv, io, json, os, re, sys, zipfile, collections, datetime as dt
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
import geo

RAW, OUT = 'data/raw', 'data/out'
TODAY = dt.date.today()
HORIZON = 1095
KEEP_FROM = dt.date(2016, 1, 1)

SVC_NM = {'CS100001': '한식', 'CS100002': '중식', 'CS100003': '일식', 'CS100004': '양식', 'CS100005': '제과',
          'CS100006': '패스트푸드', 'CS100007': '치킨', 'CS100008': '분식', 'CS100009': '호프·주점', 'CS100010': '커피·음료'}

def svc(biz, kind):
    b = biz or ''
    if kind == '휴게':
        if any(k in b for k in ('커피', '까페', '카페', '다방', '전통찻집', '기타 휴게')): return 'CS100010'
        if '패스트' in b: return 'CS100006'
        if '분식' in b or '김밥' in b: return 'CS100008'
        if '아이스크림' in b or '제과' in b: return 'CS100005'
        return 'CS100010'
    if '한식' in b or '식육' in b or '탕류' in b or '냉면' in b or '횟집' in b or '복어' in b: return 'CS100001'
    if '중국' in b: return 'CS100002'
    if '일식' in b: return 'CS100003'
    if '경양식' in b or '외국' in b or '뷔페' in b: return 'CS100004'
    if '패스트' in b: return 'CS100006'
    if '통닭' in b or '치킨' in b: return 'CS100007'
    if '분식' in b or '김밥' in b: return 'CS100008'
    if '호프' in b or '정종' in b or '감성주점' in b or '라이브' in b: return 'CS100009'
    if '까페' in b or '커피' in b: return 'CS100010'
    return None

FOOD_WORDS = ('음식점', '분식점', '제과점', '주점', '상점', '반점', '식당점', '정육점')
def is_chain(name):
    n = re.sub(r'\s+', ' ', name or '').strip()
    n = re.sub(r'\)$', '', n)
    if not n.endswith('점') or len(n) < 4: return False
    return not any(n.endswith(w) for w in FOOD_WORDS)

def floor_of(road, jibun):
    t = (road or '') + ' ' + (jibun or '')
    if re.search(r'지하|지\s*\d+\s*층|B\d', t): return '지하'
    m = re.search(r'(\d+)\s*층', t)
    if m: return '1층' if m.group(1) == '1' else '2층 이상'
    return '층 미상'

def size_band(s):
    if not s: return '미기재'
    if s < 33: return '10평 미만'
    if s < 66: return '10~20평'
    if s < 99: return '20~30평'
    return '30평 이상'

def jkey(addr):
    m = re.search(r'(\S+구)\s+(\S+동\d*가?)\s+(산\s*)?(\d+)(?:-(\d+))?', addr or '')
    if not m: return None
    return f"{m.group(1)}|{m.group(2)} {m.group(4)}" + (f"-{m.group(5)}" if m.group(5) and m.group(5) != '0' else '')

def d(s):
    try: return dt.date.fromisoformat((s or '').strip()[:10])
    except ValueError: return None

# ---------- 상권 영역 (5181) + 격자 색인
def load_areas():
    zr = zipfile.ZipFile(f'{RAW}/relm.zip')
    nm = {n[-3:].lower(): n for n in zr.namelist()}
    polys = geo.read_shp_polygons(zr.read(nm['shp']))
    attrs = geo.read_dbf(zr.read(nm['dbf']))
    areas = []
    for p, a in zip(polys, attrs):
        if not p: continue
        areas.append(dict(code=a['TRDAR_CD'], name=a['TRDAR_CD_N'], kind=a['TRDAR_SE_1'], gu_cd=a['SIGNGU_CD_'],
                          area=float(a['RELM_AR'] or 0), bbox=p[0], rings=p[1]))
    return areas
G = 500.0
def grid_index(areas):
    idx = collections.defaultdict(list)
    for i, a in enumerate(areas):
        x0, y0, x1, y1 = a['bbox']
        for gx in range(int(x0 // G), int(x1 // G) + 1):
            for gy in range(int(y0 // G), int(y1 // G) + 1):
                idx[(gx, gy)].append(i)
    return idx
def find_area(areas, idx, x, y):
    hit = [areas[i] for i in idx.get((int(x // G), int(y // G)), ())
           if areas[i]['bbox'][0] <= x <= areas[i]['bbox'][2] and areas[i]['bbox'][1] <= y <= areas[i]['bbox'][3]
           and geo.point_in_rings(x, y, areas[i]['rings'])]
    return min(hit, key=lambda a: a['area'])['code'] if hit else None

def ring_latlon(ring, tol=8.0):
    out, last = [], None
    for x, y in ring:
        if last and abs(x - last[0]) < tol and abs(y - last[1]) < tol: continue
        lat, lon = geo.tm_inverse(x, y, geo.GRS80, 127.0)
        out.append([round(lon, 5), round(lat, 5)]); last = (x, y)
    if len(out) >= 3 and out[0] != out[-1]: out.append(out[0])
    return out

# ---------- 구별 처리
def process_gu(gu, areas, idx, wl, wc):
    stores = []
    for fn, kind in (('general_restaurants.csv', '음식점'), ('rest_cafes.csv', '휴게')):
        for r in csv.DictReader(open(f'{RAW}/{gu}/{fn}', encoding='cp949', errors='replace')):
            o = d(r['인허가일자'])
            if not o: continue
            status = (r['영업상태명'] or '').strip()
            c = d(r['폐업일자']) if status.startswith('폐업') else None
            if c and c < KEEP_FROM: continue
            lat = lon = area = None
            try:
                x, y = float(r['좌표정보(X)']), float(r['좌표정보(Y)'])
                lat, lon = geo.localdata_to_latlon(x, y, '5174')
                X, Y = geo.latlon_to_5181(lat, lon)
                area = find_area(areas, idx, X, Y)
            except (ValueError, TypeError):
                pass
            sz = (r['소재지면적'] or '').strip()
            name = (r['사업장명'] or '').strip()
            jib, road = (r['지번주소'] or '').strip(), (r['도로명주소'] or '').strip()
            stores.append(dict(id=r['관리번호'].strip(), gu=gu, kind=kind, name=name, biz=(r['업태구분명'] or '').strip(),
                               svc=svc(r['업태구분명'], kind), open=o, close=c, status=status, jibun=jib, road=road,
                               jkey=jkey(jib), size=float(sz) if re.match(r'^[0-9.]+$', sz) and float(sz) > 0 else None,
                               floor=floor_of(road, jib), chain=is_chain(name), lat=lat, lon=lon, area=area))
    seen = set(); uniq = []
    for s in stores:
        if s['id'] in seen: continue
        seen.add(s['id']); uniq.append(s)
    stores = uniq

    by_name = collections.defaultdict(list); by_jibun = collections.defaultdict(list)
    for s in stores:
        by_name[(s['jibun'], s['name'])].append(s); by_jibun[s['jibun']].append(s)
    def died(s):
        if not s['close'] or (s['close'] - s['open']).days >= HORIZON: return False
        for t in by_name[(s['jibun'], s['name'])]:   # 같은 자리·같은 상호 60일 안 재개업 = 명의변경
            if t is not s and t['open'] >= s['close'] and (t['open'] - s['close']).days <= 60: return False
        return True
    def spot(s):
        lo = s['open'] - dt.timedelta(days=HORIZON)
        return min(2, sum(1 for t in by_jibun[s['jibun']] if t is not s and t['close'] and lo <= t['close'] <= s['open'] and t['name'] != s['name']))

    nc = 0
    for s in stores:
        wl.writerow([s['id'], gu, s['kind'], s['name'], s['biz'], SVC_NM.get(s['svc'], ''), s['open'], s['close'] or '',
                     s['status'], s['jibun'], s['road'], s['jkey'] or '', s['size'] or '', s['floor'],
                     't' if s['chain'] else 'f', s['lat'] or '', s['lon'] or '', s['area'] or ''])
        if s['svc'] and s['open'] >= KEEP_FROM and (TODAY - s['open']).days > HORIZON:
            wc.writerow([s['id'], gu, s['area'] or '', SVC_NM[s['svc']], size_band(s['size']), s['floor'],
                         't' if s['chain'] else 'f', spot(s), 't' if died(s) else 'f', s['open']]); nc += 1
    print(f'{gu}: 인허가 {len(stores):,}  코호트 {nc:,}', flush=True)

if __name__ == '__main__':
    gus = sys.argv[1:] or sorted(n for n in os.listdir(RAW) if os.path.isdir(f'{RAW}/{n}'))
    os.makedirs(OUT, exist_ok=True)
    areas = load_areas(); idx = grid_index(areas)
    with open(f'{OUT}/area.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh); w.writerow(['code', 'name', 'kind', 'gu', 'geom'])
        GU_CD = {'11110': '종로구', '11140': '중구', '11170': '용산구', '11200': '성동구', '11215': '광진구', '11230': '동대문구',
                 '11260': '중랑구', '11290': '성북구', '11305': '강북구', '11320': '도봉구', '11350': '노원구', '11380': '은평구',
                 '11410': '서대문구', '11440': '마포구', '11470': '양천구', '11500': '강서구', '11530': '구로구', '11545': '금천구',
                 '11560': '영등포구', '11590': '동작구', '11620': '관악구', '11650': '서초구', '11680': '강남구', '11710': '송파구', '11740': '강동구'}
        for a in areas:
            w.writerow([a['code'], a['name'], a['kind'], GU_CD.get(a['gu_cd'], a['gu_cd']),
                        json.dumps([ring_latlon(r) for r in a['rings']], separators=(',', ':'))])
    print('상권', len(areas), flush=True)
    with open(f'{OUT}/license.csv', 'w', encoding='utf-8', newline='') as fl, open(f'{OUT}/cohort.csv', 'w', encoding='utf-8', newline='') as fc:
        wl, wc = csv.writer(fl), csv.writer(fc)
        for g in gus:
            process_gu(g, areas, idx, wl, wc)
    json.dump({'gus': gus, 'built': TODAY.isoformat()}, open(f'{OUT}/meta.json', 'w', encoding='utf-8'), ensure_ascii=False)
