-- =============================================================================
-- RADAR TLS — banco Supabase (plano gratuito): acessos individuais, dados pessoais e dados do site
-- Idempotente: pode ser executado de novo (SQL Editor > New query > Run).
--
-- Modelo de segurança
--  * Login individual (Supabase Auth: senha com hash bcrypt, sessão JWT, limite de tentativas do Auth).
--    O usuário entra com o NOME DE USUÁRIO; internamente o e-mail técnico é <usuario>@radar-tls.invalid
--    (domínio reservado: nenhum e-mail é enviado). Cadastro público desativado.
--  * public.perfis diz quem pode usar o Radar (ativo) e quem é administrador (papel = 'admin').
--    Criar, redefinir senha, desativar e reativar: só pela Edge Function "admin-usuarios" (chave de serviço).
--  * Dados compartilhados (todos os usuários ativos): radar_export (oportunidades/atas classificadas),
--    tracking (status comercial, responsável, observação, próximo acompanhamento), radar_config.
--  * Dados pessoais (cada um vê só os seus): favoritos, preferencias (filtros, buscas salvas, visualização).
--  * Base de ofertas TLS (radar_ofertas): privada; o coletor lê com a chave de serviço; na API só o admin lê.
--  * O papel "anon" (chave publicável do site) não acessa nenhuma tabela.
-- =============================================================================

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

-- ------------------------------------------------------------------ perfis
create table if not exists public.perfis (
  user_id uuid primary key references auth.users(id) on delete cascade,
  usuario text not null unique check (usuario ~ '^[a-z0-9][a-z0-9._-]{1,31}$'),
  nome text not null,
  papel text not null default 'usuario' check (papel in ('admin', 'usuario')),
  ativo boolean not null default true,
  trocar_senha boolean not null default true,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

-- Funções de autorização fora do schema exposto pela API (não viram /rpc)
create or replace function private.is_allowed() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.perfis where user_id = auth.uid() and ativo);
$$;
create or replace function private.is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.perfis where user_id = auth.uid() and ativo and papel = 'admin');
$$;
revoke execute on function private.is_allowed() from public, anon;
revoke execute on function private.is_admin() from public, anon;
grant execute on function private.is_allowed() to authenticated;
grant execute on function private.is_admin() to authenticated;

alter table public.perfis enable row level security;
drop policy if exists perfis_le on public.perfis;
create policy perfis_le on public.perfis for select to authenticated
  using (user_id = (select auth.uid()) or private.is_admin());
-- sem políticas de escrita: perfis só mudam pela Edge Function (chave de serviço)

-- ------------------------------------------------------------- dados pessoais
create table if not exists public.favoritos (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  item_id text not null,
  tipo text,
  criado_em timestamptz not null default now(),
  primary key (user_id, item_id)
);
alter table public.favoritos enable row level security;
drop policy if exists favoritos_proprios on public.favoritos;
create policy favoritos_proprios on public.favoritos for all to authenticated
  using (user_id = (select auth.uid()) and private.is_allowed())
  with check (user_id = (select auth.uid()) and private.is_allowed());

create table if not exists public.preferencias (
  user_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  data jsonb not null default '{}'::jsonb,
  atualizado_em timestamptz not null default now()
);
alter table public.preferencias enable row level security;
drop policy if exists preferencias_proprias on public.preferencias;
create policy preferencias_proprias on public.preferencias for all to authenticated
  using (user_id = (select auth.uid()) and private.is_allowed())
  with check (user_id = (select auth.uid()) and private.is_allowed());

-- ------------------------------------------------------ dados da equipe
create table if not exists public.tracking (
  item_id text primary key,
  tipo text not null,
  favorito boolean not null default false,   -- obsoleto: favoritos agora são por usuário (public.favoritos)
  status text,
  responsavel text,
  observacao text,
  proximo_acompanhamento date,
  updated_at timestamptz not null default now(),
  updated_by text
);
create table if not exists public.radar_config (
  id text primary key,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  updated_by text
);
alter table public.tracking enable row level security;
alter table public.radar_config enable row level security;
drop policy if exists tracking_rw on public.tracking;
create policy tracking_rw on public.tracking for all to authenticated
  using (private.is_allowed()) with check (private.is_allowed());
drop policy if exists config_rw on public.radar_config;
create policy config_rw on public.radar_config for all to authenticated
  using (private.is_allowed()) with check (private.is_allowed());

