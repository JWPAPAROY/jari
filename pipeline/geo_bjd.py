import sys, csv, collections
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0,'pipeline')
import urllib.parse
from fetch_academy import VW, get_json
from build_stay import load_dongs, find_dong
dongs=load_dongs(); name={d['cd']:d['name'] for d in dongs}
miss=[('서대문구','충정로2가'),('서대문구','충정로3가'),('종로구','명륜1가'),('종로구','명륜2가'),('종로구','명륜3가'),('종로구','명륜4가'),('종로구','신문로2가'),('중구','의주로1가'),('중구','충무로2가'),('중구','충무로3가'),('중구','충무로5가')]
out=[]
for gu,b in miss:
    c=collections.Counter()
    for j in range(1,121,3):
        q=urllib.parse.urlencode({'service':'address','request':'getcoord','version':'2.0','crs':'epsg:4326','address':f'서울특별시 {gu} {b} {j}','refine':'true','simple':'true','format':'json','type':'parcel','key':VW,'domain':'https://jwpaparoy.github.io'})
        try: d=get_json('https://api.vworld.kr/req/address?'+q)['response']
        except Exception: continue
        if d.get('status')!='OK': continue
        p=d['result']['point']; cd=find_dong(dongs,float(p['y']),float(p['x']))
        if cd: c[cd]+=1
    tot=sum(c.values()); print(gu,b,tot,[(name[k],v) for k,v in c.most_common()])
    for k,v in c.most_common():
        if tot and v/tot>=.1: out.append([gu,b,k,round(v/tot,3)])
csv.writer(open('pipeline/bjd_fix.csv','w',encoding='utf-8',newline='')).writerows(out)
