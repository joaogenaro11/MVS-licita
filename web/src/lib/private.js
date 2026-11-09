// Acesso individual e dados pessoais/da equipe.
//
// - Com Supabase configurado (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY): login individual
//   (Supabase Auth: senha com hash bcrypt, sessão JWT, limite de tentativas) e Row Level Security.
//   A chave publicável vai para o navegador por definição; a proteção está nas políticas RLS
//   (docs/supabase.sql). Sem login, nenhuma tabela é acessível.
//     * Pessoal (cada usuário vê só o seu): favoritos, filtro de portfólio, filtros, buscas salvas.
//     * Equipe (todos os usuários ativos): status comercial, responsável, observação, próximo
//       acompanhamento e configuração comercial (órgãos prioritários, parceiros, notas).
// - Sem Supabase (desenvolvimento local / teste automatizado): tudo fica neste navegador (localStorage).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const URL = import.meta.env.VITE_SUPABASE_URL
const KEY = import.meta.env.VITE_SUPABASE_ANON_KEY
export const SUPABASE_ENABLED = Boolean(URL && KEY)
export const LOGIN_DOMAIN = 'radar-tls.invalid'

let clientPromise = null
export function getClient() {
  if (!SUPABASE_ENABLED) return null
  if (!clientPromise) {
    clientPromise = import('@supabase/supabase-js').then(({ createClient }) =>
      createClient(URL, KEY, { auth: { persistSession: true, autoRefreshToken: true, storageKey: 'radar-tls-auth' } }))
  }
  return clientPromise
}

const LS_TRACK = 'radar-tls.tracking.v1'
const LS_CONF = 'radar-tls.config.v1'
const LS_PREFS = 'radar-tls.prefs.v1'
const LS_LOCK = 'radar-tls.login-lock.v1'
export const lsGet = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d } catch { return d } }
export const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* modo privado */ } }

export const EMPTY_CONFIG = { priority_orgs: [], partners: [], vendor_notes: {} }
export const STATUS_COMERCIAL = ['Novo', 'Em análise', 'Qualificado', 'Parceiro acionado', 'Proposta', 'Ganho', 'Perdido', 'Descartado']

/** Usuário -> e-mail técnico do Supabase Auth (nenhum e-mail é enviado: domínio reservado). */
export const loginEmail = (usuario) => {
  const u = (usuario || '').trim().toLowerCase()
  return u.includes('@') ? u : `${u}@${LOGIN_DOMAIN}`
}

const MAX_TENTATIVAS = 5
const BLOQUEIO_S = 60

/** Limite de tentativas no navegador (além do limite do próprio Supabase Auth, por IP). */
export function loginLockState(now = Date.now()) {
  const st = lsGet(LS_LOCK, { falhas: 0, ate: 0 })
  return { ...st, bloqueado: st.ate > now, restante_s: Math.max(0, Math.ceil((st.ate - now) / 1000)) }
}
function registerFailure() {
  const st = lsGet(LS_LOCK, { falhas: 0, ate: 0 })
  const falhas = (st.falhas || 0) + 1
  lsSet(LS_LOCK, falhas >= MAX_TENTATIVAS ? { falhas: 0, ate: Date.now() + BLOQUEIO_S * 1000 } : { falhas, ate: 0 })
}

const traduzErro = (e) => {
  const m = e?.message || String(e)
  if (/invalid login credentials/i.test(m)) return 'Usuário ou senha incorretos.'
  if (/banned|user is banned/i.test(m)) return 'Acesso desativado. Fale com o administrador.'
  if (/rate limit|too many/i.test(m)) return 'Muitas tentativas. Aguarde alguns minutos e tente de novo.'
  if (/failed to fetch|network/i.test(m)) return 'Sem conexão com o servidor de login.'
  return m
}

