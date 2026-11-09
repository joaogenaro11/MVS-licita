// Dados exibidos pelo site.
// - Produção (Supabase configurado): lidos da tabela radar_export SOMENTE após o login
//   (a classificação deriva da base de ofertas privada; nada disso fica público no GitHub Pages).
// - Desenvolvimento local / teste automatizado: arquivos em web/public/data (gerados pelo coletor).
import { getClient, SUPABASE_ENABLED } from './private.js'

const BASE = import.meta.env.BASE_URL + 'data/'

async function getJson(name) {
  const res = await fetch(BASE + name, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`)
  return res.json()
}

async function loadSupabase() {
  const sb = await getClient()
  const { data, error } = await sb.from('radar_export').select('nome,parte,data').order('nome').order('parte')
  if (error) throw new Error(error.message)
  const by = { oportunidades: [], atas: [], meta: null }
  for (const row of data || []) {
    if (row.nome === 'meta') by.meta = row.data
    else if (by[row.nome]) by[row.nome].push(...(row.data?.items || []))
  }
  if (!by.meta) throw new Error('Os dados ainda não foram publicados (aguarde a próxima coleta)')
  const dedup = (list) => [...new Map(list.map((r) => [r.id, r])).values()]
  return { meta: by.meta, items: dedup(by.oportunidades), atas: dedup(by.atas) }
}

export async function loadAll() {
  if (SUPABASE_ENABLED) return loadSupabase()
  const [meta, opps, atas] = await Promise.all([getJson('meta.json'), getJson('opportunities.json'), getJson('atas.json')])
  return { meta, items: opps.items || [], atas: atas.items || [] }
}
