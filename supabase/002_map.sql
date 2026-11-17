-- 지도·검색용: 생존 기간, 건물/상권 집계, 검색·반경 통계 함수

alter table license add column if not exists life_days int;          -- 개업~폐업 일수(영업 중·명의변경이면 null)
alter table license add column if not exists stat boolean default true; -- 통계 포함 여부(명의변경 전 기록은 false)
alter table area add column if not exists lat double precision;
alter table area add column if not exists lon double precision;

-- 건물(지번) 단위 집계: 2016년 이후 개업 가게 기준
create table if not exists building (
  jkey text primary key, gu text, label text, road text, lat double precision, lon double precision, area_code text,
  n int, n_open int, o1 int, s1 int, o2 int, s2 int, o3 int, s3 int, last_open date
);
create index if not exists building_latlon on building (lat, lon);
create index if not exists building_label on building using gin (to_tsvector('simple', coalesce(label,'') || ' ' || coalesce(road,'')));

-- 상권 × 업종 집계 (svc = '전체' 포함)
create table if not exists area_stats (
  code text, svc text, o1 int, s1 int, o2 int, s2 int, o3 int, s3 int, med_days int,
  primary key (code, svc)
);

alter table building   enable row level security;
alter table area_stats enable row level security;
do $$ begin
  create policy "public read" on building   for select to anon, authenticated using (true);
  create policy "public read" on area_stats for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;

-- 집계 다시 만들기 (적재 후 호출)
create or replace function refresh_stats() returns void language sql security definer set search_path = public as $$
  truncate building;
  insert into building
  select l.jkey, min(l.gu), split_part(l.jkey, '|', 2),
         (array_agg(split_part(l.road, ',', 1) order by l.open_date desc) filter (where l.road <> ''))[1],
         avg(l.lat), avg(l.lon),
         mode() within group (order by l.area_code),
         count(*) filter (where l.open_date >= '2016-01-01' and l.stat),
         count(*) filter (where l.close_date is null),
         count(*) filter (where l.stat and l.open_date >= '2016-01-01' and l.open_date <= current_date - 365),
         count(*) filter (where l.stat and l.open_date >= '2016-01-01' and l.open_date <= current_date - 365 and coalesce(l.life_days, 99999) >= 365),
         count(*) filter (where l.stat and l.open_date >= '2016-01-01' and l.open_date <= current_date - 730),
         count(*) filter (where l.stat and l.open_date >= '2016-01-01' and l.open_date <= current_date - 730 and coalesce(l.life_days, 99999) >= 730),
         count(*) filter (where l.stat and l.open_date >= '2016-01-01' and l.open_date <= current_date - 1095),
         count(*) filter (where l.stat and l.open_date >= '2016-01-01' and l.open_date <= current_date - 1095 and coalesce(l.life_days, 99999) >= 1095),
         max(l.open_date)
  from license l
  where l.jkey is not null and l.lat is not null and l.svc is not null and (l.close_date is null or l.close_date >= '2016-01-01')
  group by l.jkey;

  truncate area_stats;
  insert into area_stats
  select l.area_code, coalesce(g.svc, '전체'),
         count(*) filter (where l.open_date <= current_date - 365),
         count(*) filter (where l.open_date <= current_date - 365 and coalesce(l.life_days, 99999) >= 365),
         count(*) filter (where l.open_date <= current_date - 730),
         count(*) filter (where l.open_date <= current_date - 730 and coalesce(l.life_days, 99999) >= 730),
         count(*) filter (where l.open_date <= current_date - 1095),
         count(*) filter (where l.open_date <= current_date - 1095 and coalesce(l.life_days, 99999) >= 1095),
         (percentile_cont(0.5) within group (order by l.life_days) filter (where l.life_days is not null))::int
  from license l
  cross join lateral (select l.svc as svc union all select null) g
  where l.stat and l.open_date >= '2016-01-01' and l.area_code is not null and l.svc is not null
  group by l.area_code, g.svc;
$$;
revoke execute on function refresh_stats() from public, anon, authenticated;

-- 검색: 지번·도로명·상권 이름
create or replace function search_places(q text)
returns table (kind text, id text, label text, sub text, lat double precision, lon double precision, n int)
language sql stable security invoker as $$
  with t as (select array_remove(string_to_array(trim(regexp_replace(regexp_replace(q, '서울(특별시)?', '', 'g'), '\s+', ' ', 'g')), ' '), '') as toks)
  (select 'area', a.code, a.name, a.gu || ' · ' || a.kind, a.lat, a.lon, null::int
   from area a, t
   where (select bool_and(position(x in a.name) > 0) from unnest(t.toks) x)
   order by length(a.name) limit 8)
  union all
  (select 'building', b.jkey, b.label, b.gu || coalesce(' · ' || b.road, ''), b.lat, b.lon, b.n
   from building b, t
   where (select bool_and(position(x in (b.gu || ' ' || b.label || ' ' || coalesce(b.road, ''))) > 0) from unnest(t.toks) x)
   order by b.n desc nulls last limit 15)
$$;

-- 반경 통계(업종별): 지도에서 고른 위치 주변 r 미터
create or replace function near_stats(p_lat double precision, p_lon double precision, p_r double precision default 300)
returns table (svc text, o1 int, s1 int, o2 int, s2 int, o3 int, s3 int, med_days int)
language sql stable security invoker as $$
  with near as (
    select l.* from license l
    where l.lat between p_lat - p_r / 111000.0 and p_lat + p_r / 111000.0
      and l.lon between p_lon - p_r / 88000.0 and p_lon + p_r / 88000.0
      and l.stat and l.open_date >= '2016-01-01' and l.svc is not null
      and (l.lat - p_lat) ^ 2 * 111000.0 ^ 2 + (l.lon - p_lon) ^ 2 * 88000.0 ^ 2 <= p_r ^ 2
  )
  select coalesce(g.svc, '전체'),
         count(*) filter (where n.open_date <= current_date - 365)::int,
         count(*) filter (where n.open_date <= current_date - 365 and coalesce(n.life_days, 99999) >= 365)::int,
         count(*) filter (where n.open_date <= current_date - 730)::int,
         count(*) filter (where n.open_date <= current_date - 730 and coalesce(n.life_days, 99999) >= 730)::int,
         count(*) filter (where n.open_date <= current_date - 1095)::int,
         count(*) filter (where n.open_date <= current_date - 1095 and coalesce(n.life_days, 99999) >= 1095)::int,
         (percentile_cont(0.5) within group (order by n.life_days) filter (where n.life_days is not null))::int
  from near n cross join lateral (select n.svc as svc union all select null) g
  group by g.svc
$$;

-- 화면 범위 안 건물 (지도 점)
create or replace function buildings_in_view(min_lat double precision, min_lon double precision, max_lat double precision, max_lon double precision)
returns table (jkey text, lat double precision, lon double precision, n int, n_open int, o3 int, s3 int)
language sql stable security invoker as $$
  select b.jkey, b.lat, b.lon, b.n, b.n_open, b.o3, b.s3 from building b
  where b.lat between min_lat and max_lat and b.lon between min_lon and max_lon and b.n > 0
  order by b.n desc limit 3000
$$;

grant execute on function search_places(text) to anon, authenticated;
grant execute on function near_stats(double precision, double precision, double precision) to anon, authenticated;
grant execute on function buildings_in_view(double precision, double precision, double precision, double precision) to anon, authenticated;