export function useAuth() {
  const [session, setSession] = useState(null)
  const [perfil, setPerfil] = useState(null)
  const [ready, setReady] = useState(!SUPABASE_ENABLED)
  const uid = session?.user?.id

  useEffect(() => {
    if (!SUPABASE_ENABLED) return
    let sub
    getClient().then((sb) => {
      sb.auth.getSession().then(({ data }) => { setSession(data.session); if (!data.session) setReady(true) })
      sub = sb.auth.onAuthStateChange((_e, s) => setSession(s)).data.subscription
    })
    return () => sub?.unsubscribe()
  }, [])

  const loadPerfil = useCallback(async () => {
    if (!uid) { setPerfil(null); return }
    const sb = await getClient()
    const { data, error } = await sb.from('perfis').select('user_id,usuario,nome,papel,ativo,trocar_senha').eq('user_id', uid).maybeSingle()
    setPerfil(error ? { erro: error.message } : (data || { ausente: true }))
    setReady(true)
  }, [uid])
  useEffect(() => { if (SUPABASE_ENABLED) loadPerfil() }, [loadPerfil])

  const signIn = useCallback(async (usuario, password) => {
    const lock = loginLockState()
    if (lock.bloqueado) throw new Error(`Muitas tentativas. Tente de novo em ${lock.restante_s} s.`)
    const sb = await getClient()
    const { error } = await sb.auth.signInWithPassword({ email: loginEmail(usuario), password })
    if (error) { registerFailure(); throw new Error(traduzErro(error)) }
    lsSet(LS_LOCK, { falhas: 0, ate: 0 })
  }, [])
  const signOut = useCallback(async () => {
    const sb = await getClient()
    await sb.auth.signOut()
    setPerfil(null)
  }, [])
  const trocarSenha = useCallback(async (atual, nova) => {
    const sb = await getClient()
    const { error } = await sb.rpc('trocar_minha_senha', { p_atual: atual, p_nova: nova })
    if (error) throw new Error(traduzErro(error))
    await loadPerfil()
  }, [loadPerfil])

  return {
    enabled: SUPABASE_ENABLED, session, user: session?.user, perfil, ready,
    isAdmin: perfil?.papel === 'admin' && perfil?.ativo, signIn, signOut, trocarSenha, reload: loadPerfil,
  }
}

/** Favoritos PESSOAIS (tabela favoritos, por usuário) ou locais sem Supabase. */
export function useFavoritos(auth) {
  const shared = SUPABASE_ENABLED && Boolean(auth.user)
  const [ids, setIds] = useState(() => new Set())
  const [error, setError] = useState(null)
  useEffect(() => {
    if (!SUPABASE_ENABLED) {
      const local = lsGet(LS_TRACK, {})
      setIds(new Set(Object.keys(local).filter((k) => local[k]?.favorito)))
      return
    }
    if (!auth.user) { setIds(new Set()); return }
    let alive = true
    getClient().then(async (sb) => {
      const { data, error: e } = await sb.from('favoritos').select('item_id')
      if (!alive) return
      if (e) { setError(e.message); return }
      setIds(new Set((data || []).map((r) => r.item_id)))
    })
    return () => { alive = false }
  }, [auth.user])

  const toggle = useCallback(async (r) => {
    const on = !ids.has(r.id)
    const next = new Set(ids)
    if (on) next.add(r.id); else next.delete(r.id)
    setIds(next)
    if (!shared) {
      const local = lsGet(LS_TRACK, {})
      local[r.id] = { ...(local[r.id] || { item_id: r.id, tipo: r.tipo }), favorito: on }
      lsSet(LS_TRACK, local)
      return
    }
    const sb = await getClient()
    const { error: e } = on
      ? await sb.from('favoritos').upsert({ item_id: r.id, tipo: r.tipo })
      : await sb.from('favoritos').delete().eq('item_id', r.id)
    if (e) { setError(e.message); setIds(ids) }
  }, [ids, shared])

  const isFav = useCallback((id) => ids.has(id), [ids])
  return { ids, isFav, toggle, shared, error, setIds }
}

