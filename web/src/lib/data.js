// Carrega os arquivos estáticos gerados pelo coletor (publicados junto com o site).
const BASE = import.meta.env.BASE_URL + 'data/'

async function getJson(name) {
  const res = await fetch(BASE + name, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`)
  return res.json()
}

export async function loadAll() {
  const [meta, opps, atas] = await Promise.all([getJson('meta.json'), getJson('opportunities.json'), getJson('atas.json')])
  return { meta, items: opps.items || [], atas: atas.items || [] }
}
