#!/usr/bin/env bash
# 민박·행정동 → Supabase. 표가 작아(민박 1만여 곳, 행정동 427곳) 통째로 바꾼다.
# 필요: data/raw/relm.zip(fetch.py), SEOUL_API_KEY(로컬은 .secrets)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/tmp
python -I pipeline/fetch_stay.py
python -I pipeline/build_stay.py
META=$(cat data/out/stay_meta.json)
cat > data/tmp/load_stay.sql <<SQL
set statement_timeout = 0;
begin;
create temp table s_stay (id text, gu text, kind text, name text, open_date date, close_date text, status text, road text, jkey text,
  lat text, lon text, rooms text, guests text, bld text, size_m2 text, area_code text, dong_cd text, life_days text) on commit drop;
\copy s_stay from 'data/out/stay.csv' with (format csv)
create temp table s_dong (cd text, name text, gu text, lat real, lon real, geom jsonb, n_open int, rooms int, hotel int, hotel_n int, hanok int,
  new1 int, new0 int, close1 int, o1 int, s1 int, o2 int, s2 int, o3 int, s3 int, night text, day text, per_room text, pct text, night_pct text, bmix jsonb) on commit drop;
\copy s_dong from 'data/out/dong.csv' with (format csv)
do \$\$ begin
  if (select count(*) from s_stay) < 5000 then raise exception 'stay rows too few'; end if;
  if (select count(*) from s_dong) < 400 then raise exception 'dong rows too few'; end if;
end \$\$;
delete from stay;
insert into stay select id, gu, kind, name, open_date, nullif(close_date,'')::date, status, road, nullif(jkey,''), nullif(lat,'')::real, nullif(lon,'')::real,
  nullif(rooms,'')::smallint, nullif(guests,'')::smallint, nullif(bld,''), nullif(size_m2,'')::real, nullif(area_code,''), nullif(dong_cd,''), nullif(life_days,'')::int from s_stay;
delete from dong;
insert into dong select cd, name, gu, lat, lon, geom, n_open, rooms, hotel, hotel_n, hanok, new1, new0, close1, o1, s1, o2, s2, o3, s3,
  nullif(night,'')::real, nullif(day,'')::real, nullif(per_room,'')::real, nullif(pct,'')::real, nullif(night_pct,'')::real, bmix from s_dong;
insert into meta values ('stay', '$META'::jsonb, now()) on conflict (key) do update set value = excluded.value, updated_at = now();
commit;
SQL
bash ./db.sh -q -f data/tmp/load_stay.sql
bash ./db.sh -q -c "set statement_timeout = 0" -c "vacuum analyze stay" -c "vacuum analyze dong"
bash ./db.sh -tAc "select 'stay '||count(*)||' / dong '||(select count(*) from dong)||' / db '||pg_size_pretty(pg_database_size('postgres')) from stay"
