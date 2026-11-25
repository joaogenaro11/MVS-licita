-- =============================================================================
-- CRM (pedido de 25/11/2026): cada vendedor tem o seu funil; o GESTOR (usuário master) vê todos,
-- filtra por vendedor e atribui oportunidades ("fulano pediu para você olhar").
--   papel 'gestor' = master comercial (não administra usuários); 'admin' também tem a visão do gestor.
--   crm          = uma linha por (oportunidade, dono): etapa, próximo acompanhamento, código da
--                  oportunidade (SC), valor do negócio, parceiro, motivo da perda, observação e um
--                  retrato da oportunidade (para continuar legível se ela sair do site).
--   crm_eventos  = histórico (criação, mudança de etapa, acompanhamento, atribuição, notas).
-- =============================================================================
alter table public.perfis drop constraint if exists perfis_papel_check;
alter table public.perfis add constraint perfis_papel_check check (papel in ('admin', 'gestor', 'usuario'));

create or replace function private.is_gestor() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.perfis where user_id = auth.uid() and ativo and papel in ('admin', 'gestor'));
$$;
revoke execute on function private.is_gestor() from public, anon;
grant execute on function private.is_gestor() to authenticated;

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
  if p_papel not in ('admin', 'gestor', 'usuario') then raise exception 'papel inválido'; end if;
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

create or replace function private.definir_papel(p_user_id uuid, p_papel text) returns void
language plpgsql volatile security definer set search_path = '' as $$
begin
  perform private.exigir_admin();
  if p_papel not in ('admin', 'gestor', 'usuario') then raise exception 'papel inválido'; end if;
  if p_user_id = auth.uid() and p_papel <> 'admin' then raise exception 'você não pode tirar o seu próprio papel de administrador'; end if;
  update public.perfis set papel = p_papel, atualizado_em = now() where user_id = p_user_id;
end $$;
create or replace function public.admin_definir_papel(p_user_id uuid, p_papel text) returns void
language sql volatile security invoker set search_path = '' as $$ select private.definir_papel(p_user_id, p_papel) $$;

-- Equipe visível a todos os usuários ativos (nomes para "atribuído por", seletor de vendedor)
create or replace function private.equipe() returns table (user_id uuid, usuario text, nome text, papel text)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not private.is_allowed() then raise exception 'acesso negado' using errcode = '42501'; end if;
  return query select p.user_id, p.usuario, p.nome, p.papel from public.perfis p where p.ativo order by p.nome;
end $$;
create or replace function public.equipe() returns table (user_id uuid, usuario text, nome text, papel text)
language sql stable security invoker set search_path = '' as $$ select * from private.equipe() $$;

revoke execute on function private.definir_papel(uuid, text), private.equipe(), private.criar_usuario(text, text, text) from public, anon;
grant execute on function private.definir_papel(uuid, text), private.equipe(), private.criar_usuario(text, text, text) to authenticated;
revoke execute on function public.admin_definir_papel(uuid, text), public.equipe() from public, anon;
grant execute on function public.admin_definir_papel(uuid, text), public.equipe() to authenticated;

create table if not exists public.crm (
  id uuid primary key default gen_random_uuid(),
  item_id text not null,
  tipo text not null,
  dono uuid not null references auth.users(id) on delete cascade,
  etapa text not null default 'novo'
    check (etapa in ('novo', 'qualificando', 'proposta', 'negociacao', 'ganho', 'perdido', 'descartado')),
  proximo_acompanhamento date,
  codigo_oportunidade text check (char_length(codigo_oportunidade) <= 60),
  valor_negocio numeric check (valor_negocio is null or valor_negocio >= 0),
  parceiro text check (char_length(parceiro) <= 120),
  motivo_perda text check (char_length(motivo_perda) <= 500),
  observacao text check (char_length(observacao) <= 4000),
  snapshot jsonb not null default '{}'::jsonb,
  atribuido_por uuid references auth.users(id) on delete set null,
  atribuido_em timestamptz,
  mensagem_atribuicao text check (char_length(mensagem_atribuicao) <= 500),
  visto_em timestamptz,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  atualizado_por uuid references auth.users(id) on delete set null,
  unique (item_id, dono)
);
create index if not exists crm_dono_idx on public.crm (dono);
create index if not exists crm_item_idx on public.crm (item_id);
create index if not exists crm_acomp_idx on public.crm (proximo_acompanhamento);

