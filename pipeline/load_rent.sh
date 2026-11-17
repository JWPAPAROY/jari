#!/usr/bin/env bash
# 임대료·공실률(R-ONE) → Supabase. 표가 작아 통째로 바꾼다. 필요: data/out/area.csv(build.py)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/tmp
python -I pipeline/fetch_rent.py
cat > data/tmp/load_rent.sql <<'SQL'
set statement_timeout = 0;
begin;
create temp table s_rent (region text, q int, kind text, rent text, vac text) on commit drop;
\copy s_rent from 'data/out/rent.csv' with (format csv)
create temp table s_ar (code text, region text, dist int) on commit drop;
\copy s_ar from 'data/out/area_rent.csv' with (format csv)
do $$ begin if (select count(*) from s_rent) < 100 then raise exception 'rent rows too few'; end if; end $$;
delete from rent; insert into rent select region, q, kind, nullif(rent,'')::real, nullif(vac,'')::real from s_rent;
delete from area_rent; insert into area_rent select * from s_ar;
commit;
SQL
bash ./db.sh -q -f data/tmp/load_rent.sql
bash ./db.sh -tAc "select 'rent '||count(*)||' / area_rent '||(select count(*) from area_rent) from rent"
