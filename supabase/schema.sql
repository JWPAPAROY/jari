-- jari 스키마: 공공데이터 가공본(읽기 전용 공개). 쓰기는 파이프라인(postgres 역할)만.

create table if not exists license (
  id          text primary key,          -- LOCALDATA 관리번호
  gu          text not null,             -- 송파구 등
  kind        text not null,             -- 음식점 | 휴게
  name        text not null,
  biz_type    text,                      -- 업태구분명
  svc         text,                      -- 서울시 서비스업종 이름(한식, 커피·음료 …)
  open_date   date not null,
  close_date  date,                      -- 폐업일(폐업 상태일 때만)
  status      text,                      -- 영업 | 폐업 | 휴업 …
  jibun       text,
  road        text,
  jkey        text,                      -- '구|동 번지' 정규화 키 (건물 조회용)
  size_m2     real,
  floor       text,                      -- 1층 | 2층 이상 | 지하 | 층 미상
  chain       boolean,
  lat         double precision,
  lon         double precision,
  area_code   text,                      -- 서울시 상권 코드
  updated_at  timestamptz not null default now()
);
create index if not exists license_jkey on license (jkey);
create index if not exists license_gu_open on license (gu, open_date);
create index if not exists license_latlon on license (lat, lon);

create table if not exists area (
  code   text primary key,
  name   text not null,
  kind   text,                           -- 골목상권 | 발달상권 | 전통시장 | 관광특구
  gu     text,
  geom   jsonb                           -- [[ [lon,lat], ... ], ...] 링 목록 (단순화)
);

-- 3년 추적 코호트: 개업 후 1,095일이 지난 가게만
create table if not exists cohort (
  license_id  text primary key references license(id) on delete cascade,
  gu          text not null,
  area_code   text,
  svc         text not null,
  size_band   text not null,
  floor       text not null,
  chain       boolean not null,
  spot        smallint not null,           -- 같은 건물 직전 3년 폐업 수(최대 2)
  died        boolean not null,            -- 개업 후 3년 안에 폐업
  open_date   date not null
);
create index if not exists cohort_filter on cohort (gu, svc, size_band, floor);

create table if not exists meta (
  key text primary key,
  value jsonb,
  updated_at timestamptz not null default now()
);

alter table license enable row level security;
alter table area    enable row level security;
alter table cohort  enable row level security;
alter table meta    enable row level security;
do $$ begin
  create policy "public read" on license for select to anon, authenticated using (true);
  create policy "public read" on area    for select to anon, authenticated using (true);
  create policy "public read" on cohort  for select to anon, authenticated using (true);
  create policy "public read" on meta    for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;

-- 건물(지번) 이력 검색: '망원동 415' 같은 입력
create or replace function building_search(q text)
returns table (jkey text, n bigint, closed bigint)
language sql stable security invoker as $$
  select l.jkey, count(*), count(l.close_date)
  from license l
  where l.jkey is not null
    and (l.close_date is null or l.close_date >= date '2016-01-01')
    and (select bool_and(position(t in split_part(l.jkey, '|', 2)) > 0)
         from unnest(string_to_array(trim(regexp_replace(q, '\s+', ' ', 'g')), ' ')) t)
  group by l.jkey
  order by count(*) desc
  limit 24
$$;

-- 조건별 3년 폐업률 (빈 값 = 전체)
create or replace function cohort_rate(p_gu text default null, p_area text default null, p_svc text default null,
                                       p_size text default null, p_floor text default null,
                                       p_chain boolean default null, p_spot int default null)
returns table (n bigint, died bigint)
language sql stable security invoker as $$
  select count(*), count(*) filter (where c.died)
  from cohort c
  where (p_gu is null or c.gu = p_gu) and (p_area is null or c.area_code = p_area)
    and (p_svc is null or c.svc = p_svc) and (p_size is null or c.size_band = p_size)
    and (p_floor is null or c.floor = p_floor) and (p_chain is null or c.chain = p_chain)
    and (p_spot is null or c.spot = p_spot)
$$;

grant execute on function building_search(text) to anon, authenticated;
grant execute on function cohort_rate(text, text, text, text, text, boolean, int) to anon, authenticated;