create table if not exists public.crm_eventos (
  id bigint generated always as identity primary key,
  crm_id uuid not null references public.crm(id) on delete cascade,
  autor uuid references auth.users(id) on delete set null,
  tipo text not null check (tipo in ('criado', 'etapa', 'acompanhamento', 'codigo', 'atribuido', 'nota')),
  texto text check (char_length(texto) <= 2000),
  criado_em timestamptz not null default now()
);
create index if not exists crm_eventos_crm_idx on public.crm_eventos (crm_id, criado_em);

alter table public.crm enable row level security;
alter table public.crm_eventos enable row level security;
drop policy if exists crm_le on public.crm;
create policy crm_le on public.crm for select to authenticated
  using (private.is_allowed() and (dono = (select auth.uid()) or private.is_gestor()));
drop policy if exists crm_insere on public.crm;
create policy crm_insere on public.crm for insert to authenticated
  with check (private.is_allowed() and (dono = (select auth.uid()) or private.is_gestor()));
drop policy if exists crm_altera on public.crm;
create policy crm_altera on public.crm for update to authenticated
  using (private.is_allowed() and (dono = (select auth.uid()) or private.is_gestor()))
  with check (private.is_allowed() and (dono = (select auth.uid()) or private.is_gestor()));
drop policy if exists crm_apaga on public.crm;
create policy crm_apaga on public.crm for delete to authenticated
  using (private.is_allowed() and (dono = (select auth.uid()) or private.is_gestor()));

drop policy if exists crm_eventos_le on public.crm_eventos;
create policy crm_eventos_le on public.crm_eventos for select to authenticated
  using (exists (select 1 from public.crm c where c.id = crm_id));          -- RLS de crm decide
drop policy if exists crm_eventos_insere on public.crm_eventos;
create policy crm_eventos_insere on public.crm_eventos for insert to authenticated
  with check (autor = (select auth.uid()) and tipo = 'nota' and exists (select 1 from public.crm c where c.id = crm_id));

-- Histórico automático: criação, atribuição, etapa, acompanhamento e código. Quem atribui é o
-- autor; quem altera também. Colunas de controle (atualizado_*) são preenchidas aqui.
create or replace function private.tg_crm() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_autor uuid := coalesce(auth.uid(), new.atualizado_por);
begin
  new.atualizado_em := now();
  new.atualizado_por := v_autor;
  if tg_op = 'INSERT' then
    if new.atribuido_por is not null and new.atribuido_por <> new.dono then
      new.atribuido_em := now();
    end if;
    return new;
  end if;
  if new.atribuido_por is not null and (new.atribuido_por is distinct from old.atribuido_por
      or new.mensagem_atribuicao is distinct from old.mensagem_atribuicao) then
    new.atribuido_em := now();
    new.visto_em := null;
  end if;
  return new;
end $$;
create or replace function private.tg_crm_eventos() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_autor uuid := coalesce(auth.uid(), new.atualizado_por);
begin
  if tg_op = 'INSERT' then
    insert into public.crm_eventos (crm_id, autor, tipo, texto) values (new.id, v_autor, 'criado', 'etapa: ' || new.etapa);
    if new.atribuido_por is not null and new.atribuido_por <> new.dono then
      insert into public.crm_eventos (crm_id, autor, tipo, texto) values (new.id, new.atribuido_por, 'atribuido', new.mensagem_atribuicao);
    end if;
    return new;
  end if;
  if new.etapa is distinct from old.etapa then
    insert into public.crm_eventos (crm_id, autor, tipo, texto) values (new.id, v_autor, 'etapa', old.etapa || ' → ' || new.etapa);
  end if;
  if new.proximo_acompanhamento is distinct from old.proximo_acompanhamento then
    insert into public.crm_eventos (crm_id, autor, tipo, texto)
    values (new.id, v_autor, 'acompanhamento', coalesce(to_char(new.proximo_acompanhamento, 'DD/MM/YYYY'), 'sem data'));
  end if;
  if new.codigo_oportunidade is distinct from old.codigo_oportunidade then
    insert into public.crm_eventos (crm_id, autor, tipo, texto) values (new.id, v_autor, 'codigo', new.codigo_oportunidade);
  end if;
  if new.atribuido_em is distinct from old.atribuido_em and new.atribuido_por is not null then
    insert into public.crm_eventos (crm_id, autor, tipo, texto) values (new.id, new.atribuido_por, 'atribuido', new.mensagem_atribuicao);
  end if;
  return new;
