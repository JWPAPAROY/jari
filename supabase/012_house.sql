-- 주택 전월세 실거래 묶음(국토교통부): 법정동 × 주택 종류 × 면적대 × 기간(0 = 최근 1년, 1 = 그 전 1년)
create table if not exists house_rent (
  gu text not null, bjd text not null, type text not null,   -- 연립다세대 | 단독다가구 | 오피스텔
  band text not null, per smallint not null,                 -- 전체 | 원룸급(30㎡ 미만) | 투룸급(30~60㎡) | 60㎡ 이상
  n_wolse int, rent real, deposit real, area real, rent_py real,   -- 월세 계약 수, 월세·보증금(만원)·면적(㎡) 중앙값, 평당 월세 중앙값
  n_jeonse int, jeonse real,                                  -- 전세 계약 수, 전세 보증금 중앙값(만원)
  primary key (gu, bjd, type, band, per)
);
-- 법정동이 어느 행정동에 얼마씩 걸쳐 있나(가게 인허가 좌표 비중)
create table if not exists bjd_dong (gu text not null, bjd text not null, dong_cd text not null, share real, primary key (gu, bjd, dong_cd));
create index if not exists bjd_dong_cd on bjd_dong (dong_cd);
alter table house_rent enable row level security;
alter table bjd_dong enable row level security;
do $$ begin
  create policy "public read" on house_rent for select to anon, authenticated using (true);
  create policy "public read" on bjd_dong for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;
