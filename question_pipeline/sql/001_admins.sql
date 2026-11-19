-- Run once in Supabase: Dashboard -> SQL Editor -> paste -> Run.
-- Admin accounts for the question review screens in the Eigen app.
-- Admins are added only with the service key (create-admin command or the dashboard), never from the app.

create table if not exists public.admins (
    user_id    uuid primary key references auth.users (id) on delete cascade,
    created_at timestamptz not null default now()
);

alter table public.admins enable row level security;

-- A logged-in user may check whether they themselves are an admin (the app uses this to show admin screens).
-- There are no insert/update/delete policies, so only the service key can change this table.
drop policy if exists "read own admin row" on public.admins;
create policy "read own admin row" on public.admins
    for select using (auth.uid() = user_id);
