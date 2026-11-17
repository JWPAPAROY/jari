#!/usr/bin/env bash
# 학원·교습소 갱신: 좌표 캐시 내보내기 → fetch_academy.py → 적재(새 곳 추가, 그대로면 last_seen, 사라지면 closed_on)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/tmp data/out
bash ./db.sh -q -c "\copy (select addr, lat, lon from geo_cache) to 'data/tmp/geo_cache.csv' with (format csv)"
python -I pipeline/fetch_academy.py data/tmp/geo_cache.csv
cat > data/tmp/load_academy.sql <<'SQL'
set statement_timeout = 0;
begin;
create temp table s (id text, kind text, name text, field text, course text, gu text, road text, reg_date text,
                     lat text, lon text, area_code text) on commit drop;
\copy s from 'data/out/academy.csv' with (format csv)
create temp table g (addr text, lat double precision, lon double precision) on commit drop;
\copy g from 'data/out/geo_new.csv' with (format csv)
insert into geo_cache (addr, lat, lon) select distinct on (addr) addr, lat, lon from g on conflict (addr) do nothing;
-- 받아 온 수가 지금 영업 중 수의 90%도 안 되면 API 문제로 보고 멈춤(전부 폐원 처리 방지)
do $$ begin
  if (select count(*) from s) < 0.9 * (select count(*) from academy where closed_on is null) then
    raise exception '학원 목록이 너무 적음: %', (select count(*) from s);
  end if;
end $$;
insert into academy (id, kind, name, field, course, gu, road, reg_date, lat, lon, area_code)
  select distinct on (id) id, kind, name, nullif(field,''), nullif(course,''), gu, road, nullif(reg_date,'')::date,
         nullif(lat,'')::float8, nullif(lon,'')::float8, nullif(area_code,'')
  from s
on conflict (id) do update set kind=excluded.kind, name=excluded.name, field=excluded.field, course=excluded.course, gu=excluded.gu,
  road=excluded.road, reg_date=excluded.reg_date, lat=coalesce(excluded.lat, academy.lat), lon=coalesce(excluded.lon, academy.lon),
  area_code=coalesce(excluded.area_code, academy.area_code), last_seen=current_date, closed_on=null;
update academy set closed_on = current_date where closed_on is null and id not in (select id from s);
select link_academy();
commit;
SQL
bash ./db.sh -q -f data/tmp/load_academy.sql
bash ./db.sh -q -c "set statement_timeout = 0" -c "vacuum analyze academy"
bash ./db.sh -tAc "select '학원 영업 '||count(*) filter (where closed_on is null)||' · 폐원 기록 '||count(*) filter (where closed_on is not null)||' · 건물 연결 '||count(jkey)||' · 좌표 없음 '||count(*) filter (where lat is null) from academy"
