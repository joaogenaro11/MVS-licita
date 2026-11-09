import { norm } from './format.js'
import { matchQuery, parseQuery, searchText } from './search.js'

/** Índice de busca textual (calculado uma vez por registro). */
export function indexRecord(r) {
  const c = r.classificacao || {}
  const parts = [
    r.id, r.numero, r.processo, r.objeto, r.info_complementar,
    r.orgao?.nome, r.unidade?.nome, r.unidade?.municipio, r.orgao_subrogado,
    (c.ofertas || []).join(' '), (c.termos || []).join(' '),
    (r.itens || []).map((i) => i.descricao).join(' '),
    (r.fornecedores || []).map((f) => f.nome).join(' '),
    r.fornecedor?.nome,
  ]
  r._q = searchText(parts)
  r._org = norm([r.orgao?.nome, r.unidade?.nome].filter(Boolean).join(' '))
  return r
}

/** Portfólio do registro: ['logo'], ['mvs'], ['logo','mvs'] ou ['transversal']. */
export const portfolioOf = (r) => r.classificacao?.portfolio || []

/** Filtro Tudo / Logo / MVS. "Logo IBM + MVS" aparece nos dois; Transversal só em Tudo. */
export function matchesPortfolio(r, p) {
  if (!p || p === 'tudo') return true
  return portfolioOf(r).includes(p)
}

export function portfolioCounts(records) {
  const n = { tudo: records.length, logo: 0, mvs: 0 }
  for (const r of records) {
    const pf = portfolioOf(r)
    if (pf.includes('logo')) n.logo += 1
    if (pf.includes('mvs')) n.mvs += 1
  }
  return n
}

export function portfolioLabel(pf = []) {
  if (pf.includes('logo') && pf.includes('mvs')) return 'Logo IBM + MVS'
  if (pf.includes('logo')) return 'Logo IBM'
  if (pf.includes('mvs')) return 'MVS'
  return pf.length ? 'Transversal' : ''
}

/** Aplica a busca: devolve os registros que casam, cada um com a lista de termos que casaram
 *  em `_casou` (usada para ordenar e para mostrar "casou: ..." no card). */
export function applySearch(records, q) {
  const parsed = parseQuery(q)
  if (parsed.mode === 'vazio') {
    for (const r of records) r._casou = null
    return records
  }
  const out = []
  for (const r of records) {
    const m = matchQuery(parsed, r._q || '')
    if (m && m.length) { r._casou = m.map((t) => t.label); out.push(r) } else r._casou = null
  }
  return out
}

/** Ordenação: primeiro quem casou MAIS termos da busca; depois o critério escolhido. */
export const bySearchThen = (sortFn) => (a, b) => ((b._casou?.length || 0) - (a._casou?.length || 0)) || sortFn(a, b)

export function matchesPriority(r, terms) {
  if (!terms || !terms.length) return false
  const cnpj = (r.orgao?.cnpj || '').replace(/\D/g, '')
  return terms.some((t) => {
    const digits = t.replace(/\D/g, '')
    if (digits.length >= 8 && /^[\d./-]+$/.test(t.trim())) return cnpj.startsWith(digits)
    const nt = norm(t)
    return nt && r._org.includes(nt)
  })
}

export function matchesPartner(r, partners) {
  if (!partners?.length) return []
  const names = [...(r.fornecedores || []).map((f) => f.nome), r.fornecedor?.nome].filter(Boolean).map(norm)
  return partners.filter((p) => {
    const np = norm(p)
    return np && names.some((n) => new RegExp(`(^|[^a-z0-9])${np.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`).test(n))
  })
}

const inRange = (v, min, max) => {
  if (min !== '' && min != null && !(v >= Number(min))) return false
  if (max !== '' && max != null && !(v <= Number(max))) return false
  return true
}

/** Filtro de oportunidades (contratações, PCA, contratos). Todos os critérios são opcionais. */
export function filterItems(items, f, ctx = {}) {
  const org = norm(f.orgao)
  const mun = norm(f.municipio)
  return applySearch(items, f.q).filter((r) => {
    const c = r.classificacao || {}
    if (!matchesPortfolio(r, f.portfolio)) return false
    if (org && !r._org.includes(org)) return false
    if (f.uf && r.unidade?.uf !== f.uf) return false
    if (mun && !norm(r.unidade?.municipio).includes(mun)) return false
    if (f.tipo && r.tipo !== f.tipo) return false
    if (f.modalidade && r.modalidade?.nome !== f.modalidade) return false
    if (f.estagio && r.estagio !== f.estagio) return false
    if (f.oferta && !(c.ofertas || []).includes(f.oferta)) return false
    if (f.selo && !(c.selos || []).some((x) => x.tipo === f.selo)) return false
    if ((f.vmin || f.vmax) && !inRange(r.valor_estimado ?? -1, f.vmin, f.vmax)) return false
    if (f.faixa && c.faixa !== f.faixa) return false
    if (f.familia && !(c.familias || []).includes(f.familia)) return false
    if (f.pubDe && !((r.data_publicacao || '') >= f.pubDe)) return false
    if (f.pubAte && !((r.data_publicacao || '').slice(0, 10) <= f.pubAte)) return false
    if (f.prazoAte) {
      const p = (r.data_encerramento_proposta || '').slice(0, 10)
      if (!p || p > f.prazoAte) return false
    }
    if (f.foco === 'df_federal' && !(r.orgao?.esfera === 'F' || r.unidade?.uf === 'DF')) return false
    if (f.prioritarios && !matchesPriority(r, ctx.priorityOrgs)) return false
    if (f.favoritos && !ctx.isFav?.(r.id)) return false
    return true
  })
}

