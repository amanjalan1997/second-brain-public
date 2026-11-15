-- Second Brain web app database (Supabase). Paste into Supabase → SQL Editor → New query → Run.
-- Safe to run again: it only creates what's missing.
--
-- One table holds everything the app shows. Each row is one item (a task, a day, a person, a company,
-- a news brief, a call, a research question, a meta doc), stored as JSON in the same shape the
-- scripts/*_to_app.py scripts already produce. `collection` + `id` together identify a row.

create table if not exists public.docs (
  collection text not null,
  id         text not null,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (collection, id)
);

create index if not exists docs_day_idx on public.docs ((data->>'day')) where collection = 'tasks';

create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;
drop trigger if exists docs_touch on public.docs;
create trigger docs_touch before update on public.docs for each row execute function public.touch_updated_at();

-- Only the owner can read or change anything. Claude's scripts use the secret service key, which
-- bypasses these rules, so it never needs a login. Change the email here if the owner changes.
alter table public.docs enable row level security;
drop policy if exists "owner only" on public.docs;
create policy "owner only" on public.docs for all to authenticated
  using ((auth.jwt() ->> 'email') = 'you@example.edu')
  with check ((auth.jwt() ->> 'email') = 'you@example.edu');

-- Live updates: the app hears about changes (e.g. a /today refresh) without reloading.
alter table public.docs replica identity full;
do $$ begin
  alter publication supabase_realtime add table public.docs;
exception when duplicate_object then null; end $$;
