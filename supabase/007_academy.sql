-- 학원·교습소 (서울시 OpenAPI neisAcademyInfo: 지금 등록된 곳만 줌 → 매주 비교해 사라지면 폐원으로 기록)
create table if not exists academy (
  id          text primary key,          -- 학원지정번호 PEI_DSGN_NO
  kind        text not null,             -- 학원 | 교습소
  name        text not null,
  field       text,                      -- 분야(입시·검정 및 보습, 국제화, 예능 …)
  course      text,                      -- 교습과정
  gu          text,
  road        text,
  reg_date    date,                      -- 등록일
  lat double precision, lon double precision,
  area_code   text,
  jkey        text,                      -- 30m 안 가장 가까운 jari 건물
  first_seen  date not null default current_date,
  last_seen   date not null default current_date,
  closed_on   date                       -- 목록에서 사라진 첫 주(폐원으로 봄)
);
create index if not exists academy_latlon on academy (lat, lon);
create index if not exists academy_jkey on academy (jkey);
create index if not exists academy_area on academy (area_code);

-- 주소 → 좌표 캐시(브이월드 호출 줄이기)
create table if not exists geo_cache (addr text primary key, lat double precision, lon double precision, at date default current_date);

alter table academy   enable row level security;
alter table geo_cache enable row level security;
do $$ begin
  create policy "public read" on academy for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;

-- 건물 연결: 좌표 30m 안 가장 가까운 building
create or replace function link_academy() returns void language sql security definer set search_path = public as $$
  update academy a set jkey = (
    select b.jkey from building b
    where b.lat between a.lat - 0.00027 and a.lat + 0.00027 and b.lon between a.lon - 0.00034 and a.lon + 0.00034
    order by (b.lat - a.lat) ^ 2 * 111000.0 ^ 2 + (b.lon - a.lon) ^ 2 * 88000.0 ^ 2 limit 1)
  where a.lat is not null;
$$;
revoke execute on function link_academy() from public, anon, authenticated;

-- 반경(또는 상권) 안 학원·교습소: 지금 수, 분야별, 최근 1년 등록, 관찰된 폐원
create or replace function academy_stats(p_lat double precision, p_lon double precision, p_r double precision default 300, p_area text default null)
returns jsonb language sql stable security invoker as $$
  with b as (
    select * from academy a
    where (p_area is not null and a.area_code = p_area)
       or (p_area is null and a.lat between p_lat - p_r / 111000.0 and p_lat + p_r / 111000.0
           and a.lon between p_lon - p_r / 88000.0 and p_lon + p_r / 88000.0
           and (a.lat - p_lat) ^ 2 * 111000.0 ^ 2 + (a.lon - p_lon) ^ 2 * 88000.0 ^ 2 <= p_r ^ 2)
  )
  select jsonb_build_object(
    'open', (select count(*) from b where closed_on is null),
    'hakwon', (select count(*) from b where closed_on is null and kind = '학원'),
    'gyoseupso', (select count(*) from b where closed_on is null and kind = '교습소'),
    'new_1y', (select count(*) from b where reg_date > current_date - 365),
    'closed', (select count(*) from b where closed_on is not null),
    'since', (select min(first_seen) from academy),
    'fields', (select coalesce(jsonb_agg(to_jsonb(f) order by f.n desc), '[]') from
                 (select coalesce(nullif(field, ''), '기타') field, count(*)::int n from b where closed_on is null group by 1) f)
  )
$$;
grant execute on function academy_stats(double precision, double precision, double precision, text) to anon, authenticated;
