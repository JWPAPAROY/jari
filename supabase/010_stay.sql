-- 민박(외국인관광 도시민박업·한옥체험업) + 행정동별 수요·공급
create table if not exists stay (
  id text primary key,          -- 구:종류:관리번호
  gu text not null, kind text not null,   -- 도시민박 | 한옥체험
  name text, open_date date not null, close_date date, status text, road text, jkey text,
  lat real, lon real, rooms smallint, guests smallint, bld text, size_m2 real,
  area_code text, dong_cd text, life_days int
);
create index if not exists stay_dong on stay (dong_cd);
create index if not exists stay_latlon on stay (lat, lon);
create index if not exists stay_jkey on stay (jkey);

create table if not exists dong (
  cd text primary key, name text not null, gu text not null, lat real, lon real, geom jsonb,
  n_open int, rooms int, hotel int, hotel_n int, hanok int, new1 int, new0 int, close1 int,
  o1 int, s1 int, o2 int, s2 int, o3 int, s3 int,
  night real, day real,          -- 단기체류 외국인 생활인구 평균(밤 01~05시, 낮 11~18시)
  per_room real, pct real, night_pct real,   -- 숙박 객실(민박+호텔 등) 1개당 밤 외국인, 그 백분위, 밤 외국인 백분위
  bmix jsonb                     -- 영업 중 민박 건물 종류 {다가구: n, ...}
);
alter table stay enable row level security;
alter table dong enable row level security;
do $$ begin
  create policy "public read" on stay for select to anon, authenticated using (true);
  create policy "public read" on dong for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;

-- 반경 안 민박(가게 화면에서 '주변 민박'으로 씀)
create or replace function stay_near(p_lat double precision, p_lon double precision, p_r double precision default 300)
returns json language sql stable security invoker as $$
  with n as (
    select * from stay
    where lat between p_lat - p_r / 111000.0 and p_lat + p_r / 111000.0
      and lon between p_lon - p_r / 88000.0 and p_lon + p_r / 88000.0
      and (lat - p_lat) ^ 2 * 111000.0 ^ 2 + (lon - p_lon) ^ 2 * 88000.0 ^ 2 <= p_r ^ 2
  )
  select json_build_object(
    'n_open', count(*) filter (where close_date is null),
    'rooms', coalesce(sum(coalesce(rooms, 1)) filter (where close_date is null), 0),
    'new1', count(*) filter (where open_date > current_date - 365),
    'close1', count(*) filter (where close_date > current_date - 365),
    'o3', count(*) filter (where open_date >= '2016-01-01' and open_date <= current_date - 1095),
    's3', count(*) filter (where open_date >= '2016-01-01' and open_date <= current_date - 1095 and coalesce(life_days, 99999) >= 1095),
    'dong', (select dong_cd from n where dong_cd is not null group by dong_cd order by count(*) desc limit 1)
  ) from n
$$;
