import { norm } from './format.js'

/** Índice de busca textual (calculado uma vez por registro). */
export function indexRecord(r) {
  const c = r.classificacao || {}
  const parts = [
    r.id, r.numero, r.processo, r.objeto, r.info_complementar,
    r.orgao?.nome, r.unidade?.nome, r.unidade?.municipio, r.orgao_subrogado,
    (c.ofertas || []).join(' '), (c.fabricantes || []).map((f) => f.nome).join(' '),
    (r.itens || []).map((i) => i.descricao).join(' '),
    (r.fornecedores || []).map((f) => f.nome).join(' '),
    r.fornecedor?.nome,
  ]
  r._q = norm(parts.filter(Boolean).join(' '))
  r._org = norm([r.orgao?.nome, r.unidade?.nome].filter(Boolean).join(' '))
  return r
}

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
  const words = norm(f.q).split(' ').filter(Boolean)
  const org = norm(f.orgao)
  const mun = norm(f.municipio)
  return items.filter((r) => {
    const c = r.classificacao || {}
    if (words.length && !words.every((w) => r._q.includes(w))) return false
    if (org && !r._org.includes(org)) return false
    if (f.uf && r.unidade?.uf !== f.uf) return false
    if (mun && !norm(r.unidade?.municipio).includes(mun)) return false
    if (f.tipo && r.tipo !== f.tipo) return false
    if (f.modalidade && r.modalidade?.nome !== f.modalidade) return false
    if (f.estagio && r.estagio !== f.estagio) return false
    if (f.oferta && !(c.ofertas || []).includes(f.oferta)) return false
    if (f.fabricante && !(c.fabricantes || []).some((x) => x.nome === f.fabricante)) return false
    if (f.relacao && c.relacao !== f.relacao) return false
    if ((f.vmin || f.vmax) && !inRange(r.valor_estimado ?? -1, f.vmin, f.vmax)) return false
    if (f.scoreMin && !((c.score || 0) >= Number(f.scoreMin))) return false
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
  const words = norm(f.q).split(' ').filter(Boolean)
  const org = norm(f.orgao)
  return atas.filter((a) => {
    const c = a.classificacao || {}
    if (words.length && !words.every((w) => a._q.includes(w))) return false
    if (org && !a._org.includes(org)) return false
    if (f.vigencia === 'vigentes' && !['vigente', 'vence_em_breve'].includes(a.vigencia_status)) return false
    if (f.vigencia === 'vence_em_breve' && a.vigencia_status !== 'vence_em_breve') return false
    if (f.vigencia === 'encerradas' && !['encerrada', 'cancelada'].includes(a.vigencia_status)) return false
    if (f.vigencia === 'a_conferir' && !['inconsistente', 'sem_data'].includes(a.vigencia_status)) return false
    if (f.adesao && a.adesao_status !== f.adesao) return false
    if (f.oferta && !(c.ofertas || []).includes(f.oferta)) return false
    if (f.fabricante && !(c.fabricantes || []).some((x) => x.nome === f.fabricante)) return false
    if ((f.vmin || f.vmax) && !inRange(a.compra?.valor ?? -1, f.vmin, f.vmax)) return false
    if (f.scoreMin && !((c.score || 0) >= Number(f.scoreMin))) return false
    if (f.uf && a.unidade?.uf !== f.uf) return false
    if (f.prioritarios && !matchesPriority(a, ctx.priorityOrgs)) return false
    if (f.favoritos && !ctx.isFav?.(a.id)) return false
    return true
  })
}

export const SORTS = {
  score: (a, b) => (b.classificacao?.score || 0) - (a.classificacao?.score || 0),
  valor: (a, b) => (b.valor_estimado ?? b.compra?.valor ?? 0) - (a.valor_estimado ?? a.compra?.valor ?? 0),
  publicacao: (a, b) => (b.data_publicacao || '').localeCompare(a.data_publicacao || ''),
  prazo: (a, b) => (a.data_encerramento_proposta || '9999').localeCompare(b.data_encerramento_proposta || '9999'),
  vencimento: (a, b) => (a.vigencia_fim || '9999').localeCompare(b.vigencia_fim || '9999'),
}

/** Soma valores estimados SEM duplicar registros e ignorando valores ausentes/sigilosos. */
export function aggregateValue(items) {
  const seen = new Set()
  let total = 0
  let n = 0
  for (const r of items) {
    if (seen.has(r.id)) continue
    seen.add(r.id)
    if (!['contratacao', 'pca'].includes(r.tipo)) continue
    const v = Number(r.valor_estimado)
    if (!v || v <= 0) continue
    total += v
    n += 1
  }
  return { total, n }
}

export function uniqueSorted(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'))
}