-- ----------------------------------------------- base de ofertas e dados do site
create table if not exists public.radar_ofertas (
  id text primary key,                 -- 'atual'
  data jsonb not null,                 -- conteúdo de ofertas_tls_radar.json
  versao text,
  atualizado_em timestamptz not null default now(),
  atualizado_por text
);
alter table public.radar_ofertas enable row level security;
drop policy if exists ofertas_admin_le on public.radar_ofertas;
create policy ofertas_admin_le on public.radar_ofertas for select to authenticated using (private.is_admin());

create table if not exists public.radar_export (
  nome text not null,                  -- 'oportunidades' | 'atas' | 'meta'
  parte int not null default 0,
  gerado_em timestamptz,
  data jsonb not null,
  primary key (nome, parte)
);
alter table public.radar_export enable row level security;
drop policy if exists export_le on public.radar_export;
create policy export_le on public.radar_export for select to authenticated using (private.is_allowed());

-- ------------------------------------------------ versão anterior (allowlist por e-mail)
drop function if exists public.is_allowed();
drop table if exists public.allowed_users;

-- ------------------------------------------------------------------ permissões
revoke all on public.perfis, public.favoritos, public.preferencias, public.tracking, public.radar_config,
  public.radar_ofertas, public.radar_export from anon;
revoke insert, update, delete on public.perfis, public.radar_ofertas, public.radar_export from authenticated;
grant select on public.perfis, public.radar_ofertas, public.radar_export to authenticated;
grant select, insert, update, delete on public.favoritos, public.preferencias, public.tracking, public.radar_config to authenticated;

-- =============================================================================
-- Gestão de acessos (chamada pelo site via RPC). As funções que mexem em auth.* ficam no schema
-- private (SECURITY DEFINER); no schema public ficam só "invólucros" SECURITY INVOKER.
-- Senhas: geradas aqui (aleatórias, fortes), devolvidas UMA vez a quem pediu e guardadas só como
-- hash bcrypt (pgcrypto, mesmo formato do Supabase Auth). Nunca são gravadas em claro.
-- =============================================================================
create or replace function private.dominio_login() returns text language sql immutable set search_path = '' as $$ select 'radar-tls.invalid' $$;

create or replace function private.senha_aleatoria() returns text
language plpgsql volatile set search_path = '' as $$
declare
  chars constant text := 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
  b bytea := extensions.gen_random_bytes(16);
  s text := '';
begin
  for i in 0..15 loop
    s := s || substr(chars, 1 + (get_byte(b, i) % length(chars)), 1);
    if i in (3, 7, 11) then s := s || '-'; end if;
  end loop;
  return s;  -- 16 caracteres aleatórios em 4 blocos (ex.: Abcd-2345-...)
end $$;

create or replace function private.exigir_admin() returns void language plpgsql stable set search_path = '' as $$
begin
  if not private.is_admin() then
    raise exception 'acesso negado: somente administradores' using errcode = '42501';
  end if;
end $$;

create or replace function private.criar_usuario(p_usuario text, p_nome text, p_papel text default 'usuario')
returns table (user_id uuid, usuario text, senha_temporaria text)
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_id uuid := gen_random_uuid();
  v_usuario text := lower(trim(p_usuario));
  v_email text;
  v_senha text := private.senha_aleatoria();
begin
  -- auth.uid() nulo = SQL Editor do painel (papel anon/autenticado nunca chega aqui sem JWT: sem EXECUTE)
  if auth.uid() is not null then perform private.exigir_admin(); end if;
  if v_usuario !~ '^[a-z0-9][a-z0-9._-]{1,31}$' then
    raise exception 'usuário inválido: use 2 a 32 caracteres (letras minúsculas, números, ponto, hífen, sublinhado)';
  end if;
  if coalesce(trim(p_nome), '') = '' then raise exception 'informe o nome'; end if;
  if p_papel not in ('admin', 'usuario') then raise exception 'papel inválido'; end if;
  if exists (select 1 from public.perfis p where p.usuario = v_usuario) then raise exception 'usuário já existe'; end if;
  v_email := v_usuario || '@' || private.dominio_login();
  insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
                          raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
                          confirmation_token, recovery_token, email_change_token_new, email_change)
  values ('00000000-0000-0000-0000-000000000000', v_id, 'authenticated', 'authenticated', v_email,
          extensions.crypt(v_senha, extensions.gen_salt('bf', 10)), now(),
          '{"provider":"email","providers":["email"]}'::jsonb,
          jsonb_build_object('usuario', v_usuario, 'nome', trim(p_nome)), now(), now(), '', '', '', '');
  insert into auth.identities (user_id, provider_id, provider, identity_data, created_at, updated_at)
  values (v_id, v_id::text, 'email',
          jsonb_build_object('sub', v_id::text, 'email', v_email, 'email_verified', true, 'phone_verified', false), now(), now());
  insert into public.perfis (user_id, usuario, nome, papel, ativo, trocar_senha)
  values (v_id, v_usuario, trim(p_nome), p_papel, true, true);
  return query select v_id, v_usuario, v_senha;
