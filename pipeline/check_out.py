"""적재 전 검사: data/out CSV가 DB 칸과 맞는지, 업종 이름이 화면 선택지에 다 있는지. 하나라도 어긋나면 종료 코드 1.
사용: python -I pipeline/check_out.py
"""
import csv, re, sys, collections
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'pipeline')
from build import road_short

bad = []
def check(cond, msg):
    if not cond: bad.append(msg)

# 1) 칸 수 (load.sh의 insert 목록과 같아야 함)
for name, n in (('license', 20), ('cohort', 10)):
    widths = collections.Counter(len(r) for r in csv.reader(open(f'data/out/{name}.csv', encoding='utf-8')))
    check(set(widths) == {n}, f'{name}.csv 칸 수 {dict(widths)} (기대 {n})')

lic = list(csv.reader(open('data/out/license.csv', encoding='utf-8')))
# 2) 관리번호 중복 없음
dup = [k for k, v in collections.Counter(r[0] for r in lic).items() if v > 1]
check(not dup, f'license 관리번호 중복 {len(dup)}건 (예: {dup[:3]})')
# 3) 숫자·날짜 칸 모양
for r in lic[:50000]:
    if r[12] and not re.fullmatch(r'[0-9.]+', r[12]): bad.append(f'면적 칸이 숫자가 아님: {r[:4]} {r[12]!r}'); break
    if not re.fullmatch(r'\d{4}-\d\d-\d\d', r[6]): bad.append(f'개업일 형식: {r[:4]} {r[6]!r}'); break
    if r[14] not in ('t', 'f') or r[19] not in ('t', 'f'): bad.append(f'참/거짓 칸: {r[:4]}'); break
# 4) 업종 이름이 화면 선택지에 있는지
page = open('docs/index.html', encoding='utf-8').read()
sel = re.search(r'<select id="svc".*?</select>', page, re.S).group(0)
opts = set(re.findall(r'<option(?: value="([^"]*)")?>([^<]*)</option>', sel))
opts = {v or t for v, t in opts}
svcs = collections.Counter(r[5] for r in lic if r[5])
missing = {s: n for s, n in svcs.items() if s not in opts}
check(not missing, f'화면 선택지에 없는 업종: {missing}')
# 5) 도로명 줄이기
for src, want in (('서울특별시 마포구 월드컵북로2길 31 (동교동,1층)', '서울특별시 마포구 월드컵북로2길 31'),
                  ('서울특별시 중구 세종대로 110, 2층 201호 (태평로1가)', '서울특별시 중구 세종대로 110')):
    check(road_short(src) == want, f'road_short({src!r}) = {road_short(src)!r}')
# 6) 행 수가 너무 적지 않은지(받다 만 원자료)
gus = collections.Counter(r[1] for r in lic)
small = {g: n for g, n in gus.items() if n < 5000}
check(not small, f'가게 기록이 너무 적은 구: {small}')

if bad:
    print('검사 실패:'); [print(' -', b) for b in bad]; sys.exit(1)
print(f'검사 통과: license {len(lic):,}행, 구 {len(gus)}, 업종 {len(svcs)}')
