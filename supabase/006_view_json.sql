-- 지도 점: PostgREST 행 제한(1000)에 안 걸리도록 한 행(json 배열)으로 돌려준다
create or replace function buildings_view(min_lat double precision, min_lon double precision, max_lat double precision, max_lon double precision)
returns jsonb
language sql stable security invoker as $$
  select coalesce(jsonb_agg(jsonb_build_array(t.jkey, t.lat, t.lon, t.n, t.n_open, t.o3, t.s3)), '[]'::jsonb)
  from (
    select b.jkey, b.lat, b.lon, b.n, b.n_open, b.o3, b.s3 from building b
    where b.lat between min_lat and max_lat and b.lon between min_lon and max_lon and b.n > 0
    order by b.n desc limit 5000
  ) t
$$;

grant execute on function buildings_view(double precision, double precision, double precision, double precision) to anon, authenticated;