end $$;

create or replace function private.redefinir_senha(p_user_id uuid)
returns text language plpgsql volatile security definer set search_path = '' as $$
declare v_senha text := private.senha_aleatoria();
begin
  perform private.exigir_admin();
  update auth.users set encrypted_password = extensions.crypt(v_senha, extensions.gen_salt('bf', 10)), updated_at = now()
   where id = p_user_id;
  if not found then raise exception 'usuário não encontrado'; end if;
  update public.perfis set trocar_senha = true, atualizado_em = now() where user_id = p_user_id;
  delete from auth.sessions where user_id = p_user_id;          -- encerra as sessões abertas
  return v_senha;
end $$;

create or replace function private.definir_ativo(p_user_id uuid, p_ativo boolean)
returns void language plpgsql volatile security definer set search_path = '' as $$
begin
  perform private.exigir_admin();
  if p_user_id = auth.uid() and not p_ativo then raise exception 'você não pode desativar o próprio acesso'; end if;
  update public.perfis set ativo = p_ativo, atualizado_em = now() where user_id = p_user_id;
  if not found then raise exception 'usuário não encontrado'; end if;
  -- data distante (o Supabase Auth não aceita 'infinity')
  update auth.users set banned_until = case when p_ativo then null else '2999-12-31 00:00:00+00'::timestamptz end, updated_at = now()
   where id = p_user_id;
  if not p_ativo then delete from auth.sessions where user_id = p_user_id; end if;
end $$;

create or replace function private.listar_usuarios()
returns table (user_id uuid, usuario text, nome text, papel text, ativo boolean, trocar_senha boolean,
               criado_em timestamptz, ultimo_acesso timestamptz)
language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.exigir_admin();
  return query select p.user_id, p.usuario, p.nome, p.papel, p.ativo, p.trocar_senha, p.criado_em, u.last_sign_in_at
                 from public.perfis p join auth.users u on u.id = p.user_id order by p.usuario;
end $$;

create or replace function private.trocar_minha_senha(p_atual text, p_nova text)
returns void language plpgsql volatile security definer set search_path = '' as $$
declare v_hash text;
begin
  if auth.uid() is null or not private.is_allowed() then raise exception 'acesso negado' using errcode = '42501'; end if;
  select encrypted_password into v_hash from auth.users where id = auth.uid();
  if v_hash is null or extensions.crypt(p_atual, v_hash) <> v_hash then raise exception 'senha atual incorreta'; end if;
  if length(p_nova) < 10 or p_nova !~ '[A-Za-z]' or p_nova !~ '[0-9]' then
    raise exception 'a nova senha precisa de ao menos 10 caracteres, com letras e números';
  end if;
  if p_nova = p_atual then raise exception 'a nova senha deve ser diferente da atual'; end if;
  update auth.users set encrypted_password = extensions.crypt(p_nova, extensions.gen_salt('bf', 10)), updated_at = now()
   where id = auth.uid();
  update public.perfis set trocar_senha = false, atualizado_em = now() where user_id = auth.uid();
end $$;