/** Preferências PESSOAIS: filtro de portfólio, filtros, ordenação e buscas salvas. */
export function usePreferencias(auth) {
  const shared = SUPABASE_ENABLED && Boolean(auth.user)
  const [prefs, setPrefs] = useState(() => (SUPABASE_ENABLED ? {} : lsGet(LS_PREFS, {})))
  const [loaded, setLoaded] = useState(!SUPABASE_ENABLED)
  const timer = useRef(null)
  useEffect(() => {
    if (!SUPABASE_ENABLED) return
    if (!auth.user) { setPrefs({}); setLoaded(false); return }
    getClient().then(async (sb) => {
      const { data } = await sb.from('preferencias').select('data').maybeSingle()
      setPrefs(data?.data || {})
      setLoaded(true)
    })
  }, [auth.user])

  const update = useCallback((patch) => {
    setPrefs((old) => {
      const next = { ...old, ...patch }
      clearTimeout(timer.current)
      timer.current = setTimeout(async () => {
        if (!shared) { lsSet(LS_PREFS, next); return }
        const sb = await getClient()
        await sb.from('preferencias').upsert({ data: next, atualizado_em: new Date().toISOString() })
      }, 600)
      return next
    })
  }, [shared])
  return { prefs, update, loaded, shared }
}

/** Acompanhamento da EQUIPE por item (status, responsável, observação, próximo acompanhamento). */
export function useTracking(auth) {
  const shared = SUPABASE_ENABLED && Boolean(auth.user)
  const [rows, setRows] = useState(() => (SUPABASE_ENABLED ? {} : lsGet(LS_TRACK, {})))
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!SUPABASE_ENABLED) { setRows(lsGet(LS_TRACK, {})); return }
    if (!auth.user) { setRows({}); return }
    let alive = true
    getClient().then(async (sb) => {
      const { data, error: e } = await sb.from('tracking').select('*')
      if (!alive) return
      if (e) { setError(e.message); return }
      setRows(Object.fromEntries((data || []).map((r) => [r.item_id, r])))
    })
    return () => { alive = false }
  }, [auth.user])

  const save = useCallback(async (itemId, tipo, patch) => {
    const next = { ...(rows[itemId] || { item_id: itemId, tipo }), ...patch, item_id: itemId, tipo }
    if (!shared) {
      const all = { ...lsGet(LS_TRACK, {}), [itemId]: { ...(lsGet(LS_TRACK, {})[itemId] || {}), ...next } }
      setRows(all); lsSet(LS_TRACK, all)
      return
    }
    const sb = await getClient()
    const { favorito: _f, ...rest } = next
    const payload = { ...rest, updated_at: new Date().toISOString(), updated_by: auth.perfil?.usuario || auth.user.email }
    const { data, error: e } = await sb.from('tracking').upsert(payload).select().single()
    if (e) { setError(e.message); throw e }
    setRows((r) => ({ ...r, [itemId]: data }))
  }, [rows, shared, auth])

  return { rows, save, shared, error }
}

/** Migração única: o que estava salvo neste navegador antes dos acessos individuais (favoritos,
 *  preferências e anotações) passa para o ADMINISTRADOR na 1ª vez que ele entra neste navegador. */
export function useMigracaoLocal(auth, favoritos, prefs, tracking) {
  useEffect(() => {
    if (!SUPABASE_ENABLED || !auth.isAdmin || !prefs.loaded || prefs.prefs.migrado_navegador) return
    const local = lsGet(LS_TRACK, {})
    const favs = Object.values(local).filter((r) => r?.favorito && r.item_id)
    const notas = Object.values(local).filter((r) => r?.item_id && (r.status || r.observacao || r.responsavel))
    ;(async () => {
      const sb = await getClient()
      if (favs.length) {
        await sb.from('favoritos').upsert(favs.map((r) => ({ item_id: r.item_id, tipo: r.tipo })))
        favoritos.setIds((old) => new Set([...old, ...favs.map((r) => r.item_id)]))
      }
      for (const r of notas) {
        if (tracking.rows[r.item_id]) continue
        await tracking.save(r.item_id, r.tipo, { status: r.status || null, responsavel: r.responsavel || null,
          observacao: r.observacao || null, proximo_acompanhamento: r.proximo_acompanhamento || null }).catch(() => {})
      }
      const localPrefs = lsGet(LS_PREFS, {})
      prefs.update({ ...localPrefs, migrado_navegador: new Date().toISOString(), migrados: { favoritos: favs.length, anotacoes: notas.length } })
    })()
  }, [auth.isAdmin, prefs.loaded]) // eslint-disable-line react-hooks/exhaustive-deps
}

