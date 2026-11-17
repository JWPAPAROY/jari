"""검색 노출용 정적 페이지: docs/a/<상권코드>.html, docs/g/<구코드>.html, docs/d/<행정동코드>.html, docs/list.html, docs/stay.html, docs/sitemap.xml

입력은 build_pages.sh가 DB에서 내보낸 data/tmp/p_*.csv. 문장은 모두 그 주 숫자로 만든다(고정 안내문 없음).
사용: bash pipeline/build_pages.sh
"""
import csv, os, sys, html, json, collections, datetime as dt
sys.stdout.reconfigure(encoding='utf-8')

BASE = 'https://jwpaparoy.github.io/jari/'
T = 'data/tmp'
DOCS = 'docs'
SB = 'https://weqtznraiderretvcwzp.supabase.co'
ANON = dict(l.strip().split('=', 1) for l in open('.env.public', encoding='utf-8') if '=' in l)['SUPABASE_ANON_KEY']
GU_CD = {'11110': '종로구', '11140': '중구', '11170': '용산구', '11200': '성동구', '11215': '광진구', '11230': '동대문구',
         '11260': '중랑구', '11290': '성북구', '11305': '강북구', '11320': '도봉구', '11350': '노원구', '11380': '은평구',
         '11410': '서대문구', '11440': '마포구', '11470': '양천구', '11500': '강서구', '11530': '구로구', '11545': '금천구',
         '11560': '영등포구', '11590': '동작구', '11620': '관악구', '11650': '서초구', '11680': '강남구', '11710': '송파구', '11740': '강동구'}
GU_CODE = {v: k for k, v in GU_CD.items()}
MIN_ROW = 10      # 업종 줄을 보여줄 3년 표본
MIN_AREA = 15     # 상권 전체 생존율을 말할 3년 표본

e = html.escape
def rd(name):
    return list(csv.DictReader(open(f'{T}/p_{name}.csv', encoding='utf-8')))
def i(x): return int(x or 0)
def pct(s, o): return f'{round(100 * s / o)}%' if o else '—'
SVL = lambda s: '외식 기타' if s == '기타' else s
def iga(word):   # 받침 있으면 '이', 없으면 '가'
    c = word[-1]
    return '이' if '가' <= c <= '힣' and (ord(c) - 0xAC00) % 28 else '가'

areas = {r['code']: r for r in rd('area')}
stats = collections.defaultdict(dict)
for r in rd('stats'): stats[r['code']][r['svc']] = r
seoul = {r['svc']: r for r in rd('seoul')}
openn = collections.defaultdict(dict)
for r in rd('open'): openn[r['code']][r['svc']] = i(r['n'])
trend = {r['code']: r for r in rd('trend')}
acad = {r['code']: r for r in rd('acad')}
built = open(f'{T}/p_built.txt', encoding='utf-8').read().strip()
rent = collections.defaultdict(dict)   # 상권 → {(종류, 분기): 행}
for r in rd('rent'): rent[r['code']][(r['kind'], int(r['q']))] = r
RQ = max((q for v in rent.values() for _, q in v), default=0)

def near(code, k=6):
    a = areas[code]
    if not a['lat']: return []
    la, lo = float(a['lat']), float(a['lon'])
    ds = sorted((((float(b['lat']) - la) * 111) ** 2 + ((float(b['lon']) - lo) * 88) ** 2, c) for c, b in areas.items() if c != code and b['lat'])
    return [c for _, c in ds[:k]]

