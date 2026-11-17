#!/usr/bin/env bash
# data/out/*.csv → Supabase. 구 하나씩 따로 지우고 넣는다.
# 한 트랜잭션에 전부 넣으면 커밋 전까지 옛 행과 새 행이 함께 자리를 차지해 무료 한도(500MB)를 넘는다(2026-11-17 552MB).
# 구마다 커밋 → 일반 vacuum으로 지운 자리를 다음 구가 재사용 → 최대 용량 ≈ 최종 크기 + 구 하나.
# 필요: psql, 환경변수 JARI_DB_PASSWORD (로컬은 db.sh가 .secrets에서 읽음)
set -euo pipefail
cd "$(dirname "$0")/.."
META=$(cat data/out/meta.json)
T=data/tmp; mkdir -p $T
size(){ bash ./db.sh -tAc "select pg_size_pretty(pg_database_size('postgres'))"; }
echo "시작 db $(size)"

# 구별로 CSV 나누기(license 2열, cohort 2열 = 구)
python -I - <<'PY'
import csv, collections
for name in ('license', 'cohort'):
    out = collections.defaultdict(list)
    for r in csv.reader(open(f'data/out/{name}.csv', encoding='utf-8')): out[r[1]].append(r)
    for gu, rows in out.items():
        with open(f'data/tmp/{name}.{gu}.csv', 'w', encoding='utf-8', newline='') as fh: csv.writer(fh).writerows(rows)
PY

for f in $T/license.*.csv; do
  gu=${f#$T/license.}; gu=${gu%.csv}
  [ -f "$T/cohort.$gu.csv" ] || : > "$T/cohort.$gu.csv"
  cat > $T/load_gu.sql <<SQL
set statement_timeout = 0;
begin;
create temp table s_license (like license including defaults) on commit drop;
alter table s_license drop column updated_at;
\copy s_license from '$T/license.$gu.csv' with (format csv)
create temp table s_cohort (like cohort) on commit drop;
\copy s_cohort from '$T/cohort.$gu.csv' with (format csv, header false)
delete from cohort where gu = (select min(gu) from s_license);
delete from license where gu = (select min(gu) from s_license);
insert into license (id,gu,kind,name,biz_type,svc,open_date,close_date,status,jibun,road,jkey,size_m2,floor,chain,lat,lon,area_code,life_days,stat)
  select id,gu,kind,name,biz_type,nullif(svc,''),open_date,close_date,status,jibun,road,nullif(jkey,''),size_m2,floor,chain,lat,lon,nullif(area_code,''),life_days,stat from s_license;
insert into cohort select license_id,gu,nullif(area_code,''),svc,size_band,floor,chain,spot,died,open_date from s_cohort;
commit;
SQL
  bash ./db.sh -q -f $T/load_gu.sql
  bash ./db.sh -q -c "set statement_timeout = 0" -c "vacuum license" -c "vacuum cohort"
  echo "$gu 적재 · db $(size)"
done

cat > $T/load_rest.sql <<SQL
set statement_timeout = 0;
begin;
create temp table s_area (like area) on commit drop;
\copy s_area from 'data/out/area.csv' with (format csv, header true)
insert into area select * from s_area on conflict (code) do update set name=excluded.name, kind=excluded.kind, gu=excluded.gu, geom=excluded.geom, lat=excluded.lat, lon=excluded.lon;
insert into meta values ('build', '$META'::jsonb, now()) on conflict (key) do update set value=excluded.value, updated_at=now();
select refresh_stats();
commit;
SQL
bash ./db.sh -q -f $T/load_rest.sql
bash ./db.sh -q -c "set statement_timeout = 0" -c "vacuum analyze license" -c "vacuum analyze cohort" -c "vacuum analyze building" -c "vacuum analyze area_stats"
bash ./db.sh -tAc "select 'license '||count(*) from license union all select 'cohort '||count(*) from cohort union all select 'area '||count(*) from area"
echo "끝 db $(size)"
