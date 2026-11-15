#!/usr/bin/env bash
# data/out/*.csv → Supabase. 처리한 구의 기존 행을 지우고 다시 넣는다(한 트랜잭션).
# 필요: psql, 환경변수 JARI_DB_PASSWORD (로컬은 db.sh가 .secrets에서 읽음)
set -euo pipefail
cd "$(dirname "$0")/.."
META=$(cat data/out/meta.json)
mkdir -p data/tmp
cat > data/tmp/load.sql <<SQL
begin;
create temp table s_license (like license including defaults) on commit drop;
alter table s_license drop column updated_at;
\copy s_license from 'data/out/license.csv' with (format csv)
create temp table s_cohort (like cohort) on commit drop;
\copy s_cohort from 'data/out/cohort.csv' with (format csv, header false)
create temp table s_area (like area) on commit drop;
\copy s_area from 'data/out/area.csv' with (format csv, header true)
delete from cohort where gu in (select distinct gu from s_license);
delete from license where gu in (select distinct gu from s_license);
insert into license (id,gu,kind,name,biz_type,svc,open_date,close_date,status,jibun,road,jkey,size_m2,floor,chain,lat,lon,area_code,life_days,stat)
  select id,gu,kind,name,biz_type,nullif(svc,''),open_date,close_date,status,jibun,road,nullif(jkey,''),size_m2,floor,chain,lat,lon,nullif(area_code,''),life_days,stat from s_license;
insert into cohort select license_id,gu,nullif(area_code,''),svc,size_band,floor,chain,spot,died,open_date from s_cohort;
insert into area select * from s_area on conflict (code) do update set name=excluded.name, kind=excluded.kind, gu=excluded.gu, geom=excluded.geom, lat=excluded.lat, lon=excluded.lon;
insert into meta values ('build', '$META'::jsonb, now()) on conflict (key) do update set value=excluded.value, updated_at=now();
select refresh_stats();
commit;
SQL
bash ./db.sh -q -f data/tmp/load.sql
bash ./db.sh -tAc "select 'license '||count(*) from license union all select 'cohort '||count(*) from cohort union all select 'area '||count(*) from area"
# 지우고 다시 넣은 자리(빈 공간)를 돌려받음: 안 하면 매주 커져 무료 한도 500MB를 넘김
bash ./db.sh -q -c "vacuum full analyze license" -c "vacuum full analyze cohort" -c "vacuum full analyze building"
bash ./db.sh -tAc "select 'db '||pg_size_pretty(pg_database_size('postgres'))"
