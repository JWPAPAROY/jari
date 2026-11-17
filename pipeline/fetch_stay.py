"""민박(외국인관광 도시민박업·한옥체험업) 원자료 → data/raw/

- LOCALDATA 인허가 4종, 서울 25개 구        data/raw/<구>/foreigner_city_homestays.csv, hanok_experience.csv, lodgings.csv, tourist_accommodations.csv
- 행정동 경계(vuski/admdongkor, 통계청·행안부 경계 가공본)   data/raw/dong/hjd.geojson
- 서울시 단기체류 외국인 생활인구(행정동·시간대), 자료가 있는 마지막 28일   data/raw/spop/<날짜>.json
사용: python -I pipeline/fetch_stay.py
"""
import os, sys, json, datetime as dt, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))
from fetch import SEOUL, RAW, get

STAY_SLUGS = ('foreigner_city_homestays', 'hanok_experience', 'lodgings', 'tourist_accommodations')   # 뒤 둘 = 호텔·모텔 등(수요를 나눠 갖는 공급)
HJD = 'https://raw.githubusercontent.com/vuski/admdongkor/master/ver20261001/HangJeongDong_ver20261001.geojson'
DAYS = 28

def localdata():
    import zipfile, io
    for gu, org in SEOUL.items():
        os.makedirs(f'{RAW}/{gu}', exist_ok=True)
        for slug in STAY_SLUGS:
            b = get(f'https://file.localdata.go.kr/file/download/{slug}/info?orgCode={org}', referer='https://www.localdata.go.kr/')
            if b[:2] == b'PK':
                z = zipfile.ZipFile(io.BytesIO(b)); b = z.read(z.namelist()[0])
            if b'<html' in b[:500].lower(): raise RuntimeError(f'{gu} {slug}: CSV가 아님')
            out = f'{RAW}/{gu}/{slug}.csv'
            open(out + '.tmp', 'wb').write(b); os.replace(out + '.tmp', out)
    print('민박·숙박 인허가 받음', flush=True)

def dong():
    os.makedirs(f'{RAW}/dong', exist_ok=True)
    out = f'{RAW}/dong/hjd.geojson'
    if os.path.exists(out) and os.path.getsize(out) > 1e5: return
    b = get(HJD)
    d = json.loads(b.decode('utf-8'))
    d['features'] = [f for f in d['features'] if str(f['properties'].get('adm_cd2', '')).startswith('11')]
    if len(d['features']) < 400: raise RuntimeError('행정동 경계: 서울 행정동이 너무 적음')
    json.dump(d, open(out + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False); os.replace(out + '.tmp', out)
    print(f"행정동 경계 {len(d['features'])}곳", flush=True)

def spop():
    key = os.environ.get('SEOUL_API_KEY') or open(os.path.expanduser('~/.secrets/seoul-openapi-key.txt')).read().strip()
    os.makedirs(f'{RAW}/spop', exist_ok=True)
    def day(ds, a, b):
        u = f'http://openapi.seoul.go.kr:8088/{key}/json/SPOP_FORN_TEMP_RESD_DONG/{a}/{b}/{ds}'
        d = json.loads(get(u).decode('utf-8')).get('SPOP_FORN_TEMP_RESD_DONG') or {}
        return d.get('list_total_count') or 0, d.get('row') or []
    # 자료는 몇 달 늦게 올라옴: 오늘부터 거슬러 올라가며 마지막 날을 찾는다
    d0 = dt.date.today()
    for _ in range(400):
        if day(d0.strftime('%Y%m%d'), 1, 1)[0]: break
        d0 -= dt.timedelta(days=1 if d0.day <= 3 else d0.day - 1)   # 달 단위로 빠르게, 첫날 근처는 하루씩
    else: raise RuntimeError('외국인 생활인구: 자료가 있는 날을 못 찾음')
    while day((d0 + dt.timedelta(days=1)).strftime('%Y%m%d'), 1, 1)[0]: d0 += dt.timedelta(days=1)
    got = 0
    for i in range(DAYS):
        ds = (d0 - dt.timedelta(days=i)).strftime('%Y%m%d')
        out = f'{RAW}/spop/{ds}.json'
        if os.path.exists(out): got += 1; continue
        n, rows = day(ds, 1, 1000)
        for a in range(1001, n + 1, 1000): rows += day(ds, a, min(a + 999, n))[1]
        if n < 9000 or len(rows) < n: print(f'{ds}: {len(rows)}/{n}행, 건너뜀', flush=True); continue
        json.dump([[r['TMZON_PD_SE'], r['ADSTRD_CODE_SE'], r['TOT_LVPOP_CO']] for r in rows], open(out, 'w')); got += 1
    for f in os.listdir(f'{RAW}/spop'):   # 28일 창 밖의 옛 파일은 지운다
        if f < (d0 - dt.timedelta(days=DAYS - 1)).strftime('%Y%m%d'): os.remove(f'{RAW}/spop/{f}')
    print(f'외국인 생활인구 {got}일 (~{d0})', flush=True)

if __name__ == '__main__':
    dong(); spop(); localdata()