end $$;
drop trigger if exists crm_antes on public.crm;
create trigger crm_antes before insert or update on public.crm for each row execute function private.tg_crm();
drop trigger if exists crm_depois on public.crm;
create trigger crm_depois after insert or update on public.crm for each row execute function private.tg_crm_eventos();

-- =============================================================================
-- Bases comerciais privadas: atestados (filtro "Atestados") e territórios (carteira por vendedor).
-- Só o admin lê/grava pelo site; a coleta lê com a chave de serviço. Nunca vão para o repositório.
-- =============================================================================
create table if not exists public.radar_bases (
  id text primary key check (id in ('atestados', 'territorios')),
  data jsonb not null,
  versao text,
  atualizado_em timestamptz not null default now(),
  atualizado_por text
);
alter table public.radar_bases enable row level security;
drop policy if exists bases_admin_le on public.radar_bases;
create policy bases_admin_le on public.radar_bases for select to authenticated using (private.is_admin());

create or replace function private.salvar_base(p_id text, p_data jsonb) returns text
language plpgsql volatile security definer set search_path = '' as $$
declare v_user text; v_n int;
begin
  perform private.exigir_admin();
  if p_id = 'atestados' then
    if jsonb_typeof(p_data -> 'atestados') <> 'array' or jsonb_array_length(p_data -> 'atestados') = 0 then
      raise exception 'arquivo inválido: esperado {"atestados": [...]}';
    end if;
    v_n := jsonb_array_length(p_data -> 'atestados');
  elsif p_id = 'territorios' then
    if jsonb_typeof(p_data -> 'contas') <> 'array' or jsonb_array_length(p_data -> 'contas') = 0 then
      raise exception 'arquivo inválido: esperado {"contas": [...]}';
    end if;
    v_n := jsonb_array_length(p_data -> 'contas');
  else
    raise exception 'base desconhecida: %', p_id;
  end if;
  select usuario into v_user from public.perfis where user_id = auth.uid();
  insert into public.radar_bases (id, data, versao, atualizado_em, atualizado_por)
  values (p_id, p_data, p_data ->> 'versao', now(), v_user)
  on conflict (id) do update set data = excluded.data, versao = excluded.versao,
                                 atualizado_em = excluded.atualizado_em, atualizado_por = excluded.atualizado_por;
  return coalesce(p_data ->> 'versao', '') || ' · ' || v_n || ' registros';
end $$;
create or replace function public.admin_salvar_base(p_id text, p_data jsonb) returns text
language sql volatile security invoker set search_path = '' as $$ select private.salvar_base(p_id, p_data) $$;
revoke execute on function private.salvar_base(text, jsonb), public.admin_salvar_base(text, jsonb) from public, anon;
grant execute on function private.salvar_base(text, jsonb), public.admin_salvar_base(text, jsonb) to authenticated;

create or replace function public.admin_bases_info() returns table (id text, versao text, atualizado_em timestamptz, atualizado_por text, registros int)
language plpgsql stable security definer set search_path = '' as $$
begin
  perform private.exigir_admin();
  return query select b.id, b.versao, b.atualizado_em, b.atualizado_por,
                      coalesce(jsonb_array_length(b.data -> 'atestados'), jsonb_array_length(b.data -> 'contas'))
                 from public.radar_bases b order by b.id;
end $$;
revoke execute on function public.admin_bases_info() from public, anon;
grant execute on function public.admin_bases_info() to authenticated;
