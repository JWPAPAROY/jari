"""원자료 내려받기 → data/raw/

- LOCALDATA 인허가 (서울 25개 구, 음식점·카페 + 미용·의원·약국·PC방 등 가게형 업종)  data/raw/<구>/<slug>.csv
- 서울시 상권 영역 shapefile (OA-15560)            data/raw/relm.zip
사용: python -I pipeline/fetch.py [구 이름 ...]   (생략 시 25개 구 전체)
"""
import os, sys, time, zipfile, io, urllib.request, urllib.parse
sys.stdout.reconfigure(encoding='utf-8')

SEOUL = {'종로구': '3000000', '중구': '3010000', '용산구': '3020000', '성동구': '3030000', '광진구': '3040000',
         '동대문구': '3050000', '중랑구': '3060000', '성북구': '3070000', '강북구': '3080000', '도봉구': '3090000',
         '노원구': '3100000', '은평구': '3110000', '서대문구': '3120000', '마포구': '3130000', '양천구': '3140000',
         '강서구': '3150000', '구로구': '3160000', '금천구': '3170000', '영등포구': '3180000', '동작구': '3190000',
         '관악구': '3200000', '서초구': '3210000', '강남구': '3220000', '송파구': '3230000', '강동구': '3240000'}
# build.py SOURCES와 같은 목록
SLUGS = ('general_restaurants', 'rest_cafes', 'bakeries', 'beauty_salons', 'barber_shops', 'laundries',
         'pharmacies', 'clinics', 'optical_shops', 'animal_hospitals', 'pet_grooming',
         'karaoke_rooms', 'pc_bangs', 'billiard_halls', 'fitness_centers', 'martial_arts_dojo', 'tobacco_retailers')
RAW = 'data/raw'
UA = 'Mozilla/5.0 (jari data pipeline)'

def get(url, data=None, referer=None, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={'User-Agent': UA, **({'Referer': referer} if referer else {})})
            return urllib.request.urlopen(req, timeout=300).read()
        except Exception as e:
            err = e; time.sleep(5 * (i + 1))
    raise RuntimeError(f'{url} 실패: {err}')

def localdata(gu):
    os.makedirs(f'{RAW}/{gu}', exist_ok=True)
    for slug in SLUGS:
        out = f'{RAW}/{gu}/{slug}.csv'
        b = get(f'https://file.localdata.go.kr/file/download/{slug}/info?orgCode={SEOUL[gu]}', referer='https://www.localdata.go.kr/')
        if b[:2] == b'PK':   # 압축으로 올 때
            z = zipfile.ZipFile(io.BytesIO(b)); b = z.read(z.namelist()[0])
        if len(b) < 1000 or b'<html' in b[:500].lower():
            raise RuntimeError(f'{gu} {slug}: CSV가 아님 ({len(b)} bytes)')
        open(out + '.tmp', 'wb').write(b); os.replace(out + '.tmp', out)
        print(f'{gu} {slug} {len(b) / 1e6:.1f}MB', flush=True)

def relm():
    out = f'{RAW}/relm.zip'
    body = urllib.parse.urlencode({'infId': 'OA-15560', 'seqNo': '', 'seq': '5', 'infSeq': '3'}).encode()
    b = get('https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false', data=body,
            referer='https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do')
    if b[:2] != b'PK': raise RuntimeError('상권 영역: zip이 아님')
    open(out, 'wb').write(b); print(f'상권 영역 {len(b) / 1e6:.1f}MB', flush=True)

if __name__ == '__main__':
    gus = sys.argv[1:] or list(SEOUL)
    os.makedirs(RAW, exist_ok=True)
    relm()
    for g in gus:
        localdata(g)
