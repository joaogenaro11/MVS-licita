// Acesso individual e dados pessoais/da equipe.
//
// - Com Supabase configurado (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY): login individual
//   (Supabase Auth: senha com hash bcrypt, sessão JWT, limite de tentativas) e Row Level Security.
//   A chave publicável vai para o navegador por definição; a proteção está nas políticas RLS
//   (docs/supabase.sql). Sem login, nenhuma tabela é acessível.
//     * Pessoal (cada usuário vê só o seu): favoritos, filtro de portfólio, filtros, buscas salvas.
//     * CRM: cada usuário tem o próprio funil (etapa, próximo acompanhamento, código da oportunidade/SC,
//       valor, parceiro, histórico). Gestor/admin vê o de todos e pede acompanhamento a um vendedor.
//     * Equipe (todos os usuários ativos): configuração comercial (órgãos prioritários, parceiros, notas).
// - Sem Supabase (desenvolvimento local / teste automatizado): tudo fica neste navegador (localStorage).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { diffEventos, snapshotDe } from './crm.js'

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
const LS_CRM = 'radar-tls.crm.v1'
export const LOCAL_ME = 'local'
export const lsGet = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d } catch { return d } }
export const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* modo privado */ } }

export const EMPTY_CONFIG = { priority_orgs: [], partners: [], vendor_notes: {} }

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
    isAdmin: perfil?.papel === 'admin' && perfil?.ativo,
    isGestor: !SUPABASE_ENABLED || (['admin', 'gestor'].includes(perfil?.papel) && perfil?.ativo), signIn, signOut, trocarSenha, reload: loadPerfil,
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

/** CRM: cada usuário tem o seu funil (linha por oportunidade e dono). Gestor/admin vê todos,
 *  edita qualquer um e pede para um vendedor acompanhar (atribuição). Sem Supabase: localStorage. */
export function useCRM(auth) {
  const shared = SUPABASE_ENABLED && Boolean(auth.user)
  const me = auth.user?.id || LOCAL_ME
  const [rows, setRows] = useState([])
  const [equipe, setEquipe] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(null)
  const local = () => lsGet(LS_CRM, { rows: [], eventos: [] })

  const reload = useCallback(async () => {
    if (!SUPABASE_ENABLED) {
      setRows(local().rows)
      setEquipe([{ user_id: LOCAL_ME, usuario: 'local', nome: 'Você (neste navegador)', papel: 'admin' }])
      setLoaded(true)
      return
    }
    if (!auth.user) { setRows([]); setEquipe([]); setLoaded(false); return }
    const sb = await getClient()
    const [a, b] = await Promise.all([sb.from('crm').select('*').order('atualizado_em', { ascending: false }).limit(5000), sb.rpc('equipe')])
    if (a.error) setError(a.error.message); else { setRows(a.data || []); setError(null) }
    if (!b.error) setEquipe(b.data || [])
    setLoaded(true)
  }, [auth.user])
  useEffect(() => { reload() }, [reload])

  /** Cria ou altera a linha de `dono` para o item. `item` = registro do site (guarda o retrato)
   *  ou {id, tipo} quando a oportunidade já saiu da base publicada. */
  const salvar = useCallback(async (item, patch, dono = me) => {
    const atual = rows.find((c) => c.item_id === item.id && c.dono === dono)
    const snap = item.orgao || item.objeto ? { snapshot: snapshotDe(item) } : {}
    if (!shared) {
      const st = local()
      const agora = new Date().toISOString()
      const novo = { ...(atual || { id: `local-${Date.now()}`, item_id: item.id, tipo: item.tipo, dono, etapa: 'novo', criado_em: agora }),
        ...snap, ...patch, atualizado_em: agora, atualizado_por: me }
      if (novo.atribuido_por && (!atual || atual.atribuido_por !== novo.atribuido_por || atual.mensagem_atribuicao !== novo.mensagem_atribuicao)) {
        novo.atribuido_em = agora
        if (atual) novo.visto_em = null
      }
      st.eventos = [...st.eventos, ...diffEventos(atual, novo, me, agora)]
      st.rows = [novo, ...st.rows.filter((c) => c.id !== novo.id)]
      lsSet(LS_CRM, st); setRows(st.rows)
      return novo
    }
    const sb = await getClient()
    const q = atual
      ? sb.from('crm').update({ ...snap, ...patch }).eq('id', atual.id)
      : sb.from('crm').insert({ item_id: item.id, tipo: item.tipo, dono, ...snap, ...patch })
    const { data, error: e } = await q.select().single()
    if (e) { setError(e.message); throw new Error(e.message) }
    setRows((old) => [data, ...old.filter((c) => c.id !== data.id)])
    return data
  }, [rows, shared, me])

  const remover = useCallback(async (id) => {
    if (!shared) {
      const st = local()
      st.rows = st.rows.filter((c) => c.id !== id); st.eventos = st.eventos.filter((e) => e.crm_id !== id)
      lsSet(LS_CRM, st); setRows(st.rows); return
    }
    const sb = await getClient()
    const { error: e } = await sb.from('crm').delete().eq('id', id)
    if (e) throw new Error(e.message)
    setRows((old) => old.filter((c) => c.id !== id))
  }, [shared])

  const marcarVisto = useCallback(async (c) => {
    const visto_em = new Date().toISOString()
    if (!shared) {
      const st = local()
      st.rows = st.rows.map((x) => (x.id === c.id ? { ...x, visto_em } : x)); lsSet(LS_CRM, st); setRows(st.rows); return
    }
    const sb = await getClient()
    const { data, error: e } = await sb.from('crm').update({ visto_em }).eq('id', c.id).select().single()
    if (!e) setRows((old) => old.map((x) => (x.id === data.id ? data : x)))
  }, [shared])

  const eventos = useCallback(async (crmId) => {
    if (!shared) return local().eventos.filter((e) => e.crm_id === crmId).sort((a, b) => b.criado_em.localeCompare(a.criado_em))
    const sb = await getClient()
    const { data, error: e } = await sb.from('crm_eventos').select('*').eq('crm_id', crmId).order('criado_em', { ascending: false }).limit(200)
    if (e) throw new Error(e.message)
    return data || []
  }, [shared])

  const nota = useCallback(async (crmId, texto) => {
    if (!shared) {
      const st = local()
      st.eventos.push({ id: `n-${Date.now()}`, crm_id: crmId, autor: me, tipo: 'nota', texto, criado_em: new Date().toISOString() })
      lsSet(LS_CRM, st); return
    }
    const sb = await getClient()
    const { error: e } = await sb.from('crm_eventos').insert({ crm_id: crmId, autor: me, tipo: 'nota', texto })
    if (e) throw new Error(e.message)
  }, [shared, me])

  const nomes = useMemo(() => Object.fromEntries(equipe.map((u) => [u.user_id, u.nome || u.usuario])), [equipe])
  const nomeDe = useCallback((id) => (id === me ? (nomes[id] ? `${nomes[id]} (você)` : 'Você') : (nomes[id] || 'usuário removido')), [nomes, me])
  const doItem = useCallback((itemId) => rows.filter((c) => c.item_id === itemId), [rows])
  const meus = useMemo(() => rows.filter((c) => c.dono === me), [rows, me])

  return useMemo(() => ({ rows, meus, equipe, me, shared, loaded, error, isGestor: Boolean(auth.isGestor),
    salvar, remover, marcarVisto, eventos, nota, nomeDe, doItem, reload }),
  [rows, meus, equipe, me, shared, loaded, error, auth.isGestor, salvar, remover, marcarVisto, eventos, nota, nomeDe, doItem, reload])
}

