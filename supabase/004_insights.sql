-- 상세 인사이트: 층·면적·체인별 생존, 연도별 개업·폐업, 지금 영업 중인 업종 구성
create index if not exists license_area on license (area_code);

-- p_area가 있으면 그 상권, 없으면 (p_lat, p_lon) 반경 p_r 미터. p_svc='전체'면 모든 업종.
create or replace function place_detail(p_lat double precision, p_lon double precision, p_r double precision default 300,
                                        p_svc text default '전체', p_area text default null)
returns jsonb language sql stable security invoker as $$
  with base as (
    select l.* from license l
    where p_area is not null and l.area_code = p_area and l.svc is not null
    union all
    select l.* from license l
    where p_area is null and l.svc is not null
      and l.lat between p_lat - p_r / 111000.0 and p_lat + p_r / 111000.0
      and l.lon between p_lon - p_r / 88000.0 and p_lon + p_r / 88000.0
      and (l.lat - p_lat) ^ 2 * 111000.0 ^ 2 + (l.lon - p_lon) ^ 2 * 88000.0 ^ 2 <= p_r ^ 2
  ),
  coh as (   -- 생존율 대상: 2016년 이후 개업, 명의변경 전 기록 제외, 고른 업종
    select * from base where stat and open_date >= '2016-01-01' and (p_svc = '전체' or svc = p_svc)
  ),
  grp as (
    select g, k, ord,
           count(*) filter (where open_date <= current_date - 365)::int o1,
           count(*) filter (where open_date <= current_date - 365 and coalesce(life_days, 99999) >= 365)::int s1,
           count(*) filter (where open_date <= current_date - 1095)::int o3,
           count(*) filter (where open_date <= current_date - 1095 and coalesce(life_days, 99999) >= 1095)::int s3
    from coh cross join lateral (values
      ('floor', floor, case floor when '1층' then 1 when '2층 이상' then 2 when '지하' then 3 else 9 end),
      ('size', case when size_m2 is null then null when size_m2 < 33 then '10평 미만' when size_m2 < 66 then '10~20평' when size_m2 < 132 then '20~40평' else '40평 이상' end,
               case when size_m2 < 33 then 1 when size_m2 < 66 then 2 when size_m2 < 132 then 3 else 4 end),
      ('chain', case when chain then '프랜차이즈' else '개인 가게' end, case when chain then 2 else 1 end)
    ) v(g, k, ord)
    where k is not null and k <> '층 미상'
    group by g, k, ord
  ),
  yrs as (
    select y.y,
           count(*) filter (where b.stat and b.open_date >= make_date(y.y, 1, 1) and b.open_date < make_date(y.y + 1, 1, 1))::int opens,
           count(*) filter (where b.life_days is not null and b.close_date >= make_date(y.y, 1, 1) and b.close_date < make_date(y.y + 1, 1, 1))::int closes
    from generate_series(2016, extract(year from current_date)::int) y(y)
    left join base b on (p_svc = '전체' or b.svc = p_svc)
    group by y.y
  ),
  now_open as (
    select svc, count(*)::int n from base where close_date is null group by svc
  )
  select jsonb_build_object(
    'groups', (select coalesce(jsonb_agg(to_jsonb(grp) order by g, ord), '[]') from grp),
    'years',  (select jsonb_agg(to_jsonb(yrs) order by y) from yrs),
    'open_now', (select coalesce(jsonb_agg(to_jsonb(now_open) order by n desc), '[]') from now_open),
    'asof', current_date
  )
$$;
grant execute on function place_detail(double precision, double precision, double precision, text, text) to anon, authenticated;
