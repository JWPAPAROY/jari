-- 한국부동산원 상업용부동산 임대동향: 조사 상권 × 분기 × 상가 종류(소규모·중대형)
create table if not exists rent (
  region text not null,      -- 조사 상권(홍대/합정 …) 또는 '서울'
  q      int  not null,      -- 20263 = 2026년 3분기
  kind   text not null,      -- 소규모 | 중대형
  rent   real,               -- ㎡당 월 임대료(천원)
  vac    real,               -- 공실률(%)
  primary key (region, q, kind)
);
-- 서울시 상권 → 가장 가까운 조사 상권(1.5km 안)
create table if not exists area_rent (code text primary key, region text not null, dist int);
alter table rent enable row level security;
alter table area_rent enable row level security;
do $$ begin
  create policy "public read" on rent for select to anon, authenticated using (true);
  create policy "public read" on area_rent for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;