/** Configuração comercial da equipe (órgãos prioritários, parceiros, notas por fabricante). */
export function useCommercialConfig(auth) {
  const shared = SUPABASE_ENABLED && Boolean(auth.user)
  const [config, setConfig] = useState(() => (SUPABASE_ENABLED ? EMPTY_CONFIG : { ...EMPTY_CONFIG, ...lsGet(LS_CONF, {}) }))
  useEffect(() => {
    if (!SUPABASE_ENABLED) { setConfig({ ...EMPTY_CONFIG, ...lsGet(LS_CONF, {}) }); return }
    if (!auth.user) { setConfig(EMPTY_CONFIG); return }
    getClient().then(async (sb) => {
      const { data } = await sb.from('radar_config').select('data').eq('id', 'comercial').maybeSingle()
      setConfig({ ...EMPTY_CONFIG, ...(data?.data || {}) })
    })
  }, [auth.user])
  const save = useCallback(async (cfg) => {
    setConfig(cfg)
    if (!shared) { lsSet(LS_CONF, cfg); return }
    const sb = await getClient()
    const { error } = await sb.from('radar_config').upsert({ id: 'comercial', data: cfg, updated_at: new Date().toISOString(), updated_by: auth.perfil?.usuario })
    if (error) throw error
  }, [shared, auth.perfil])
  return useMemo(() => ({ config, save, shared }), [config, save, shared])
}

/** Chamadas de administração (o banco recusa com 403 para quem não é admin). */
export const adminApi = {
  async listar() { return rpc('admin_listar_usuarios', {}) },
  async criar(usuario, nome, papel) { return (await rpc('admin_criar_usuario', { p_usuario: usuario, p_nome: nome, p_papel: papel }))[0] },
  async redefinir(userId) { return rpc('admin_redefinir_senha', { p_user_id: userId }) },
  async verSenha(userId) { return rpc('admin_ver_senha_temporaria', { p_user_id: userId }) },
  async ativo(userId, ativo) { return rpc('admin_definir_ativo', { p_user_id: userId, p_ativo: ativo }) },
  async salvarOfertas(json) { return rpc('admin_salvar_ofertas', { p_data: json }) },
  async ofertasAtuais() {
    const sb = await getClient()
    const { data, error } = await sb.from('radar_ofertas').select('versao,atualizado_em,atualizado_por').eq('id', 'atual').maybeSingle()
    if (error) throw new Error(error.message)
    return data
  },
}
async function rpc(fn, args) {
  const sb = await getClient()
  const { data, error } = await sb.rpc(fn, args)
  if (error) throw new Error(traduzErro(error))
  return data
}

/** Converte o texto YAML simples da configuração privada (seções de listas/notas). */
export function parseConfigText(text) {
  const cfg = { priority_orgs: [], partners: [], vendor_notes: {} }
  let section = null
  for (const raw of (text || '').split('\n')) {
    const line = raw.replace(/\s+#.*$/, '').replace(/\r/, '')
    if (!line.trim() || line.trim().startsWith('#')) continue
    const top = line.match(/^([a-z_]+):\s*$/)
    if (top) { section = top[1]; continue }
    if (!/^\s/.test(line)) { section = null; continue }
    if (section === 'priority_orgs' || section === 'partners') {
      const m = line.match(/^\s*-\s*(.+)$/)
      if (m) cfg[section].push(m[1].trim().replace(/^["']|["']$/g, ''))
    } else if (section === 'vendor_notes') {
      const m = line.match(/^\s+([^:]+):\s*(.+)$/)
      if (m) cfg.vendor_notes[m[1].trim()] = m[2].trim().replace(/^["']|["']$/g, '')
    }
  }
  return cfg
}

export function configToText(cfg) {
  const q = (s) => `"${String(s).replace(/"/g, "'")}"`
  return [
    'priority_orgs:', ...(cfg.priority_orgs || []).map((o) => `  - ${o}`),
    '', 'partners:', ...(cfg.partners || []).map((p) => `  - ${p}`),
    '', 'vendor_notes:', ...Object.entries(cfg.vendor_notes || {}).map(([k, v]) => `  ${k}: ${q(v)}`),
  ].join('\n')
}
