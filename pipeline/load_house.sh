#!/usr/bin/env bash
# 주택 전월세 실거래 묶음 + 법정동→행정동 연결 → Supabase. 필요: DATA_GO_KR_KEY(로컬은 .secrets), data/raw/dong(fetch_stay.py)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/tmp
python -I pipeline/fetch_house.py
cat > data/tmp/bjd_pts.sql <<'SQL'
set statement_timeout = 0;
\copy (select gu, split_part(split_part(jkey, '|', 2), ' ', 1), round(lat::numeric, 4), round(lon::numeric, 4), count(*) from license where jkey is not null and lat is not null group by 1, 2, 3, 4) to 'data/tmp/bjd_pts.csv' with (format csv)
SQL
bash ./db.sh -q -f data/tmp/bjd_pts.sql
python -I pipeline/build_bjd.py
cat > data/tmp/load_house.sql <<'SQL'
set statement_timeout = 0;
begin;
create temp table s_h (gu text, bjd text, type text, band text, per smallint, n_wolse int, rent text, deposit text, area text, rent_py text, n_jeonse int, jeonse text) on commit drop;
\copy s_h from 'data/out/house_rent.csv' with (format csv)
create temp table s_b (gu text, bjd text, dong_cd text, share real) on commit drop;
\copy s_b from 'data/out/bjd_dong.csv' with (format csv)
do $$ begin if (select count(*) from s_h) < 3000 then raise exception 'house rows too few'; end if; end $$;
delete from house_rent;
insert into house_rent select gu, bjd, type, band, per, n_wolse, nullif(rent,'')::real, nullif(deposit,'')::real, nullif(area,'')::real, nullif(rent_py,'')::real, n_jeonse, nullif(jeonse,'')::real from s_h;
delete from bjd_dong; insert into bjd_dong select distinct on (gu, bjd, dong_cd) * from s_b;
commit;
SQL
bash ./db.sh -q -f data/tmp/load_house.sql
bash ./db.sh -tAc "select 'house_rent '||count(*)||' / bjd_dong '||(select count(*) from bjd_dong)||' / db '||pg_size_pretty(pg_database_size('postgres')) from house_rent"
