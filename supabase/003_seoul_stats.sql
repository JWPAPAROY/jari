-- 서울(또는 구) 전체 업종별 생존 집계
create or replace function seoul_stats(p_gu text default null)
returns table (svc text, o1 bigint, s1 bigint, o2 bigint, s2 bigint, o3 bigint, s3 bigint)
language sql stable security invoker as $$
  select s.svc, sum(s.o1), sum(s.s1), sum(s.o2), sum(s.s2), sum(s.o3), sum(s.s3)
  from area_stats s join area a on a.code = s.code
  where p_gu is null or a.gu = p_gu
  group by s.svc
$$;
grant execute on function seoul_stats(text) to anon, authenticated;
