// Dados comerciais internos: favoritos, status, responsável, observações, próximo
// acompanhamento e configuração comercial (órgãos prioritários, parceiros, notas).
//
// - Com Supabase configurado (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY): autenticação
//   real (Supabase Auth) + Row Level Security restrita aos usuários autorizados.
//   A chave "anon" é pública por definição; a proteção está nas políticas RLS (docs/supabase.sql).
// - Sem Supabase: favoritos e configuração ficam SOMENTE neste navegador (localStorage).
import { useCallback, useEffect, useMemo, useState } from 'react'

const URL = import.meta.env.VITE_SUPABASE_URL
const KEY = import.meta.env.VITE_SUPABASE_ANON_KEY
export const SUPABASE_ENABLED = Boolean(URL && KEY)

let clientPromise = null
function getClient() {
  if (!SUPABASE_ENABLED) return null
  if (!clientPromise) {
    clientPromise = import('@supabase/supabase-js').then(({ createClient }) =>
      createClient(URL, KEY, { auth: { persistSession: true, autoRefreshToken: true } }))
  }
  return clientPromise
}

const LS_TRACK = 'radar-tls.tracking.v1'
const LS_CONF = 'radar-tls.config.v1'
const lsGet = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d } catch { return d } }
const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* modo privado */ } }

export const EMPTY_CONFIG = { priority_orgs: [], partners: [], vendor_notes: {} }

export const STATUS_COMERCIAL = ['Novo', 'Em análise', 'Qualificado', 'Parceiro acionado', 'Proposta', 'Ganho', 'Perdido', 'Descartado']

export function useAuth() {
  const [session, setSession] = useState(null)
  const [ready, setReady] = useState(!SUPABASE_ENABLED)
  useEffect(() => {
    if (!SUPABASE_ENABLED) return
    let sub
    getClient().then((sb) => {
      sb.auth.getSession().then(({ data }) => { setSession(data.session); setReady(true) })
      sub = sb.auth.onAuthStateChange((_e, s) => setSession(s)).data.subscription
    })
    return () => sub?.unsubscribe()
  }, [])
  const signIn = useCallback(async (email, password) => {
    const sb = await getClient()
    const { error } = await sb.auth.signInWithPassword({ email, password })
    if (error) throw error
  }, [])
  const signOut = useCallback(async () => { const sb = await getClient(); await sb.auth.signOut() }, [])
  return { enabled: SUPABASE_ENABLED, session, user: session?.user, ready, signIn, signOut }
}

/** Registros de acompanhamento por item (compartilhados via Supabase ou locais). */
export function useTracking(user) {
  const shared = SUPABASE_ENABLED && Boolean(user)
  const [rows, setRows] = useState(() => (shared ? {} : lsGet(LS_TRACK, {})))
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!shared) { setRows(lsGet(LS_TRACK, {})); return }
    let alive = true
    getClient().then(async (sb) => {
      const { data, error: e } = await sb.from('tracking').select('*')
      if (!alive) return
      if (e) { setError(e.message); return }
      setRows(Object.fromEntries((data || []).map((r) => [r.item_id, r])))
    })
    return () => { alive = false }
  }, [shared])

  const save = useCallback(async (itemId, tipo, patch) => {
    const next = { ...(rows[itemId] || { item_id: itemId, tipo }), ...patch, item_id: itemId, tipo }
    if (!shared) {
      const all = { ...rows, [itemId]: next }
      setRows(all); lsSet(LS_TRACK, all)
      return
    }
    const sb = await getClient()
    const payload = { ...next, updated_at: new Date().toISOString(), updated_by: user.email }
    const { data, error: e } = await sb.from('tracking').upsert(payload).select().single()
    if (e) { setError(e.message); throw e }
    setRows((r) => ({ ...r, [itemId]: data }))
  }, [rows, shared, user])

  const isFav = useCallback((id) => Boolean(rows[id]?.favorito), [rows])
  return { rows, save, isFav, shared, error }
}

/** Configuração comercial privada (órgãos prioritários, parceiros, notas por fabricante). */
export function useCommercialConfig(user) {
  const shared = SUPABASE_ENABLED && Boolean(user)
  const [config, setConfig] = useState(() => (shared ? EMPTY_CONFIG : { ...EMPTY_CONFIG, ...lsGet(LS_CONF, {}) }))
  useEffect(() => {
    if (!shared) { setConfig({ ...EMPTY_CONFIG, ...lsGet(LS_CONF, {}) }); return }
    getClient().then(async (sb) => {
      const { data } = await sb.from('radar_config').select('data').eq('id', 'comercial').maybeSingle()
      setConfig({ ...EMPTY_CONFIG, ...(data?.data || {}) })
    })
  }, [shared])
  const save = useCallback(async (cfg) => {
    setConfig(cfg)
    if (!shared) { lsSet(LS_CONF, cfg); return }
    const sb = await getClient()
    const { error } = await sb.from('radar_config').upsert({ id: 'comercial', data: cfg, updated_at: new Date().toISOString(), updated_by: user.email })
    if (error) throw error
  }, [shared, user])
  return useMemo(() => ({ config, save, shared }), [config, save, shared])
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
