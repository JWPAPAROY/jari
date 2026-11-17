#!/usr/bin/env bash
# DB → data/tmp/p_*.csv → 정적 페이지(docs/a, docs/g, docs/list.html, docs/sitemap.xml)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/tmp
cat > data/tmp/pages_export.sql <<'SQL'
set statement_timeout = 0;
\copy (select code, name, kind, gu, lat, lon from area order by code) to 'data/tmp/p_area.csv' with (format csv, header true)
\copy (select code, svc, o1, s1, o2, s2, o3, s3 from area_stats) to 'data/tmp/p_stats.csv' with (format csv, header true)
\copy (select svc, o1, s1, o2, s2, o3, s3 from seoul_stats(null)) to 'data/tmp/p_seoul.csv' with (format csv, header true)
\copy (select area_code code, svc, count(*) n from license where close_date is null and area_code is not null and svc is not null group by 1, 2) to 'data/tmp/p_open.csv' with (format csv, header true)
\copy (select code, grade, sales_yoy from area_trend where svc = '전체') to 'data/tmp/p_trend.csv' with (format csv, header true)
\copy (select area_code code, sum(k) n, string_agg(f || ' ' || k, ' · ' order by k desc) fields from (select area_code, coalesce(nullif(field,''),'기타') f, count(*) k from academy where closed_on is null and area_code is not null group by 1, 2) x group by 1) to 'data/tmp/p_acad.csv' with (format csv, header true)
\copy (select coalesce(value->>'built', '') from meta where key = 'build') to 'data/tmp/p_built.txt'
\copy (select ar.code, ar.region, ar.dist, r.kind, r.q, r.rent, r.vac from area_rent ar join rent r on r.region = ar.region where r.q in ((select max(q) from rent), (select max(q) from rent) - 10)) to 'data/tmp/p_rent.csv' with (format csv, header true)
SQL
bash ./db.sh -q -f data/tmp/pages_export.sql
python -I pipeline/build_pages.py
