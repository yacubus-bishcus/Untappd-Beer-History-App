revoke all privileges on table public.beer_checkins from public, anon;
revoke all privileges on sequence public.beer_checkins_id_seq from public, anon;

grant select, insert, update, delete on table public.beer_checkins to authenticated;
grant usage, select on sequence public.beer_checkins_id_seq to authenticated;