create or replace function private.salvar_ofertas(p_data jsonb)
returns text language plpgsql volatile security definer set search_path = '' as $$
declare v_user text;
begin
  perform private.exigir_admin();
  if jsonb_typeof(p_data -> 'ofertas') <> 'array' or jsonb_array_length(p_data -> 'ofertas') = 0
     or p_data -> 'marcas_logo' is null or p_data -> 'marcas_mvs' is null or p_data -> 'exclusoes_globais' is null then
    raise exception 'arquivo inválido: esperado ofertas_tls_radar.json (ofertas, marcas_logo, marcas_mvs, exclusoes_globais)';
  end if;
  select usuario into v_user from public.perfis where user_id = auth.uid();
  insert into public.radar_ofertas (id, data, versao, atualizado_em, atualizado_por)
  values ('atual', p_data, p_data ->> 'versao', now(), v_user)
  on conflict (id) do update set data = excluded.data, versao = excluded.versao,
                                 atualizado_em = excluded.atualizado_em, atualizado_por = excluded.atualizado_por;
  return coalesce(p_data ->> 'versao', '') || ' · ' || jsonb_array_length(p_data -> 'ofertas') || ' ofertas';
end $$;

revoke execute on all functions in schema private from public, anon;
grant execute on function private.is_allowed(), private.is_admin(), private.exigir_admin(),
  private.criar_usuario(text, text, text), private.redefinir_senha(uuid), private.definir_ativo(uuid, boolean),
  private.listar_usuarios(), private.trocar_minha_senha(text, text), private.salvar_ofertas(jsonb) to authenticated;

