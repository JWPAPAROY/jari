#!/usr/bin/env bash
# data/out/area_q.csv, area_sales.csv → Supabase. 받은 분기만 지우고 다시 넣은 뒤 refresh_trend().
set -euo pipefail
cd "$(dirname "$0")/.."
QS=$(cat data/out/trend_quarters.txt | tr ' ' ',')
[ -n "$QS" ] || { echo "받은 분기 없음"; exit 0; }
mkdir -p data/tmp
cat > data/tmp/load_trend.sql <<SQL
set statement_timeout = 0;
begin;
delete from area_q where q in ($QS);
delete from area_sales where q in ($QS);
\copy area_q from 'data/out/area_q.csv' with (format csv)
\copy area_sales from 'data/out/area_sales.csv' with (format csv)
select refresh_trend();
commit;
SQL
bash ./db.sh -q -f data/tmp/load_trend.sql
bash ./db.sh -tAc "select 'area_q '||count(*) from area_q union all select 'area_sales '||count(*) from area_sales union all select 'area_trend '||count(*) from area_trend"
