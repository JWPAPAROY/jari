"""서울시 학원·교습소(neisAcademyInfo) → data/out/academy.csv, data/out/geo_new.csv

- 지금 등록된 곳만 오므로 폐원은 load_academy.sh가 주간 비교로 기록한다.
- 좌표: 도로명주소를 브이월드 지오코더로. 이미 DB geo_cache에 있는 주소는 건너뜀(인자로 캐시 CSV 경로).
- 상권: build.py와 같은 상권 영역(data/raw/relm.zip)으로 점-다각형 판정.
사용: SEOUL_API_KEY=... VWORLD_KEY=... python -I pipeline/fetch_academy.py data/tmp/geo_cache.csv
"""
import os, sys, csv, json, time, urllib.request, urllib.parse, datetime as dt
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
import geo, build

def key(env, path):
    if os.environ.get(env): return os.environ[env]
    p = os.path.expanduser(path)
    return open(p).read().strip() if os.path.exists(p) else ''
SEOUL = key('SEOUL_API_KEY', '~/.secrets/seoul-openapi-key.txt')
VW = key('VWORLD_KEY', '~/.secrets/vworld-key.txt')   # 없으면 좌표 캐시에 있는 주소만 좌표를 붙임
OUT = 'data/out'
MAX_GEO = 30000   # 브이월드 하루 4만 건 한도 안에서

def get_json(url, tries=4):
    for i in range(tries):
        try: return json.loads(urllib.request.urlopen(url, timeout=60).read().decode('utf-8'))
        except Exception as e: err = e; time.sleep(3 * (i + 1))
    raise RuntimeError(f'{url[:80]}: {err}')

def academies():
    first = get_json(f'http://openapi.seoul.go.kr:8088/{SEOUL}/json/neisAcademyInfo/1/1000/')['neisAcademyInfo']
    n, rows = first['list_total_count'], list(first['row'])
    for a in range(1001, n + 1, 1000):
        rows += get_json(f'http://openapi.seoul.go.kr:8088/{SEOUL}/json/neisAcademyInfo/{a}/{a + 999}/')['neisAcademyInfo']['row']
    if len(rows) != n: raise RuntimeError(f'학원 {len(rows)}/{n}건만 받음')
    return rows

def geocode(addr):
    q = urllib.parse.urlencode({'service': 'address', 'request': 'getcoord', 'version': '2.0', 'crs': 'epsg:4326', 'address': addr,
                                'refine': 'true', 'simple': 'true', 'format': 'json', 'type': 'road', 'key': VW, 'domain': 'https://jwpaparoy.github.io'})
    d = get_json('https://api.vworld.kr/req/address?' + q)['response']
    if d.get('status') != 'OK': return None
    p = d['result']['point']; return float(p['y']), float(p['x'])

def ymd(s):
    s = (s or '').strip()
    try: return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8])).isoformat() if len(s) == 8 and s[:4] < '2100' else ''
    except ValueError: return ''

if __name__ == '__main__':
    cache = {}
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        for r in csv.reader(open(sys.argv[1], encoding='utf-8')):
            if len(r) >= 3 and r[1]: cache[r[0]] = (float(r[1]), float(r[2]))
    rows = academies()
    print(f'학원·교습소 {len(rows):,}곳, 좌표 캐시 {len(cache):,}', flush=True)
    areas = build.load_areas(); idx = build.grid_index(areas)
    new, miss, calls, fails = {}, 0, 0, 0
    os.makedirs(OUT, exist_ok=True)
    with open(f'{OUT}/academy.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        for r in rows:
            addr = (r.get('ROAD_NM_ADDR') or '').strip()
            ll = cache.get(addr) or new.get(addr)
            if not ll and addr and VW and calls < MAX_GEO and fails < 5:
                calls += 1
                try: ll = geocode(addr); fails = 0
                except RuntimeError as e:   # 브이월드가 잠깐 막혀도 학원 목록은 갱신(좌표만 다음 주로 미룸)
                    ll = None; fails += 1
                    if fails == 5: print(f'브이월드 연속 실패로 이번엔 새 좌표를 그만 받음: {e}', flush=True)
                time.sleep(0.05)
                if ll: new[addr] = ll
            area = ''
            if ll:
                X, Y = geo.latlon_to_5181(*ll); area = build.find_area(areas, idx, X, Y) or ''
            else: miss += 1
            w.writerow([r['PEI_DSGN_NO'].strip(), (r.get('PEI_TRNG_NM') or '').strip(), (r.get('PEI_NM') or '').strip(),
                        (r.get('FLD_NM') or '').strip(), (r.get('TRNG_CRS_NM') or '').strip(), (r.get('ADMDST_NM') or '').strip(),
                        build.road_short(addr), ymd(r.get('REG_YMD')), ll[0] if ll else '', ll[1] if ll else '', area])
    with open(f'{OUT}/geo_new.csv', 'w', encoding='utf-8', newline='') as fh:
        csv.writer(fh).writerows([a, la, lo] for a, (la, lo) in new.items())
    print(f'지오코딩 호출 {calls:,}, 새 좌표 {len(new):,}, 좌표 없음 {miss:,}', flush=True)