-- Invólucros expostos como /rest/v1/rpc/* (SECURITY INVOKER: a checagem fica nas funções privadas)
create or replace function public.admin_listar_usuarios()
returns table (user_id uuid, usuario text, nome text, papel text, ativo boolean, trocar_senha boolean,
               criado_em timestamptz, ultimo_acesso timestamptz)
language sql volatile security invoker set search_path = '' as $$ select * from private.listar_usuarios() $$;
create or replace function public.admin_criar_usuario(p_usuario text, p_nome text, p_papel text default 'usuario')
returns table (user_id uuid, usuario text, senha_temporaria text)
language sql volatile security invoker set search_path = '' as $$ select * from private.criar_usuario(p_usuario, p_nome, p_papel) $$;
create or replace function public.admin_redefinir_senha(p_user_id uuid) returns text
language sql volatile security invoker set search_path = '' as $$ select private.redefinir_senha(p_user_id) $$;
create or replace function public.admin_definir_ativo(p_user_id uuid, p_ativo boolean) returns void
language sql volatile security invoker set search_path = '' as $$ select private.definir_ativo(p_user_id, p_ativo) $$;
create or replace function public.admin_salvar_ofertas(p_data jsonb) returns text
language sql volatile security invoker set search_path = '' as $$ select private.salvar_ofertas(p_data) $$;
create or replace function public.trocar_minha_senha(p_atual text, p_nova text) returns void
language sql volatile security invoker set search_path = '' as $$ select private.trocar_minha_senha(p_atual, p_nova) $$;
revoke execute on function public.admin_listar_usuarios(), public.admin_criar_usuario(text, text, text),
  public.admin_redefinir_senha(uuid), public.admin_definir_ativo(uuid, boolean), public.admin_salvar_ofertas(jsonb),
  public.trocar_minha_senha(text, text) from public, anon;
grant execute on function public.admin_listar_usuarios(), public.admin_criar_usuario(text, text, text),
  public.admin_redefinir_senha(uuid), public.admin_definir_ativo(uuid, boolean), public.admin_salvar_ofertas(jsonb),
  public.trocar_minha_senha(text, text) to authenticated;

-- =============================================================================
-- Senha temporária visível para o admin (pedido do administrador)
-- A senha temporária (criação/redefinição) fica CRIPTOGRAFADA no Supabase Vault até a pessoa
-- criar a própria senha; aí é apagada. Também é apagada ao desativar o usuário.
-- Só o admin consegue ler (função com checagem de papel). Senhas pessoais nunca são guardadas.
-- =============================================================================
create table if not exists private.senhas_temporarias (
  user_id uuid primary key references auth.users(id) on delete cascade,
  secret_id uuid not null,
  criada_em timestamptz not null default now()
);
revoke all on private.senhas_temporarias from public, anon, authenticated;

create or replace function private.apagar_senha_temporaria(p_user_id uuid) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare v_secret uuid;
begin
  delete from private.senhas_temporarias where user_id = p_user_id returning secret_id into v_secret;
  if v_secret is not null then delete from vault.secrets where id = v_secret; end if;
end $$;

create or replace function private.guardar_senha_temporaria(p_user_id uuid, p_senha text) returns void
language plpgsql volatile security definer set search_path = '' as $$
begin
  perform private.apagar_senha_temporaria(p_user_id);
  insert into private.senhas_temporarias (user_id, secret_id)
  values (p_user_id, vault.create_secret(p_senha, 'radar-tls-senha-temporaria-' || p_user_id::text || '-' || extract(epoch from clock_timestamp())::bigint,
                                         'Senha temporária do Radar TLS (apagada quando o usuário cria a própria senha)'));
end $$;

create or replace function private.ver_senha_temporaria(p_user_id uuid) returns text
language plpgsql stable security definer set search_path = '' as $$
declare v_senha text;
begin
  perform private.exigir_admin();
  if not exists (select 1 from public.perfis where user_id = p_user_id and trocar_senha and ativo) then
    raise exception 'este usuário já criou a própria senha (ou está desativado): use "Redefinir senha" para gerar outra temporária';
  end if;
  select d.decrypted_secret into v_senha
    from private.senhas_temporarias s join vault.decrypted_secrets d on d.id = s.secret_id
   where s.user_id = p_user_id;
  if v_senha is null then
    raise exception 'senha temporária não guardada (usuário criado antes desta opção): use "Redefinir senha"';
  end if;
  return v_senha;
end $$;

-- criação, redefinição, troca e desativação passam a guardar/apagar a senha temporária
create or replace function private.criar_usuario(p_usuario text, p_nome text, p_papel text default 'usuario')
returns table (user_id uuid, usuario text, senha_temporaria text)
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_id uuid := gen_random_uuid();
  v_usuario text := lower(trim(p_usuario));
  v_email text;
  v_senha text := private.senha_aleatoria();
begin
  -- auth.uid() nulo = SQL Editor do painel (papel anon/autenticado nunca chega aqui sem JWT: sem EXECUTE)
  if auth.uid() is not null then perform private.exigir_admin(); end if;
  if v_usuario !~ '^[a-z0-9][a-z0-9._-]{1,31}$' then
    raise exception 'usuário inválido: use 2 a 32 caracteres (letras minúsculas, números, ponto, hífen, sublinhado)';
  end if;
  if coalesce(trim(p_nome), '') = '' then raise exception 'informe o nome'; end if;
  if p_papel not in ('admin', 'usuario') then raise exception 'papel inválido'; end if;
  if exists (select 1 from public.perfis p where p.usuario = v_usuario) then raise exception 'usuário já existe'; end if;
  v_email := v_usuario || '@' || private.dominio_login();
  insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
                          raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
                          confirmation_token, recovery_token, email_change_token_new, email_change)
  values ('00000000-0000-0000-0000-000000000000', v_id, 'authenticated', 'authenticated', v_email,
          extensions.crypt(v_senha, extensions.gen_salt('bf', 10)), now(),
          '{"provider":"email","providers":["email"]}'::jsonb,
          jsonb_build_object('usuario', v_usuario, 'nome', trim(p_nome)), now(), now(), '', '', '', '');
  insert into auth.identities (user_id, provider_id, provider, identity_data, created_at, updated_at)
  values (v_id, v_id::text, 'email',
          jsonb_build_object('sub', v_id::text, 'email', v_email, 'email_verified', true, 'phone_verified', false), now(), now());
  insert into public.perfis (user_id, usuario, nome, papel, ativo, trocar_senha)
  values (v_id, v_usuario, trim(p_nome), p_papel, true, true);
  perform private.guardar_senha_temporaria(v_id, v_senha);
  return query select v_id, v_usuario, v_senha;
end $$;

create or replace function private.redefinir_senha(p_user_id uuid)
returns text language plpgsql volatile security definer set search_path = '' as $$
declare v_senha text := private.senha_aleatoria();
begin
  if auth.uid() is not null then perform private.exigir_admin(); end if;
  update auth.users set encrypted_password = extensions.crypt(v_senha, extensions.gen_salt('bf', 10)), updated_at = now()
   where id = p_user_id;
  if not found then raise exception 'usuário não encontrado'; end if;
  update public.perfis set trocar_senha = true, atualizado_em = now() where user_id = p_user_id;
  delete from auth.sessions where user_id = p_user_id;          -- encerra as sessões abertas
  perform private.guardar_senha_temporaria(p_user_id, v_senha);
  return v_senha;
end $$;

create or replace function private.definir_ativo(p_user_id uuid, p_ativo boolean)
returns void language plpgsql volatile security definer set search_path = '' as $$
begin
  perform private.exigir_admin();
  if p_user_id = auth.uid() and not p_ativo then raise exception 'você não pode desativar o próprio acesso'; end if;
  update public.perfis set ativo = p_ativo, atualizado_em = now() where user_id = p_user_id;
  if not found then raise exception 'usuário não encontrado'; end if;
  -- data distante (o Supabase Auth não aceita 'infinity')
  update auth.users set banned_until = case when p_ativo then null else '2999-12-31 00:00:00+00'::timestamptz end, updated_at = now()
   where id = p_user_id;
  if not p_ativo then
    delete from auth.sessions where user_id = p_user_id;
    perform private.apagar_senha_temporaria(p_user_id);
  end if;
end $$;

create or replace function private.trocar_minha_senha(p_atual text, p_nova text)
returns void language plpgsql volatile security definer set search_path = '' as $$
declare v_hash text;
begin
  if auth.uid() is null or not private.is_allowed() then raise exception 'acesso negado' using errcode = '42501'; end if;
  select encrypted_password into v_hash from auth.users where id = auth.uid();
  if v_hash is null or extensions.crypt(p_atual, v_hash) <> v_hash then raise exception 'senha atual incorreta'; end if;
  if length(p_nova) < 10 or p_nova !~ '[A-Za-z]' or p_nova !~ '[0-9]' then
    raise exception 'a nova senha precisa de ao menos 10 caracteres, com letras e números';
  end if;
  if p_nova = p_atual then raise exception 'a nova senha deve ser diferente da atual'; end if;
  update auth.users set encrypted_password = extensions.crypt(p_nova, extensions.gen_salt('bf', 10)), updated_at = now()
   where id = auth.uid();
  update public.perfis set trocar_senha = false, atualizado_em = now() where user_id = auth.uid();
  perform private.apagar_senha_temporaria(auth.uid());   -- a temporária deixa de existir
end $$;

-- listagem passa a dizer se há senha temporária guardada
drop function if exists public.admin_listar_usuarios();
drop function if exists private.listar_usuarios();
create function private.listar_usuarios()
returns table (user_id uuid, usuario text, nome text, papel text, ativo boolean, trocar_senha boolean,
               criado_em timestamptz, ultimo_acesso timestamptz, senha_temporaria_guardada boolean)
language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.exigir_admin();
  return query select p.user_id, p.usuario, p.nome, p.papel, p.ativo, p.trocar_senha, p.criado_em, u.last_sign_in_at,
                      exists (select 1 from private.senhas_temporarias s where s.user_id = p.user_id)
                 from public.perfis p join auth.users u on u.id = p.user_id order by p.usuario;
end $$;
create function public.admin_listar_usuarios()
returns table (user_id uuid, usuario text, nome text, papel text, ativo boolean, trocar_senha boolean,
               criado_em timestamptz, ultimo_acesso timestamptz, senha_temporaria_guardada boolean)
language sql volatile security invoker set search_path = '' as $$ select * from private.listar_usuarios() $$;
create or replace function public.admin_ver_senha_temporaria(p_user_id uuid) returns text
language sql volatile security invoker set search_path = '' as $$ select private.ver_senha_temporaria(p_user_id) $$;

revoke execute on all functions in schema private from public, anon;
grant execute on function private.is_allowed(), private.is_admin(), private.exigir_admin(),
  private.criar_usuario(text, text, text), private.redefinir_senha(uuid), private.definir_ativo(uuid, boolean),
  private.listar_usuarios(), private.trocar_minha_senha(text, text), private.salvar_ofertas(jsonb),
  private.ver_senha_temporaria(uuid) to authenticated;
revoke execute on function public.admin_listar_usuarios(), public.admin_ver_senha_temporaria(uuid) from public, anon;
grant execute on function public.admin_listar_usuarios(), public.admin_ver_senha_temporaria(uuid) to authenticated;

-- Ao apagar a linha da senha temporária (inclusive quando o usuário é excluído direto no painel),
-- o segredo correspondente sai do Vault: nada fica órfão.
create or replace function private.tg_apaga_segredo_senha() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  delete from vault.secrets where id = old.secret_id;
  return old;
end $$;
revoke execute on function private.tg_apaga_segredo_senha() from public, anon, authenticated;
drop trigger if exists apaga_segredo_senha on private.senhas_temporarias;
create trigger apaga_segredo_senha after delete on private.senhas_temporarias
  for each row execute function private.tg_apaga_segredo_senha();
