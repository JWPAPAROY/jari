"""민박 원자료 → data/out/stay.csv, data/out/dong.csv, data/out/stay_meta.json

stay.csv  민박 한 곳 = 한 줄 (외국인관광 도시민박업 + 한옥체험업)
dong.csv  행정동 한 곳 = 한 줄: 민박 공급(영업 중·객실·신규·폐업·생존율), 수요(단기체류 외국인 생활인구 밤·낮 평균),
          숙박 객실(민박+호텔·모텔 등) 1개당 밤 외국인 수와 그 백분위, 영업 중 민박의 건물 종류
수요는 서울시 '단기체류 외국인 생활인구'(통신 기반 추정, 행정동·시간대)의 마지막 28일 평균.
  밤(01~05시) = 그 동에서 잠자는 외국인 → 숙박 수요에 가까움 / 낮(11~18시) = 그 동을 찾는 외국인
사용: python -I pipeline/build_stay.py   (fetch_stay.py, fetch.py(relm.zip) 뒤)
"""
import os, sys, csv, json, re, glob, math, collections, datetime as dt
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
import geo
from build import load_areas, grid_index, find_area, jkey, road_short, d, KEEP_FROM
from fetch import SEOUL

RAW, OUT = 'data/raw', 'data/out'
TODAY = dt.date.today()
SLUGS = (('foreigner_city_homestays', '도시민박'), ('hanok_experience', '한옥체험'))
NIGHT, DAY = {'01', '02', '03', '04', '05'}, {'11', '12', '13', '14', '15', '16', '17', '18'}
MIN_NIGHT = 100         # 밤 외국인이 이보다 적은 동은 '객실당' 순위에서 뺌(수요가 거의 없음)
K_ROOMS = 10            # 객실이 0~2개인 동에서 나눗셈이 튀지 않게 더하는 가상 객실 수

def bld_kind(s):
    s = s or ''
    for k, w in (('다가구', '다가구'), ('다세대', '다세대'), ('아파트', '아파트'), ('연립', '연립'), ('다중', '다가구'), ('단독', '단독')):
        if k in s: return w
    return '기타' if s.strip() else ''

def rooms_of(r):
    a = (r.get('객실수') or '').strip()
    b = r.get('보험기관명') or ''   # 이 열에 'N실(M명)'이 들어 있는 기록이 많음(원자료 열 어긋남)
    m = re.search(r'(\d+)\s*실', b); g = re.search(r'(\d+)\s*명', b)
    rooms = int(a) if a.isdigit() and 0 < int(a) < 60 else int(m.group(1)) if m and 0 < int(m.group(1)) < 60 else None
    return rooms, int(g.group(1)) if g and 0 < int(g.group(1)) < 200 else None

def load_dongs():
    fs = json.load(open(f'{RAW}/dong/hjd.geojson', encoding='utf-8'))['features']
    out = []
    for f in fs:
        p, g = f['properties'], f['geometry']
        polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
        rings = [ring for poly in polys for ring in poly]
        xs = [x for ring in rings for x, _ in ring]; ys = [y for ring in rings for _, y in ring]
        outer = max((poly[0] for poly in polys), key=len)
        out.append(dict(cd=str(p['adm_cd2'])[:8], name=p['adm_nm'].split()[-1], gu=p['sggnm'], rings=rings,
                        bbox=(min(xs), min(ys), max(xs), max(ys)),
                        lat=sum(y for _, y in outer) / len(outer), lon=sum(x for x, _ in outer) / len(outer)))
    return out

def find_dong(dongs, lat, lon):
    for dn in dongs:
        x0, y0, x1, y1 = dn['bbox']
        if x0 <= lon <= x1 and y0 <= lat <= y1 and geo.point_in_rings(lon, lat, dn['rings']): return dn['cd']
    return None

def simplify(ring, tol=0.00015):   # 약 15m보다 가까운 점은 버린다
    out = []
    for x, y in ring:
        if out and abs(x - out[-1][0]) < tol and abs(y - out[-1][1]) < tol: continue
        out.append([round(x, 5), round(y, 5)])
    if len(out) >= 3 and out[0] != out[-1]: out.append(out[0])
    return out if len(out) >= 4 else None

