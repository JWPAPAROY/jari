-- 방문 통계(쿠키·개인정보 없음): 날짜 × 페이지 종류 × 유입 경로 × 행동 별 횟수만 센다
create table if not exists hits (
  day date not null default (now() at time zone 'Asia/Seoul')::date,
  page text not null,     -- map | area | gu | list
  src  text not null,     -- google | naver | daum | bing | other | direct | internal
  evt  text not null,     -- view | search | building | area | point | svc | trend | compare
  n    int not null default 0,
  primary key (day, page, src, evt)
);
alter table hits enable row level security;   -- 읽기는 관리 쪽에서만(psql)

create or replace function hit(p_page text, p_src text, p_evt text default 'view') returns void
language plpgsql security definer set search_path = public as $$
begin
  -- 정해 둔 값만 받아 행 수가 늘지 않게 함(하루 최대 4×7×8행)
  if p_page not in ('map','area','gu','list') or p_src not in ('google','naver','daum','bing','other','direct','internal')
     or p_evt not in ('view','search','building','area','point','svc','trend','compare') then return; end if;
  insert into hits (page, src, evt, n) values (p_page, p_src, p_evt, 1)
  on conflict (day, page, src, evt) do update set n = hits.n + 1;
end $$;
revoke execute on function hit(text, text, text) from public;
grant execute on function hit(text, text, text) to anon, authenticated;
