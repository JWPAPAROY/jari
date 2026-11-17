-- 건축물대장(국토교통부 건축HUB) 조회 RPC: 키는 private 스키마에 두고 서버에서만 호출, 결과는 30일 캐시
-- 필요: create extension http; private.cfg에 data_go_kr_key 행(값은 저장소에 넣지 않음, load로 따로 넣음)
create extension if not exists http with schema extensions;
create schema if not exists private;
revoke all on schema private from anon, authenticated;
create table if not exists private.cfg (k text primary key, v text not null);
create table if not exists private.bld_cache (pnu text primary key, data jsonb, at timestamptz default now());
create table if not exists private.bld_calls (d date primary key, n int not null);

create or replace function private.arr(j jsonb) returns jsonb language sql immutable as $$
  select case jsonb_typeof(j) when 'array' then j when 'object' then jsonb_build_array(j) else '[]'::jsonb end $$;

create or replace function public.bld_ledger(p_pnu text) returns jsonb
language plpgsql security definer set search_path = public, extensions as $$
declare
  c jsonb; v_n int; k text; q text; base text := 'https://apis.data.go.kr/1613000/BldRgstHubService/';
  t jsonb; f jsonb; e jsonb := '[]'; ex jsonb := null; out jsonb;
begin
  if p_pnu !~ '^11\d{17}$' then return null; end if;   -- 서울 필지만
  select data into c from private.bld_cache where pnu = p_pnu and at > now() - interval '30 days';
  if found then return c; end if;
  insert into private.bld_calls as b (d, n) values (current_date, 1) on conflict (d) do update set n = b.n + 1 returning b.n into v_n;
  if v_n > 2500 then return jsonb_build_object('err', 'limit'); end if;   -- 하루 호출 상한(개발 계정 한도 보호)
  select v into k from private.cfg where cfg.k = 'data_go_kr_key';
  if k is null then return jsonb_build_object('err', 'nokey'); end if;
  perform http_set_curlopt('CURLOPT_TIMEOUT_MS', '8000');
  q := 'serviceKey=' || urlencode(k) || '&sigunguCd=' || substr(p_pnu, 1, 5) || '&bjdongCd=' || substr(p_pnu, 6, 5)
       || '&platGbCd=' || (case substr(p_pnu, 11, 1) when '2' then '1' else '0' end)
       || '&bun=' || substr(p_pnu, 12, 4) || '&ji=' || substr(p_pnu, 16, 4) || '&_type=json&pageNo=1';
  begin
    t := private.arr((select content::jsonb from http_get(base || 'getBrTitleInfo?numOfRows=30&' || q)) #> '{response,body,items,item}');
    f := private.arr((select content::jsonb from http_get(base || 'getBrFlrOulnInfo?numOfRows=200&' || q)) #> '{response,body,items,item}');
    -- 공동주택이면 호별 전용면적(전유부)
    if exists (select 1 from jsonb_array_elements(t) x where x->>'mainPurpsCd' like '02%') then
      e := private.arr((select content::jsonb from http_get(base || 'getBrExposPubuseAreaInfo?numOfRows=1000&' || q)) #> '{response,body,items,item}');
      select jsonb_build_object('n', count(*), 'min', round(min(a)::numeric, 1), 'med', round((percentile_cont(.5) within group (order by a))::numeric, 1), 'max', round(max(a)::numeric, 1))
        into ex from (
          select sum((x->>'area')::real) a from jsonb_array_elements(e) x
          where x->>'exposPubuseGbCd' = '1' and x->>'mainPurpsCd' like '02%' group by x->>'dongNm', x->>'hoNm') s;
    end if;
  exception when others then
    return jsonb_build_object('err', 'api');
  end;
  out := jsonb_build_object(
    'title', (select coalesce(jsonb_agg(jsonb_build_object('kind', x->>'regstrKindCdNm', 'dong', nullif(trim(x->>'dongNm'), ''), 'cd', x->>'mainPurpsCd', 'nm', x->>'mainPurpsCdNm',
               'etc', nullif(trim(x->>'etcPurps'), ''), 'area', (x->>'totArea')::real, 'hhld', (x->>'hhldCnt')::int, 'fmly', (x->>'fmlyCnt')::int, 'ho', (x->>'hoCnt')::int,
               'strct', nullif(trim(coalesce(x->>'strctCdNm', '') || ' ' || coalesce(x->>'etcStrct', '')), ''), 'roof', nullif(trim(coalesce(x->>'roofCdNm', '') || ' ' || coalesce(x->>'etcRoof', '')), ''), 'grnd', (x->>'grndFlrCnt')::int, 'ugrnd', (x->>'ugrndFlrCnt')::int, 'apr', nullif(trim(x->>'useAprDay'), ''))), '[]') from jsonb_array_elements(t) x),
    'floors', (select coalesce(jsonb_agg(jsonb_build_object('dong', nullif(trim(x->>'dongNm'), ''), 'gb', x->>'flrGbCdNm', 'no', (x->>'flrNo')::int, 'flr', x->>'flrNoNm',
               'cd', x->>'mainPurpsCd', 'nm', x->>'mainPurpsCdNm', 'etc', nullif(trim(x->>'etcPurps'), ''), 'area', (x->>'area')::real, 'main', x->>'mainAtchGbCd' = '0')
               order by x->>'dongNm', x->>'flrGbCd' desc, (x->>'flrNo')::int desc), '[]') from jsonb_array_elements(f) x),
    'units', ex);
  if jsonb_array_length(out->'title') > 0 then   -- 빈 결과(대장이 다른 지번에 등록된 필지 등)는 캐시하지 않음
  insert into private.bld_cache (pnu, data, at) values (p_pnu, out, now()) on conflict (pnu) do update set data = excluded.data, at = now();
  end if;
  return out;
end $$;
revoke all on function public.bld_ledger(text) from public;
grant execute on function public.bld_ledger(text) to anon, authenticated;