CSS = """:root{--bg:#f3f5f6;--panel:#fff;--ink:#18232b;--muted:#5d6b75;--line:#d9e0e4;--accent:#1f5f7a;--accent-soft:#e2eef3;--safe:#2c7a4b;--risk:#b4342b;
--f-body:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;--f-num:"IBM Plex Mono",ui-monospace,Consolas,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#11181d;--panel:#182229;--ink:#e4ebef;--muted:#93a3ad;--line:#2a3842;--accent:#6fb3cf;--accent-soft:#1d3440;--safe:#6cc58f;--risk:#ec7a70;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 var(--f-body)}
header{background:var(--panel);border-bottom:1px solid var(--line);padding:12px 16px}header a{color:var(--ink);text-decoration:none;font-weight:700}
main{max-width:760px;margin:0 auto;padding:20px 16px 60px}h1{font-size:24px;line-height:1.3;margin:6px 0 4px}h2{font-size:18px;margin:28px 0 8px}
.sub{color:var(--muted);margin:0 0 16px}.num{font-family:var(--f-num);font-variant-numeric:tabular-nums}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px}
.card b{display:block;font-size:24px;font-family:var(--f-num)}.card span{color:var(--muted);font-size:13px}
.lead{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;padding:12px 14px;margin:16px 0}
.tw{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{color:var(--muted);font-weight:500}td.r,th.r{text-align:right}
tr:last-child td{border-bottom:0}.up{color:var(--safe)}.dn{color:var(--risk)}
a{color:var(--accent)}.btn{display:inline-block;background:var(--accent);color:var(--panel);padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:700;margin:8px 0}
.links{display:flex;flex-wrap:wrap;gap:6px}.links a{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:4px 10px;text-decoration:none;font-size:14px}
.wrap td,.wrap th{white-space:normal;min-width:110px}ul,ol{padding-left:22px}li{margin:4px 0}
footer{color:var(--muted);font-size:13px;margin-top:36px;border-top:1px solid var(--line);padding-top:12px}
@media (max-width:520px){h1{font-size:21px}.card b{font-size:20px}.card{padding:10px}}"""

import hashlib
CSS_V = hashlib.md5(CSS.encode()).hexdigest()[:8]   # CSS가 바뀌면 주소가 바뀌어 캐시를 피함
open(f'{DOCS}/p.css', 'w', encoding='utf-8', newline='\n').write(CSS)

