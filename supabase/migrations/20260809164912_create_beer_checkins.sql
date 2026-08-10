create table public.beer_checkins (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  fingerprint text not null check (char_length(fingerprint) = 64),
  beer_name text not null check (char_length(trim(beer_name)) > 0),
  producer text,
  consumed_location text,
  latitude double precision check (latitude is null or latitude between -90 and 90),
  longitude double precision check (longitude is null or longitude between -180 and 180),
  beer_type text,
  my_rating numeric(3, 2) check (my_rating is null or my_rating between 0 and 5),
  global_rating numeric(3, 2) check (global_rating is null or global_rating between 0 and 5),
  checked_in_at timestamptz,
  total_checkins bigint check (total_checkins is null or total_checkins >= 0),
  imported_at timestamptz not null default now()
);

comment on table public.beer_checkins is
  'Per-user Untappd check-in history imported from the desktop app CSV export.';

create unique index beer_checkins_user_fingerprint_idx
  on public.beer_checkins (user_id, fingerprint);

create index beer_checkins_user_checked_in_at_idx
  on public.beer_checkins (user_id, checked_in_at desc nulls last);

create index beer_checkins_user_beer_type_idx
  on public.beer_checkins (user_id, beer_type);

create index beer_checkins_user_producer_idx
  on public.beer_checkins (user_id, producer);

alter table public.beer_checkins enable row level security;

create policy "Users can read their own check-ins"
  on public.beer_checkins
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can insert their own check-ins"
  on public.beer_checkins
  for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update their own check-ins"
  on public.beer_checkins
  for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete their own check-ins"
  on public.beer_checkins
  for delete
  to authenticated
  using ((select auth.uid()) = user_id);

grant usage on schema public to authenticated;
grant select, insert, update, delete on table public.beer_checkins to authenticated;
grant usage, select on sequence public.beer_checkins_id_seq to authenticated;
