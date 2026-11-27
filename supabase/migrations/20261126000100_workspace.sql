begin;
create table public.profiles (
  id uuid primary key,
  owner text not null,
  name text not null check (length(trim(name)) between 1 and 80),
  requirements jsonb not null check (jsonb_typeof(requirements) = 'object'),
  functional jsonb constraint profiles_functional_v1 check (
    functional is null or coalesce(jsonb_typeof(functional) = 'object' and functional ->> 'schema_version' = '1', false)
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index profiles_owner on public.profiles(owner, created_at);
create unique index profiles_owner_name on public.profiles(owner, lower(name));
create function public.workspace_updated_at() returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end;
$$;
create trigger profiles_updated_at before update on public.profiles for each row execute function public.workspace_updated_at();
create table public.analyses (
  id uuid primary key,
  owner text not null,
  created_at timestamptz not null default now(),
  profiles jsonb not null check (jsonb_array_length(profiles) = 2),
  result jsonb not null check (result->'mask' = 'null'::jsonb),
  model_versions jsonb not null,
  fingerprint text not null,
  status text not null check (status in ('pending', 'complete', 'deleting')),
  image_path text not null,
  mask_path text
);
create index analyses_owner_created on public.analyses(owner, created_at desc);
alter table public.profiles enable row level security;
alter table public.analyses enable row level security;
revoke all on public.profiles, public.analyses from anon, authenticated;
grant usage on schema public to service_role;
grant all on public.profiles, public.analyses to service_role;
revoke all on function public.workspace_updated_at() from public;
insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
values ('workspace-analyses', 'workspace-analyses', false, 8388608, array['image/jpeg','image/png','image/webp']);
-- No public/client policies: only backend secret access. No Supabase Auth.
commit;
