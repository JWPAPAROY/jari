-- 방문 통계에 민박 화면 행동 추가(stay = 민박 보기, dong = 행정동 화면), 페이지 종류에 dong(정적 페이지) 추가
create or replace function hit(p_page text, p_src text, p_evt text default 'view') returns void
language plpgsql security definer set search_path = public as $$
begin
  if p_page not in ('map','area','gu','list','dong') or p_src not in ('google','naver','daum','bing','other','direct','internal')
     or p_evt not in ('view','search','building','area','point','svc','trend','compare','stay','dong','house') then return; end if;
  insert into hits (page, src, evt, n) values (p_page, p_src, p_evt, 1)
  on conflict (day, page, src, evt) do update set n = hits.n + 1;
end $$;
revoke execute on function hit(text, text, text) from public;
grant execute on function hit(text, text, text) to anon, authenticated;