/** Migração única: o que estava salvo neste navegador antes dos acessos individuais (favoritos,
 *  preferências e anotações) passa para o usuário na 1ª vez que ele entra neste navegador
 *  (as anotações viram linhas do CRM dele). */
const STATUS_PARA_ETAPA = { 'Em análise': 'qualificando', Qualificado: 'qualificando', 'Parceiro acionado': 'qualificando',
  Proposta: 'proposta', Ganho: 'ganho', Perdido: 'perdido', Descartado: 'descartado' }
export function useMigracaoLocal(auth, favoritos, prefs, crm) {
  useEffect(() => {
    if (!SUPABASE_ENABLED || !auth.user || !prefs.loaded || !crm.loaded || prefs.prefs.migrado_navegador) return
    const local = lsGet(LS_TRACK, {})
    const favs = Object.values(local).filter((r) => r?.favorito && r.item_id)
    const notas = Object.values(local).filter((r) => r?.item_id && (r.status || r.observacao || r.proximo_acompanhamento))
    ;(async () => {
      const sb = await getClient()
      if (favs.length) {
        await sb.from('favoritos').upsert(favs.map((r) => ({ item_id: r.item_id, tipo: r.tipo })))
        favoritos.setIds((old) => new Set([...old, ...favs.map((r) => r.item_id)]))
      }
      for (const r of notas) {
        if (crm.meus.some((c) => c.item_id === r.item_id)) continue
        await crm.salvar({ id: r.item_id, tipo: r.tipo }, { etapa: STATUS_PARA_ETAPA[r.status] || 'novo',
          observacao: [r.responsavel ? `Responsável: ${r.responsavel}` : '', r.observacao || ''].filter(Boolean).join('\n') || null,
          proximo_acompanhamento: r.proximo_acompanhamento || null }).catch(() => {})
      }
      const localPrefs = lsGet(LS_PREFS, {})
      prefs.update({ ...localPrefs, migrado_navegador: new Date().toISOString(), migrados: { favoritos: favs.length, anotacoes: notas.length } })
    })()
  }, [auth.user, prefs.loaded, crm.loaded]) // eslint-disable-line react-hooks/exhaustive-deps
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
  async papel(userId, papel) { return rpc('admin_definir_papel', { p_user_id: userId, p_papel: papel }) },
  async salvarBase(id, json) { return rpc('admin_salvar_base', { p_id: id, p_data: json }) },
  async basesInfo() { return rpc('admin_bases_info', {}) },
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