export function filterAtas(atas, f, ctx = {}) {
  const org = norm(f.orgao)
  return applySearch(atas, f.q).filter((a) => {
    const c = a.classificacao || {}
    if (!matchesPortfolio(a, f.portfolio)) return false
    if (org && !a._org.includes(org)) return false
    if (f.vigencia === 'vigentes' && !['vigente', 'vence_em_breve'].includes(a.vigencia_status)) return false
    if (f.vigencia === 'vence_em_breve' && a.vigencia_status !== 'vence_em_breve') return false
    if (f.vigencia === 'encerradas' && !['encerrada', 'cancelada'].includes(a.vigencia_status)) return false
    if (f.vigencia === 'a_conferir' && !['inconsistente', 'sem_data'].includes(a.vigencia_status)) return false
    if (f.adesao && a.adesao_status !== f.adesao) return false
    if (f.oferta && !(c.ofertas || []).includes(f.oferta)) return false
    if (f.selo && !(c.selos || []).some((x) => x.tipo === f.selo)) return false
    if ((f.vmin || f.vmax) && !inRange(a.compra?.valor ?? -1, f.vmin, f.vmax)) return false
    if (f.faixa && c.faixa !== f.faixa) return false
    if (f.familia && !(c.familias || []).includes(f.familia)) return false
    if (f.uf && a.unidade?.uf !== f.uf) return false
    if (f.prioritarios && !matchesPriority(a, ctx.priorityOrgs)) return false
    if (f.favoritos && !ctx.isFav?.(a.id)) return false
    return true
  })
}

export const SORTS = {
  // aderência (maior primeiro); empate: pontos brutos; depois publicação mais recente
  score: (a, b) => ((b.classificacao?.aderencia || 0) - (a.classificacao?.aderencia || 0))
    || ((b.classificacao?.pontuacao || 0) - (a.classificacao?.pontuacao || 0))
    || (b.data_publicacao || '').localeCompare(a.data_publicacao || ''),
  valor: (a, b) => (b.valor_estimado ?? b.compra?.valor ?? 0) - (a.valor_estimado ?? a.compra?.valor ?? 0),
  publicacao: (a, b) => (b.data_publicacao || '').localeCompare(a.data_publicacao || ''),
  prazo: (a, b) => (a.data_encerramento_proposta || '9999').localeCompare(b.data_encerramento_proposta || '9999'),
  vencimento: (a, b) => (a.vigencia_fim || '9999').localeCompare(b.vigencia_fim || '9999'),
}

const tokens = (t) => new Set((norm(t).match(/[a-z0-9]{3,}/g) || []))
const jaccard = (a, b) => {
  let i = 0
  for (const x of a) if (b.has(x)) i++
  return i / Math.max(1, a.size + b.size - i)
}

/** Soma valores estimados (contratações e itens de PCA) SEM duplicidade e ignorando valores
 *  ausentes/sigilosos. Conta uma vez só: o mesmo registro (id), o mesmo item de PCA repetido
 *  (mesmo órgão, descrição e valor — ex.: planos 2026 e 2027) e o edital republicado (mesmo órgão
 *  e valor, objeto ≥ 60% igual). Atas e contratos não entram (são a mesma demanda já contada). */
export function aggregateValue(items) {
  const seen = new Set()
  const grupos = new Map()
  let total = 0
  let n = 0
  let dup = 0
  for (const r of items) {
    if (seen.has(r.id)) continue
    seen.add(r.id)
    if (!['contratacao', 'pca'].includes(r.tipo)) continue
    const v = Number(r.valor_estimado)
    if (!v || v <= 0) continue
    const key = `${r.tipo}|${r.orgao?.cnpj || r.orgao?.nome || ''}|${v.toFixed(2)}`
    const tk = tokens(r.objeto)
    const lista = grupos.get(key) || []
    const limiar = r.tipo === 'pca' ? 0.999 : 0.6
    if (lista.some((o) => jaccard(tk, o) >= limiar)) { dup += v; continue }
    lista.push(tk)
    grupos.set(key, lista)
    total += v
    n += 1
  }
  return { total, n, duplicado: dup }
}

export function uniqueSorted(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'))
}