if __name__ == '__main__':
    dongs = load_dongs()
    areas = load_areas(); idx = grid_index(areas)
    # ---- 민박
    stays, seen = [], set()
    for gu in SEOUL:
        for slug, kind in SLUGS:
            p = f'{RAW}/{gu}/{slug}.csv'
            if not os.path.exists(p): raise SystemExit(f'{p} 없음 → fetch_stay.py 먼저')
            for r in csv.DictReader(open(p, encoding='cp949', errors='replace')):
                o = d(r['인허가일자'])
                if not o: continue
                status = (r['영업상태명'] or '').strip()
                live = status.startswith(('영업', '휴업'))
                c = None if live else d(r.get('폐업일자')) or d(r.get('인허가취소일자'))
                if not live and (not c or c < o): continue
                jib, road = (r['지번주소'] or '').strip(), (r['도로명주소'] or '').strip()
                a = jib or road
                if a and re.search(r'\S+[구시]\s', a) and gu not in a: continue
                sid = f"{gu}:{kind}:{r['관리번호'].strip()}"
                if sid in seen: continue
                seen.add(sid)
                lat = lon = area = dcd = None
                try:
                    lat, lon = geo.localdata_to_latlon(float(r['좌표정보(X)']), float(r['좌표정보(Y)']), '5174')
                    X, Y = geo.latlon_to_5181(lat, lon)
                    area = find_area(areas, idx, X, Y); dcd = find_dong(dongs, lat, lon)
                except (ValueError, TypeError): pass
                rooms, guests = rooms_of(r)
                sz = (r.get('시설면적') or r.get('시설규모') or '').strip()
                stays.append(dict(id=sid, gu=gu, kind=kind, name=(r['사업장명'] or '').strip(), open=o, close=c,
                                  status=(r.get('상세영업상태명') or status).strip(), road=road_short(road), jkey=jkey(jib),
                                  lat=lat, lon=lon, rooms=rooms, guests=guests, bld=bld_kind(r.get('건물용도명')),
                                  size=float(sz) if re.match(r'^[0-9.]+$', sz) and 0 < float(sz) < 2000 else None,
                                  area=area, dong=dcd, life=(c - o).days if c else None))
    with open(f'{OUT}/stay.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        for s in stays:
            w.writerow([s['id'], s['gu'], s['kind'], s['name'], s['open'], s['close'] or '', s['status'], s['road'], s['jkey'] or '',
                        f"{s['lat']:.6f}" if s['lat'] else '', f"{s['lon']:.6f}" if s['lon'] else '', s['rooms'] or '', s['guests'] or '',
                        s['bld'], s['size'] or '', s['area'] or '', s['dong'] or '', s['life'] if s['life'] is not None else ''])
    # ---- 호텔·모텔 등 숙박업 객실(같은 외국인 수요를 나눠 갖는 공급). 위생 인허가(숙박업)를 먼저, 같은 지번에 없는 관광숙박업만 더함
    hotel = collections.Counter(); hotel_n = collections.Counter()
    for gu in SEOUL:
        keys = set()
        for slug in ('lodgings', 'tourist_accommodations'):
            for r in csv.DictReader(open(f'{RAW}/{gu}/{slug}.csv', encoding='cp949', errors='replace')):
                if not (r['영업상태명'] or '').startswith(('영업', '휴업')): continue
                jk = jkey((r['지번주소'] or '').strip())
                if slug == 'tourist_accommodations' and jk and jk in keys: continue
                if jk: keys.add(jk)
                n = sum(int(v) for v in (r.get('양실수'), r.get('한실수'), r.get('객실수')) if (v or '').strip().isdigit())
                try: lat, lon = geo.localdata_to_latlon(float(r['좌표정보(X)']), float(r['좌표정보(Y)']), '5174')
                except (ValueError, TypeError): continue
                cd = find_dong(dongs, lat, lon)
                if cd: hotel[cd] += min(max(n, 1), 3000); hotel_n[cd] += 1
    # ---- 외국인 생활인구(밤·낮 평균)
    files = sorted(glob.glob(f'{RAW}/spop/*.json'))
    if len(files) < 14: raise SystemExit('외국인 생활인구가 14일보다 적음 → fetch_stay.py')
    acc = collections.defaultdict(lambda: [0.0, 0, 0.0, 0])
    for f in files:
        for h, cd, v in json.load(open(f)):
            a = acc[cd]
            if h in NIGHT: a[0] += float(v); a[1] += 1
            elif h in DAY: a[2] += float(v); a[3] += 1
    pop = {cd: (a[0] / a[1] if a[1] else None, a[2] / a[3] if a[3] else None) for cd, a in acc.items()}
    # ---- 동별 집계
    by = collections.defaultdict(list)
    for s in stays:
        if s['dong']: by[s['dong']].append(s)
    y1, y2 = TODAY - dt.timedelta(days=365), TODAY - dt.timedelta(days=730)
    rows = []
    for dn in dongs:
        ss = by.get(dn['cd'], [])
        live = [s for s in ss if not s['close']]
        surv = {}
        for y in (1, 2, 3):
            el = [s for s in ss if s['open'] >= KEEP_FROM and s['open'] + dt.timedelta(days=365 * y) <= TODAY]
            surv[y] = (len(el), sum(1 for s in el if not s['close'] or s['close'] > s['open'] + dt.timedelta(days=365 * y)))
        night, day = pop.get(dn['cd'], (None, None))
        rooms = sum(s['rooms'] or 1 for s in live)
        bmix = collections.Counter(s['bld'] for s in live if s['bld'])
        geom = [g for g in (simplify(r) for r in dn['rings']) if g]
        rows.append(dict(cd=dn['cd'], name=dn['name'], gu=dn['gu'], lat=round(dn['lat'], 5), lon=round(dn['lon'], 5), geom=geom,
                         n_open=len(live), rooms=rooms, hotel=hotel[dn['cd']], hotel_n=hotel_n[dn['cd']], hanok=sum(1 for s in live if s['kind'] == '한옥체험'),
                         new1=sum(1 for s in ss if s['open'] > y1), new0=sum(1 for s in ss if y2 < s['open'] <= y1),
                         close1=sum(1 for s in ss if s['close'] and s['close'] > y1),
                         o1=surv[1][0], s1=surv[1][1], o2=surv[2][0], s2=surv[2][1], o3=surv[3][0], s3=surv[3][1],
                         night=round(night, 1) if night is not None else None, day=round(day, 1) if day is not None else None,
                         per_room=round(night / (rooms + hotel[dn['cd']] + K_ROOMS), 2) if night is not None and night >= MIN_NIGHT else None,
                         bmix=dict(bmix.most_common())))
    ranked = sorted(r['per_room'] for r in rows if r['per_room'] is not None)
    for r in rows:   # 백분위: 1에 가까울수록 객실 하나당 밤 외국인이 많음(공급 대비 수요가 큼)
        r['pct'] = round(sum(1 for v in ranked if v < r['per_room']) / max(len(ranked) - 1, 1), 3) if r['per_room'] is not None else None
        nights = sorted(x['night'] for x in rows if x['night'] is not None)
        r['night_pct'] = round(sum(1 for v in nights if v < r['night']) / max(len(nights) - 1, 1), 3) if r['night'] is not None else None
    cols = ['cd', 'name', 'gu', 'lat', 'lon', 'geom', 'n_open', 'rooms', 'hotel', 'hotel_n', 'hanok', 'new1', 'new0', 'close1', 'o1', 's1', 'o2', 's2', 'o3', 's3',
            'night', 'day', 'per_room', 'pct', 'night_pct', 'bmix']
    with open(f'{OUT}/dong.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        for r in rows:
            w.writerow([json.dumps(r[c], ensure_ascii=False, separators=(',', ':')) if c in ('geom', 'bmix') else ('' if r[c] is None else r[c]) for c in cols])
    live = [s for s in stays if not s['close']]
    meta = dict(built=str(TODAY), spop_from=os.path.basename(files[0])[:8], spop_to=os.path.basename(files[-1])[:8], spop_days=len(files),
                n=len(stays), n_open=len(live), rooms_open=sum(s['rooms'] or 1 for s in live),
                night_seoul=round(sum(p[0] for p in pop.values() if p[0]), 0), no_dong=sum(1 for s in stays if not s['dong']))
    json.dump(meta, open(f'{OUT}/stay_meta.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"민박 {len(stays):,}곳(영업 {len(live):,}) · 행정동 {len(rows)} · 동 못 찾음 {meta['no_dong']} · 외국인 {meta['spop_from']}~{meta['spop_to']}", flush=True)
