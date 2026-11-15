-- 뜨는 상권: 서울시 상권분석서비스 분기 자료(매출·인구·상권변화지표) + 인허가 가게 수 변화

create table if not exists area_q (           -- 상권 × 분기
  code text, q int,                           -- q = 20262 (2026년 2분기)
  flpop double precision, flpop2030 double precision, repop double precision, wrc double precision,
  ix text, ix_nm text, opr real, cls real,    -- 상권변화지표, 운영·폐업 영업 개월 평균
  primary key (code, q)
);
create table if not exists area_sales (       -- 상권 × 분기 × 업종 추정매출 (svc: jari 업종, '전체'=외식 10개 업종 합, 'ALL'=모든 업종)
  code text, q int, svc text, amt double precision, cnt double precision, a2030 double precision,
  primary key (code, q, svc)
);
create table if not exists area_trend (       -- 상권 × 업종 요약 (refresh_trend가 다시 만듦)
  code text, svc text, q_last int,
  s_now double precision, s_prev double precision, s_3y double precision,   -- 최근 4개 분기, 그 전 4개 분기, 3년 전 4개 분기 매출 합
  y_now double precision, y_prev double precision,                           -- 그중 20·30대 매출
  f_now double precision, f_prev double precision, f_3y double precision,   -- 유동인구(4개 분기 합)
  n_now int, n_3y int, op_1y int, cl_1y int,                                -- 인허가 기준 영업 중 가게 수(지금, 3년 전), 최근 1년 개업·폐업
  ix text, ix_nm text,
  sales_yoy real, sales_3y real, flpop_yoy real, store_3y real,
  score real, grade text, flag text,
  primary key (code, svc)
);
alter table area_q enable row level security;
alter table area_sales enable row level security;
alter table area_trend enable row level security;
do $$ begin
  create policy "public read" on area_q     for select to anon, authenticated using (true);
  create policy "public read" on area_sales for select to anon, authenticated using (true);
  create policy "public read" on area_trend for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;

create or replace function refresh_trend() returns void language sql security definer set search_path = public as $$
  truncate area_trend;
  insert into area_trend
  with lastq as (select max(q) q, max((q / 10) * 4 + q % 10 - 1) o from area_sales),
  s as (
    select x.code, x.svc,
      sum(amt)   filter (where x.qo between l.o - 3  and l.o)      s_now,
      sum(amt)   filter (where x.qo between l.o - 7  and l.o - 4)  s_prev,
      sum(amt)   filter (where x.qo between l.o - 15 and l.o - 12) s_3y,
      sum(a2030) filter (where x.qo between l.o - 3  and l.o)      y_now,
      sum(a2030) filter (where x.qo between l.o - 7  and l.o - 4)  y_prev,
      count(*)   filter (where x.qo between l.o - 3  and l.o)      nq_now,
      count(*)   filter (where x.qo between l.o - 7  and l.o - 4)  nq_prev
    from (select *, (q / 10) * 4 + q % 10 - 1 qo from area_sales) x, lastq l
    group by x.code, x.svc
  ),
  f as (
    select x.code,
      sum(flpop) filter (where x.qo between l.o - 3  and l.o)      f_now,
      sum(flpop) filter (where x.qo between l.o - 7  and l.o - 4)  f_prev,
      sum(flpop) filter (where x.qo between l.o - 15 and l.o - 12) f_3y,
      max(ix)    filter (where x.q = l.q) ix,
      max(ix_nm) filter (where x.q = l.q) ix_nm
    from (select *, (q / 10) * 4 + q % 10 - 1 qo from area_q) x, lastq l
    group by x.code
  ),
  st as (
    select lc.area_code code, g.svc,
      count(*) filter (where lc.close_date is null)::int n_now,
      count(*) filter (where lc.open_date <= current_date - 1095 and (lc.close_date is null or lc.close_date > current_date - 1095))::int n_3y,
      count(*) filter (where lc.stat and lc.open_date > current_date - 365)::int op_1y,
      count(*) filter (where lc.life_days is not null and lc.close_date > current_date - 365)::int cl_1y
    from license lc cross join lateral (select lc.svc as svc union all select '전체') g
    where lc.area_code is not null and lc.svc is not null
    group by lc.area_code, g.svc
  ),
  j as (
    select a.code, sv.svc, (select q from lastq) q_last,
      s.s_now, s.s_prev, s.s_3y, s.y_now, s.y_prev, f.f_now, f.f_prev, f.f_3y,
      coalesce(st.n_now, 0) n_now, coalesce(st.n_3y, 0) n_3y, coalesce(st.op_1y, 0) op_1y, coalesce(st.cl_1y, 0) cl_1y,
      f.ix, f.ix_nm,
      (s.s_now / nullif(s.s_prev, 0) - 1)::real sales_yoy,
      (s.s_now / nullif(s.s_3y, 0) - 1)::real sales_3y,
      (f.f_now / nullif(f.f_prev, 0) - 1)::real flpop_yoy,
      (st.n_now::float / nullif(st.n_3y, 0) - 1)::real store_3y,
      (s.nq_now = 4 and s.nq_prev = 4 and s.s_prev > 0 and f.f_prev > 0
        and coalesce(st.n_3y, 0) >= case when sv.svc = '전체' then 10 else 5 end) ok
    from area a
    cross join (select distinct svc from area_sales where svc <> 'ALL') sv
    left join s  on s.code = a.code and s.svc = sv.svc
    left join f  on f.code = a.code
    left join st on st.code = a.code and st.svc = sv.svc
  ),
  r as (   -- 같은 업종 안에서 매출 1년 변화·유동인구 1년 변화·가게 수 3년 변화의 백분위 평균
    select j.*, case when ok then ((percent_rank() over w1) + (percent_rank() over w2) + (percent_rank() over w3)) / 3 end score
    from j
    window w1 as (partition by svc, ok order by sales_yoy), w2 as (partition by svc, ok order by flpop_yoy), w3 as (partition by svc, ok order by store_3y)
  )
  select code, svc, q_last, s_now, s_prev, s_3y, y_now, y_prev, f_now, f_prev, f_3y, n_now, n_3y, op_1y, cl_1y, ix, ix_nm,
         sales_yoy, sales_3y, flpop_yoy, store_3y, score::real,
         case when score >= .7 then '뜨는 중' when score <= .3 then '식는 중' when score is not null then '보합' end,
         case when n_3y >= 20 and n_now < .7 * n_3y and op_1y <= greatest(1, .05 * n_3y) then '개업 거의 없음'
              when n_now >= 10 and op_1y + cl_1y >= .6 * n_now then '손바뀜 많음' end
  from r
  where s_now is not null or n_now > 0;
$$;
revoke execute on function refresh_trend() from public, anon, authenticated;
