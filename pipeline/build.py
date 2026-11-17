"""원자료 → DB 적재용 CSV (data/out/)

license.csv  인허가 전체(2016년 이후 영업한 기록, 음식점·카페 + 가게형 업종 SOURCES)
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

# 업종 분류: 업태가 분명하면 업태로, 애매하면(기타·호프/통닭·일반조리판매·백화점 등) 상호명 키워드로.
# 편의점·출장조리·푸드트럭·키즈카페처럼 '가게 자리' 비교에 맞지 않는 업태는 None(통계 제외).
KW = [  # 순서가 우선순위
    ('치킨', r'치킨|통닭|닭강정|교촌|굽네|BBQ|비비큐|bhc|BHC|네네|페리카나|처갓집|호식이|푸라닭|자담|멕시카나|노랑|가마로|또래오래|깐부|순살'),
    ('패스트푸드', r'버거|맥도날드|롯데리아|KFC|맘스터치|서브웨이|피자|도미노|파파존스|토스트|핫도그|타코야끼'),
    ('제과', r'베이커리|빵|제과|케이크|케익|도넛|도너츠|마카롱|아이스크림|배스킨|베스킨|와플|크로플|젤라또|빙수|설빙|떡집|디저트'),
    ('호프·주점', r'호프|포차|포장마차|주점|술집|이자카야|맥주|비어|펍|PUB|Pub|pub|와인|막걸리|노가리|소주|선술집|BAR|Bar|[가-힣]바$|칵테일|하이볼|위스키|요리주점|꼬치|야끼토리|kitchen bar'),
    ('커피·음료', r'커피|카페|까페|cafe|Cafe|CAFE|coffee|Coffee|COFFEE|스타벅스|이디야|투썸|메가엠지씨|컴포즈|빽다방|공차|쥬스|주스|버블티|티하우스|찻집|다방|로스터'),
    ('분식', r'분식|떡볶이|떡볶기|김밥|순대|라면|만두|어묵|오뎅|도시락|컵밥|주먹밥|호떡|핫바'),
    ('일식', r'스시|초밥|라멘|돈까스|돈가스|돈카츠|우동|소바|오마카세|사케|덮밥|규동|텐동|일식'),
    ('중식', r'짜장|자장|짬뽕|마라|반점|중화|훠궈|양꼬치|딤섬|중국'),
    ('양식', r'파스타|스테이크|비스트로|브런치|타코|쌀국수|태국|타이|베트남|인도|커리|카레|멕시칸|이탈리|프렌치|샐러드|포케|그릴|화덕|키친|다이닝|오스테리아|트라토리아|뇨끼|리조또'),
    ('한식', r'국밥|고기|삼겹|갈비|곱창|막창|족발|보쌈|찌개|해장|백반|칼국수|냉면|감자탕|횟집|수산|회센터|닭갈비|막국수|한우|정육|식당|한식|생선|아구|추어탕|설렁탕|곰탕|해물|낙지|쭈꾸미|쌈밥|부대|찜닭|닭한마리|국수|죽|반찬|비빔밥|두부|전집|한정식|숯불|대패|닭발|밥집|된장|샤브|순두부|보리밥|장어|오리|순대국|육회|불고기|전골'),
]
KW = [(n, re.compile(p)) for n, p in KW]
EXCLUDE = ('편의점', '출장조리', '푸드트럭', '키즈카페', '식품소분', '룸살롱', '유원지', '고속도로', '공항', '극장', '관광호텔', '철도역')
CLEAR = {'한식': '한식', '식육(숯불구이)': '한식', '탕류(보신용)': '한식', '냉면집': '한식', '횟집': '한식', '복어취급': '한식',
         '중국식': '중식', '일식': '일식', '경양식': '양식', '외국음식전문점(인도,태국등)': '양식', '뷔페식': '양식', '패밀리레스트랑': '양식',
         '분식': '분식', '김밥(도시락)': '분식', '패스트푸드': '패스트푸드', '통닭(치킨)': '치킨',
         '정종/대포집/소주방': '호프·주점', '감성주점': '호프·주점', '라이브카페': '호프·주점',
         '커피숍': '커피·음료', '까페': '커피·음료', '다방': '커피·음료', '전통찻집': '커피·음료', '떡카페': '커피·음료', '아이스크림': '제과'}

def by_name(name):
    for n, p in KW:
        if p.search(name or ''): return n
    return None

def svc(biz, kind, name=''):
    b = (biz or '').strip()
    if any(x in b for x in EXCLUDE): return None
    if b in CLEAR: return CLEAR[b]
    hit = by_name(name)
    if b == '호프/통닭': return hit if hit and hit not in ('커피·음료', '제과') else '호프·주점'
    if hit: return hit
    if kind == '휴게' and b in ('기타 휴게음식점', ''): return '커피·음료'
    return '기타'

food_svc = lambda kind: (lambda biz, name: svc(biz, kind, name))
const = lambda v: (lambda biz, name: v)
def beauty(biz, name):
    return {'일반미용업': '미용실', '네일아트업': '네일', '피부미용업': '피부관리', '메이크업업': '메이크업'}.get(biz)
def laundry(biz, name):
    return '빨래방' if '빨래방' in biz or re.search(r'빨래방|코인', name) else '세탁소'
def clinic(biz, name):
    return {'의원': '의원', '치과의원': '치과', '한의원': '한의원'}.get(biz)
CVS = re.compile(r'지에스|GS ?25|LG25|세븐일레븐|코리아세븐|7-?ELEVEN|씨유|^CU|\bCU\b|비지에프|BGF|이마트 ?24|emart24|위드미|미니스톱|스토리웨이', re.I)
def tobacco(biz, name):   # 담배소매 인허가로 편의점·슈퍼·전자담배 가게를 본다(그 밖의 가판·문구점 등은 제외)
    if CVS.search(name): return '편의점'
    if re.search(r'전자담배|베이프|vape|전담', name, re.I): return '전자담배'
    if re.search(r'마트|슈퍼|mart', name, re.I): return '슈퍼마켓'
    return None

# (LOCALDATA slug, 종류, 업종 분류 함수). 업종 이름은 화면 선택지와 같아야 함
SOURCES = [
    ('general_restaurants', '음식점', food_svc('음식점')), ('rest_cafes', '휴게', food_svc('휴게')),
    ('bakeries', '제과점', const('제과')),
    ('beauty_salons', '미용업', beauty), ('barber_shops', '이용업', const('이발소')), ('laundries', '세탁업', laundry),
    ('pharmacies', '약국', const('약국')), ('clinics', '의원', clinic), ('optical_shops', '안경업', const('안경점')),
    ('animal_hospitals', '동물병원', const('동물병원')), ('pet_grooming', '동물미용업', const('반려동물미용')),
    ('karaoke_rooms', '노래연습장', const('노래방')), ('pc_bangs', 'PC방', const('PC방')),
    ('billiard_halls', '당구장', const('당구장')), ('fitness_centers', '체력단련장', const('헬스장')),
    ('martial_arts_dojo', '체육도장', const('체육도장')), ('tobacco_retailers', '담배소매', tobacco),
]
FOOD_KINDS = {'음식점', '휴게', '제과점'}
SIZE_COLS = ('소재지면적', '약국영업면적', '시설면적', '총면적')   # 업종마다 이름이 다름(건축물연면적은 건물 전체라 안 씀)
LIVE = ('영업', '휴업')   # 그 밖의 상태(취소·말소·제외 등)는 폐업일자가 있으면 그날 닫은 것으로, 없으면 뺀다

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

def road_short(road):   # '서울특별시 마포구 월드컵북로2길 31, 2층 (동교동)' → '서울특별시 마포구 월드컵북로2길 31'
    m = re.match(r'(.+?(?:로|길)\s*\d+(?:-\d+)?)(?=[\s,(]|$)', road or '')
    return m.group(1) if m else (road or '').split(',')[0].split(' (')[0].strip()

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

def ring_latlon(ring, tol=12.0):
    out, last = [], None
    for x, y in ring:
        if last and abs(x - last[0]) < tol and abs(y - last[1]) < tol: continue
        lat, lon = geo.tm_inverse(x, y, geo.GRS80, 127.0)
        out.append([round(lon, 5), round(lat, 5)]); last = (x, y)
    if len(out) >= 3 and out[0] != out[-1]: out.append(out[0])
    return out

# ---------- 구별 처리
SEEN_ALL = set()   # 서울 전체 관리번호(구 사이 중복 방지)
# 관리번호가 구마다 따로 매겨지는 업종(강남·마포에 같은 번호의 다른 가게가 수백 개) → 구 이름을 붙여 구분
GU_LOCAL_ID = {'karaoke_rooms', 'pc_bangs', 'billiard_halls', 'fitness_centers', 'martial_arts_dojo'}
def process_gu(gu, areas, idx, wl, wc):
    stores = []
    for slug, kind, svcf in SOURCES:
        for r in csv.DictReader(open(f'{RAW}/{gu}/{slug}.csv', encoding='cp949', errors='replace')):
            o = d(r['인허가일자'])
            if not o: continue
            status = (r['영업상태명'] or '').strip()
            c = None if status.startswith(LIVE) else d(r.get('폐업일자'))
            if not c and not status.startswith(LIVE): continue
            if c and c < KEEP_FROM: continue
            if c and c < o: continue
            lat = lon = area = None
            try:
                x, y = float(r['좌표정보(X)']), float(r['좌표정보(Y)'])
                lat, lon = geo.localdata_to_latlon(x, y, '5174')
                X, Y = geo.latlon_to_5181(lat, lon)
                area = find_area(areas, idx, X, Y)
            except (ValueError, TypeError):
                pass
            sz = next((r[k].strip() for k in SIZE_COLS if (r.get(k) or '').strip()), '')
            name = (r['사업장명'] or '').strip()
            biz = (r.get('업태구분명') or '').strip()
            jib, road = (r['지번주소'] or '').strip(), (r['도로명주소'] or '').strip()
            mid = r['관리번호'].strip()
            if slug in GU_LOCAL_ID: mid = f'{gu}:{mid}'
            stores.append(dict(id=mid, gu=gu, kind=kind, name=name, biz=biz or kind,
                               svc=svcf(biz, name), open=o, close=c, status=status, jibun=jib, road=road,
                               jkey=jkey(jib), size=float(sz) if re.match(r'^[0-9.]+$', sz) and float(sz) > 0 else None,
                               floor=floor_of(road, jib), chain=is_chain(name), lat=lat, lon=lon, area=area))
    seen = {}; uniq = []; clash = other = dup = 0
    for s in stores:
        if s['id'] in seen:
            clash += seen[s['id']] != s['kind']; continue
        # 주소가 다른 지역(다른 구·다른 시)인 기록은 뺀다. 그래도 구 사이에 번호가 겹치면 먼저 본 구가 가짐
        a = s['jibun'] or s['road']
        if a and re.search(r'\S+[구시]\s', a) and gu not in a:
            other += 1; continue
        if s['id'] in SEEN_ALL:
            dup += 1; continue
        seen[s['id']] = s['kind']; uniq.append(s)
    stores = uniq; SEEN_ALL.update(seen)
    if clash: print(f'  경고: 서로 다른 종류에서 같은 관리번호 {clash}건(뒤쪽 버림)', flush=True)
    if other or dup: print(f'  다른 지역 주소 {other}건 · 다른 구와 번호 중복 {dup}건 제외', flush=True)
    for s in stores: s['food'] = s['kind'] in FOOD_KINDS

    by_name = collections.defaultdict(list); by_jibun = collections.defaultdict(list)
    for s in stores:
        by_name[(s['jibun'], s['name'])].append(s); by_jibun[s['jibun']].append(s)
    def continued(s):   # 같은 자리·같은 상호가 60일 안에 다시 열림 = 명의변경(영업이 이어진 것)
        if not s['close']: return False
        return any(t is not s and t['open'] >= s['close'] and (t['open'] - s['close']).days <= 60
                   for t in by_name[(s['jibun'], s['name'])])
    def died(s):
        if not s['close'] or (s['close'] - s['open']).days >= HORIZON: return False
        return not continued(s)
    def spot(s):
        lo = s['open'] - dt.timedelta(days=HORIZON)
        return min(2, sum(1 for t in by_jibun[s['jibun']] if t is not s and t['food'] == s['food'] and t['close']   # 외식은 외식끼리, 나머지는 나머지끼리
                          and lo <= t['close'] <= s['open'] and t['name'] != s['name']))

    nc = 0
    for s in stores:
        wl.writerow([s['id'], gu, s['kind'], s['name'], s['biz'], s['svc'] or '', s['open'], s['close'] or '',
                     # 용량: 지번 원문은 안 씀(jkey로 대신), 도로명은 건물번호까지만
                     s['status'], '', road_short(s['road']), s['jkey'] or '', s['size'] or '', s['floor'],
                     't' if s['chain'] else 'f', s['lat'] or '', s['lon'] or '', s['area'] or '',
                     (s['close'] - s['open']).days if s['close'] and not continued(s) else '',
                     'f' if continued(s) else 't'])
        if s['svc'] and s['open'] >= KEEP_FROM and (TODAY - s['open']).days > HORIZON:
            wc.writerow([s['id'], gu, s['area'] or '', s['svc'], size_band(s['size']), s['floor'],
                         't' if s['chain'] else 'f', spot(s), 't' if died(s) else 'f', s['open']]); nc += 1
    print(f'{gu}: 인허가 {len(stores):,}  코호트 {nc:,}', flush=True)

if __name__ == '__main__':
    gus = sys.argv[1:] or sorted(n for n in os.listdir(RAW) if os.path.isdir(f'{RAW}/{n}'))
    os.makedirs(OUT, exist_ok=True)
    areas = load_areas(); idx = grid_index(areas)
    with open(f'{OUT}/area.csv', 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh); w.writerow(['code', 'name', 'kind', 'gu', 'geom', 'lat', 'lon'])
        GU_CD = {'11110': '종로구', '11140': '중구', '11170': '용산구', '11200': '성동구', '11215': '광진구', '11230': '동대문구',
                 '11260': '중랑구', '11290': '성북구', '11305': '강북구', '11320': '도봉구', '11350': '노원구', '11380': '은평구',
                 '11410': '서대문구', '11440': '마포구', '11470': '양천구', '11500': '강서구', '11530': '구로구', '11545': '금천구',
                 '11560': '영등포구', '11590': '동작구', '11620': '관악구', '11650': '서초구', '11680': '강남구', '11710': '송파구', '11740': '강동구'}
        for a in areas:
            rings = [ring_latlon(r) for r in a['rings']]
            pts = max(rings, key=len) if rings else []
            clat = sum(p[1] for p in pts) / len(pts) if pts else ''
            clon = sum(p[0] for p in pts) / len(pts) if pts else ''
            w.writerow([a['code'], a['name'], a['kind'], GU_CD.get(a['gu_cd'], a['gu_cd']),
                        json.dumps(rings, separators=(',', ':')), clat, clon])
    print('상권', len(areas), flush=True)
    with open(f'{OUT}/license.csv', 'w', encoding='utf-8', newline='') as fl, open(f'{OUT}/cohort.csv', 'w', encoding='utf-8', newline='') as fc:
        wl, wc = csv.writer(fl), csv.writer(fc)
        for g in gus:
            process_gu(g, areas, idx, wl, wc)
    json.dump({'gus': gus, 'built': TODAY.isoformat()}, open(f'{OUT}/meta.json', 'w', encoding='utf-8'), ensure_ascii=False)
