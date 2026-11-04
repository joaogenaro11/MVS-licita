-- =============================================================================
-- RADAR TLS — banco compartilhado para dados comerciais internos (Supabase, plano gratuito)
-- Execute no Supabase: SQL Editor > New query > cole este arquivo > Run.
--
-- Modelo de segurança:
--  * Cadastro público DESATIVADO (Authentication > Sign In / Providers > "Allow new users to sign up" = off).
--  * Usuários criados pelo administrador (Authentication > Users > Add user > Create new user).
--  * Somente e-mails presentes em public.allowed_users conseguem ler/gravar (RLS).
--  * A chave "anon" usada no site é pública por definição; sem login + allowlist, nenhuma linha é acessível.
-- =============================================================================

create table if not exists public.allowed_users (
  email text primary key
);

-- Cadastre os e-mails autorizados (minúsculas). Exemplo:
-- insert into public.allowed_users (email) values ('pessoa1@empresa.com'), ('pessoa2@empresa.com'), ('pessoa3@empresa.com');

create or replace function public.is_allowed() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.allowed_users
    where email = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;

-- Acompanhamento por oportunidade/ata (compartilhado entre os usuários autorizados)
create table if not exists public.tracking (
  item_id text primary key,                -- identificador oficial PNCP (contratação, ata, contrato) ou id de item de PCA
  tipo text not null,
  favorito boolean not null default false,
  status text,
  responsavel text,
  observacao text,
  proximo_acompanhamento date,
  updated_at timestamptz not null default now(),
  updated_by text
);

-- Configuração comercial privada (órgãos prioritários, parceiros, notas por fabricante)
create table if not exists public.radar_config (
  id text primary key,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  updated_by text
);

alter table public.allowed_users enable row level security;
alter table public.tracking enable row level security;
alter table public.radar_config enable row level security;

-- allowed_users: nenhuma política => inacessível pela API (gerencie pelo painel/SQL)

drop policy if exists tracking_rw on public.tracking;
create policy tracking_rw on public.tracking
  for all to authenticated
  using (public.is_allowed())
  with check (public.is_allowed());

drop policy if exists config_rw on public.radar_config;
create policy config_rw on public.radar_config
  for all to authenticated
  using (public.is_allowed())
  with check (public.is_allowed());

-- Nenhum acesso para o papel anônimo
revoke all on public.tracking, public.radar_config, public.allowed_users from anon;
grant select, insert, update, delete on public.tracking, public.radar_config to authenticated;