SRC_SHOP = '자료: 행정안전부 LOCALDATA 인허가, 서울시 상권분석서비스(상권 영역·추정매출), 서울시 학원·교습소 정보, 한국부동산원 상업용부동산 임대동향. 생존율은 2016년 이후 문을 연 가게 중 개업 후 N년이 지난 가게가 그 시점에 영업 중이었던 비율입니다.'
def page(path, title, desc, body, kind, canon, src=SRC_SHOP):
    track = ("<script>try{var r=document.referrer,s='direct';if(r){var h=new URL(r).hostname;s=h===location.hostname?'internal':"
             "['google','naver','daum','bing'].find(function(k){return h.indexOf(k)>=0})||'other'}"
             f"fetch('{SB}/rest/v1/rpc/hit',{{method:'POST',headers:{{apikey:'{ANON}',Authorization:'Bearer {ANON}','Content-Type':'application/json'}},"
             f"body:JSON.stringify({{p_page:'{kind}',p_src:s,p_evt:'view'}}),keepalive:true}}).catch(function(){{}})}}catch(e){{}}</script>")
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{BASE}{canon}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@500;600&display=swap">
<link rel="stylesheet" href="{'../' if '/' in path else ''}p.css?v={CSS_V}"></head><body><header><a href="{'../' if '/' in path else ''}./">jari · 창업 자리 생존율 지도</a></header><main>{body}
<footer>{src} {e(built)} 기준.</footer>
</main>{track}</body></html>"""
    os.makedirs(os.path.dirname(f'{DOCS}/{path}') or DOCS, exist_ok=True)
    open(f'{DOCS}/{path}', 'w', encoding='utf-8', newline='\n').write(doc)

def svc_rows(st, base):
    rows = [r for s, r in st.items() if s != '전체' and i(r['o3']) >= MIN_ROW]
    rows.sort(key=lambda r: -i(r['s3']) / i(r['o3']))
    out = []
    for r in rows:
        sv = seoul.get(r['svc'], {}); so3, ss3 = i(sv.get('o3')), i(sv.get('s3'))
        d = (i(r['s3']) / i(r['o3']) - ss3 / so3) * 100 if so3 else None
        cmp = f'<span class="{"up" if d >= 0 else "dn"}">{"+" if d >= 0 else ""}{round(d)}%p</span>' if d is not None else '—'
        out.append(f'<tr><td>{e(SVL(r["svc"]))}</td><td class="r num">{pct(i(r["s1"]), i(r["o1"]))}</td><td class="r num">{pct(i(r["s2"]), i(r["o2"]))}</td>'
                   f'<td class="r num"><b>{pct(i(r["s3"]), i(r["o3"]))}</b></td><td class="r num">{cmp}</td><td class="r num">{i(r["o3"]):,}</td></tr>')
    return out

urls = []
sall = seoul.get('전체', {})
for code, a in areas.items():
    st = stats.get(code, {}); al = st.get('전체', {}); o3, s3 = i(al.get('o3')), i(al.get('s3'))
    name, gu, kind = a['name'], a['gu'], a['kind']
    on = sorted(openn.get(code, {}).items(), key=lambda x: -x[1]); tot = sum(n for _, n in on)
    rows = svc_rows(st, sall)
    best = rows and max((r for s, r in st.items() if s != '전체' and i(r['o3']) >= MIN_ROW), key=lambda r: i(r['s3']) / i(r['o3']))
    worst = rows and min((r for s, r in st.items() if s != '전체' and i(r['o3']) >= MIN_ROW), key=lambda r: i(r['s3']) / i(r['o3']))
    lead = []
    if o3 >= MIN_AREA and i(sall.get('o3')):
        me, sv = s3 / o3, i(sall['s3']) / i(sall['o3'])
        lead.append(f'{e(name)}에서 2016년 이후 문을 열고 3년이 지난 가게 {o3:,}곳 중 <b>{round(me * 100)}%</b>가 3년을 버텼습니다. '
                    f'서울 전체({round(sv * 100)}%)보다 {"높습니다" if me >= sv + .02 else "낮습니다" if me <= sv - .02 else "비슷합니다"}.')
    if best and worst and best is not worst:
        lead.append(f'업종별로는 <b>{e(SVL(best["svc"]))}</b>({pct(i(best["s3"]), i(best["o3"]))}){iga(SVL(best["svc"]))} 가장 오래 버텼고, '
                    f'<b>{e(SVL(worst["svc"]))}</b>({pct(i(worst["s3"]), i(worst["o3"]))}){iga(SVL(worst["svc"]))} 가장 빨리 문을 닫았습니다.')
    t = trend.get(code)
    if t and t.get('grade'):
        lead.append(f'최근 1년 외식 매출 흐름은 <b>{e(t["grade"])}</b>입니다'
                    + (f'(매출 {"+" if float(t["sales_yoy"]) >= 0 else ""}{round(float(t["sales_yoy"]) * 100)}%)' if t.get('sales_yoy') else '') + '.')
    ac = acad.get(code)
    cards = (f'<div class="cards"><div class="card"><span>1년 생존</span><b>{pct(i(al.get("s1")), i(al.get("o1")))}</b></div>'
             f'<div class="card"><span>2년 생존</span><b>{pct(i(al.get("s2")), i(al.get("o2")))}</b></div>'
             f'<div class="card"><span>3년 생존</span><b>{pct(s3, o3)}</b></div></div>')
    body = (f'<p class="sub">{e(gu)} · {e(kind)}</p><h1>{e(name)} 상권, 가게들은 몇 년 버텼나</h1>{cards}'
            + (f'<div class="lead">{" ".join(lead)}</div>' if lead else '')
            + f'<a class="btn" href="../#a={code}">지도에서 건물별로 보기</a>')
    if rows:
        body += ('<h2>업종별 생존율</h2><div class="tw"><table><thead><tr><th>업종</th><th class="r">1년</th><th class="r">2년</th><th class="r">3년</th>'
                 '<th class="r">서울 대비</th><th class="r">3년 표본</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')
    if on:
        body += f'<h2>지금 영업 중인 가게 {tot:,}곳</h2><p>' + ' · '.join(f'{e(SVL(s))} <b class="num">{n}</b>' for s, n in on[:12]) + '</p>'
    if ac and i(ac['n']):
        body += f'<h2>학원·교습소 {i(ac["n"]):,}곳</h2><p>' + e(ac['fields']) + '</p>'
    rv = rent.get(code)
    if rv and RQ:
        trs = []
        for k in ('소규모', '중대형'):
            now, prev = rv.get((k, RQ)), rv.get((k, RQ - 10))
            if not now or not now['rent']: continue
            ch = (float(now['rent']) / float(prev['rent']) - 1) * 100 if prev and prev['rent'] else None
            trs.append(f'<tr><td>{k} 상가</td><td class="r num"><b>{float(now["rent"]) * 3.3058 / 10:.1f}만원</b></td>'
                       f'<td class="r num">{"—" if ch is None else f"{ch:+.1f}%"}</td><td class="r num">{float(now["vac"]):.1f}%</td></tr>' if now['vac'] else
                       f'<tr><td>{k} 상가</td><td class="r num"><b>{float(now["rent"]) * 3.3058 / 10:.1f}만원</b></td><td class="r num">{"—" if ch is None else f"{ch:+.1f}%"}</td><td class="r num">—</td></tr>')
        if trs:
            reg = next(iter(rv.values()))['region']
            body += (f'<h2>임대료·공실률</h2><p class="sub">가까운 한국부동산원 조사 상권 <b>{e(reg)}</b> · {str(RQ)[:4]}년 {str(RQ)[4]}분기</p>'
                     '<div class="tw"><table><thead><tr><th></th><th class="r">평당 월세</th><th class="r">1년 변화</th><th class="r">공실률</th></tr></thead><tbody>'
                     + ''.join(trs) + '</tbody></table></div>')
    nb = near(code)
    if nb:
        body += '<h2>가까운 상권</h2><div class="links">' + ''.join(f'<a href="{c}.html">{e(areas[c]["name"])}</a>' for c in nb) + '</div>'
    body += f'<h2>{e(gu)} 다른 상권</h2><p><a href="../g/{GU_CODE.get(gu, "")}.html">{e(gu)} 상권 전체 보기</a> · <a href="../list.html">서울 25개 구</a></p>'
    desc = (f'{name}({gu}) 상권 가게 3년 생존율 {pct(s3, o3)}' + (f', 업종별로 {SVL(best["svc"])} {pct(i(best["s3"]), i(best["o3"]))}' if best else '')
            + f'. 2016년 이후 인허가 기록으로 본 1·2·3년 생존율과 지금 영업 중인 가게.')
    page(f'a/{code}.html', f'{name} 상권 가게 생존율·폐업률 ({gu}) | jari', desc, body, 'area', f'a/{code}.html')
    urls.append(f'a/{code}.html')

by_gu = collections.defaultdict(list)
for code, a in areas.items(): by_gu[a['gu']].append(code)
gu_rows = []
for gu, codes in sorted(by_gu.items()):
    gc = GU_CODE.get(gu);
    if not gc: continue
    rs = []
    for c in codes:
        al = stats.get(c, {}).get('전체', {})
        rs.append((i(al.get('o3')), c, al))
    rs.sort(key=lambda x: -x[0])
    tb = ''.join(f'<tr><td><a href="../a/{c}.html">{e(areas[c]["name"])}</a></td><td>{e(areas[c]["kind"])}</td>'
                 f'<td class="r num"><b>{pct(i(al.get("s3")), o)}</b></td><td class="r num">{o:,}</td></tr>' for o, c, al in rs)
    tot_o = sum(o for o, _, _ in rs); tot_s = sum(i(al.get('s3')) for _, _, al in rs)
    body = (f'<h1>{e(gu)} 상권별 가게 생존율</h1><p class="sub">상권 {len(codes):,}곳 · 3년 생존 {pct(tot_s, tot_o)} (표본 {tot_o:,}곳)</p>'
            f'<a class="btn" href="../">지도에서 보기</a><h2>상권 목록 (3년 표본 많은 순)</h2><div class="tw"><table><thead><tr><th>상권</th><th>종류</th>'
            f'<th class="r">3년 생존</th><th class="r">표본</th></tr></thead><tbody>{tb}</tbody></table></div><p><a href="../list.html">서울 25개 구</a></p>')
    page(f'g/{gc}.html', f'{gu} 상권별 가게 생존율·폐업률 | jari', f'{gu} 상권 {len(codes)}곳의 가게 3년 생존율 {pct(tot_s, tot_o)}. 상권별 1·2·3년 생존율 목록.', body, 'gu', f'g/{gc}.html')
    urls.append(f'g/{gc}.html'); gu_rows.append((gu, gc, len(codes), tot_o, tot_s))

tb = ''.join(f'<tr><td><a href="g/{gc}.html">{e(gu)}</a></td><td class="r num">{n}</td><td class="r num"><b>{pct(s, o)}</b></td><td class="r num">{o:,}</td></tr>'
             for gu, gc, n, o, s in sorted(gu_rows, key=lambda x: -x[4] / max(1, x[3])))
page('list.html', '서울 25개 구 상권별 가게 생존율 | jari', '서울 25개 구, 상권 1,650곳의 가게 1·2·3년 생존율과 업종별 차이.',
     f'<h1>서울 25개 구, 가게들은 몇 년 버텼나</h1><p class="sub">3년 생존율 높은 구부터</p><a class="btn" href="./">지도에서 보기</a>'
     f'<div class="tw"><table><thead><tr><th>구</th><th class="r">상권</th><th class="r">3년 생존</th><th class="r">표본</th></tr></thead><tbody>{tb}</tbody></table></div>',
     'list', 'list.html')
urls.append('list.html')

# ---------- 행정동 외국인 민박 페이지(민박이 있거나 밤 외국인이 100명 이상인 동만)
dongs = rd('dong'); sm = json.loads(open(f'{T}/p_stay_meta.json', encoding='utf-8').read() or '{}')
fd = lambda x: float(x) if x not in (None, '') else None
D = lambda s: f'{s[:4]}.{s[4:6]}.{s[6:]}' if s else ''
SPOP = f"{D(sm.get('spop_from', ''))}~{D(sm.get('spop_to', ''))[5:]}"
SRC_STAY = (f'자료: 행정안전부 LOCALDATA 외국인관광 도시민박업·한옥체험업·숙박업 인허가(등록하지 않은 숙소는 빠짐), 서울시 단기체류 외국인 생활인구 {SPOP} 평균(밤 01~05시·낮 11~18시), '
            '행정동 경계(통계청·행정안전부, vuski/admdongkor 가공본). 숙박 객실당 밤 외국인 = 밤 외국인 ÷ (민박 객실 + 호텔·모텔 등 객실 + 10).')
so3 = sum(i(d['o3']) for d in dongs); ss3 = sum(i(d['s3']) for d in dongs)
rank_open = {d['cd']: 1 + sum(1 for x in dongs if i(x['n_open']) > i(d['n_open'])) for d in dongs}
DBY = {d['cd']: d for d in dongs}
def dnear(d, k=6):
    la, lo = fd(d['lat']), fd(d['lon'])
    return [c for _, c in sorted((((fd(x['lat']) - la) * 111) ** 2 + ((fd(x['lon']) - lo) * 88) ** 2, x['cd']) for x in dongs if x['cd'] != d['cd'])[:k]]
def listed(d): return i(d['n_open']) > 0 or (fd(d['night']) or 0) >= 100
nd = 0
for d in dongs:
    if not listed(d): continue
    no, night = i(d['n_open']), fd(d['night'])
    name, gu = d['name'], d['gu']
    o3, s3, n1, n0 = i(d['o3']), i(d['s3']), i(d['new1']), i(d['new0'])
    lead = []
    if no: lead.append(f'{e(name)}에 영업 중인 외국인 민박은 <b>{no:,}곳</b>(객실 {i(d["rooms"]):,}개)으로 서울 행정동 {len(dongs)}곳 중 {rank_open[d["cd"]]}위입니다.')
    if n1 + n0 >= 6: lead.append(f'최근 1년 새로 등록한 곳은 <b>{n1:,}곳</b>, 그 전 1년은 {n0:,}곳입니다.')
    if o3 >= 15 and so3: lead.append(f'3년이 지난 민박 {o3:,}곳 중 <b>{round(100 * s3 / o3)}%</b>가 아직 영업 중입니다(서울 {round(100 * ss3 / so3)}%).')
    if night is not None and night >= 100:
        pr, pc = fd(d['per_room']), fd(d['pct'])
        lead.append(f'밤(01~05시)에 이 동에 머무는 단기체류 외국인은 평균 <b>{round(night):,}명</b>'
                    + (f', 숙박 객실 1개당 {pr:.1f}명으로 서울 상위 {max(1, round((1 - pc) * 100))}%입니다.' if pc is not None else '입니다.'))
    bm = json.loads(d['bmix'] or '{}')
    third = ('밤 외국인', f'{round(night):,}명') if night is not None else ('객실', f'{i(d["rooms"]):,}개')
    cards = (f'<div class="cards"><div class="card"><span>영업 중 민박</span><b>{no:,}곳</b></div>'
             f'<div class="card"><span>3년 생존</span><b>{pct(s3, o3) if o3 >= 15 else "—"}</b></div>'
             f'<div class="card"><span>{third[0]}</span><b>{third[1]}</b></div></div>')
    body = (f'<p class="sub">{e(gu)} · 행정동</p><h1>{e(name)} 외국인 민박(에어비앤비) 현황</h1>{cards}'
            + (f'<div class="lead">{" ".join(lead)}</div>' if lead else '') + f'<a class="btn" href="../#d={d["cd"]}">지도에서 민박 위치 보기</a>')
    day = fd(d['day'])
    rows = [('영업 중 민박', f'{no:,}곳'), ('민박 객실', f'{i(d["rooms"]):,}개'), ('한옥체험업', f'{i(d["hanok"]):,}곳'), ('호텔·모텔 등 숙박업 객실', f'{i(d["hotel"]):,}개'),
            ('최근 1년 새로 등록 / 폐업', f'{n1:,}곳 / {i(d["close1"]):,}곳'), ('1년 생존', pct(i(d['s1']), i(d['o1']))), ('3년 생존', pct(s3, o3) + f' ({o3:,}곳 중)'),
            ('밤 외국인(01~05시)', f'{round(night):,}명' if night is not None else '—'), ('낮 외국인(11~18시)', f'{round(day):,}명' if day is not None else '—')]
    body += '<h2>숫자로 보기</h2><div class="tw"><table><tbody>' + ''.join(f'<tr><td>{k}</td><td class="r num">{v}</td></tr>' for k, v in rows) + '</tbody></table></div>'
    if bm: body += '<h2>어떤 집에서 하나</h2><p>' + ' · '.join(f'{e(k)} <b class="num">{v}</b>' for k, v in bm.items()) + '</p>'
    nb = [c for c in dnear(d) if listed(DBY[c])]
    if nb: body += '<h2>가까운 동</h2><div class="links">' + ''.join(f'<a href="{c}.html">{e(DBY[c]["name"])}</a>' for c in nb) + '</div>'
    body += '<p><a href="../stay.html">서울 외국인 민박 동별 목록</a></p>'
    desc = (f'{name}({gu}) 외국인관광 도시민박 영업 {no}곳, 최근 1년 신규 {n1}곳' + (f', 3년 생존율 {pct(s3, o3)}' if o3 >= 15 else '')
            + (f', 밤 단기체류 외국인 {round(night):,}명' if night is not None else '') + '.')
    page(f'd/{d["cd"]}.html', f'{name} 외국인 민박·에어비앤비 현황 ({gu}) | jari', desc, body, 'dong', f'd/{d["cd"]}.html', SRC_STAY)
    urls.append(f'd/{d["cd"]}.html'); nd += 1
ld = sorted([d for d in dongs if i(d['n_open'])], key=lambda d: -i(d['n_open']))
def lrow(d):
    nt = fd(d['night'])
    return (f'<tr><td><a href="d/{d["cd"]}.html">{e(d["name"])}</a> <span class="sub">{e(d["gu"])}</span></td><td class="r num">{i(d["n_open"]):,}</td><td class="r num">{i(d["new1"]):,}</td>'
            f'<td class="r num">{pct(i(d["s3"]), i(d["o3"])) if i(d["o3"]) >= 15 else "—"}</td><td class="r num">{f"{round(nt):,}" if nt is not None else "—"}</td></tr>')
tot = sum(i(d['n_open']) for d in dongs)
page('stay.html', '서울 외국인 민박(에어비앤비) 동별 현황 | jari', f'서울 행정동별 외국인관광 도시민박 영업 {tot:,}곳, 최근 1년 신규, 3년 생존율, 밤 단기체류 외국인 수.',
     f'<h1>서울 외국인 민박, 동별로 보면</h1><p class="sub">영업 중 {tot:,}곳 · 민박 많은 동부터</p><a class="btn" href="./">지도에서 보기</a>'
     f'<div class="tw"><table><thead><tr><th>행정동</th><th class="r">영업</th><th class="r">1년 신규</th><th class="r">3년 생존</th><th class="r">밤 외국인</th></tr></thead><tbody>{"".join(lrow(d) for d in ld)}</tbody></table></div>',
     'list', 'stay.html', SRC_STAY)
urls.append('stay.html')
# 숙박 업종별 법령 정리(원문 확인일은 본문에 적음, 법령이 바뀌면 stay_law_body.html을 고친다)
page('stay-law.html', '서울 에어비앤비·공유숙박 업종별 법령 정리(도시민박·한옥체험업·숙박업) | jari',
     '외국인관광 도시민박업, 한옥체험업, 숙박업, 호스텔의 등록기준과 서울 용도지역별 숙박시설 제한, 월세로 빌려서 할 때 주의점을 법령 원문으로 정리.',
     open(os.path.join(os.path.dirname(__file__), 'stay_law_body.html'), encoding='utf-8').read(), 'list', 'stay-law.html',
     '자료: 국가법령정보센터 현행 법령·자치법규 원문.')
urls.append('stay-law.html')

today = dt.date.today().isoformat()
with open(f'{DOCS}/sitemap.xml', 'w', encoding='utf-8', newline='\n') as fh:
    fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
    for u in [''] + urls: fh.write(f'<url><loc>{BASE}{u}</loc><lastmod>{today}</lastmod></url>\n')
    fh.write('</urlset>\n')
open(f'{DOCS}/robots.txt', 'w', encoding='utf-8', newline='\n').write(f'User-agent: *\nAllow: /\nSitemap: {BASE}sitemap.xml\n')
print(f'페이지 {len(urls):,}개 (상권 {len(areas):,}, 구 {len(gu_rows)}, 행정동 {nd})')
