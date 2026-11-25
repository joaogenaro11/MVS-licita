// CRM comercial: cada vendedor tem o seu funil; o gestor (papel 'gestor' ou 'admin') vê todos,
// filtra por vendedor e pede para alguém acompanhar uma oportunidade.
export const ETAPAS = [
  { id: 'novo', label: 'Novo', cor: '#8d8d8d' },
  { id: 'qualificando', label: 'Qualificando', cor: '#0f62fe' },
  { id: 'proposta', label: 'Proposta', cor: '#8a3ffc' },
  { id: 'negociacao', label: 'Negociação', cor: '#b28600' },
  { id: 'ganho', label: 'Ganho', cor: '#198038' },
  { id: 'perdido', label: 'Perdido', cor: '#da1e28' },
  { id: 'descartado', label: 'Descartado', cor: '#6f6f6f' },
]
export const ETAPA = Object.fromEntries(ETAPAS.map((e) => [e.id, e]))
export const ABERTAS = ['novo', 'qualificando', 'proposta', 'negociacao']
export const EVENTO = {
  criado: 'Entrou no CRM', etapa: 'Etapa', acompanhamento: 'Próximo acompanhamento', codigo: 'Código da oportunidade',
  atribuido: 'Pedido de acompanhamento', nota: 'Nota',
}

export const hojeISO = (d = new Date()) => {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
  return z.toISOString().slice(0, 10)
}
const somaDias = (iso, n) => hojeISO(new Date(new Date(`${iso}T12:00:00`).getTime() + n * 86400000))

/** Retrato da oportunidade guardado no CRM (continua legível se ela sair do site). */
export function snapshotDe(r) {
  const valor = r.tipo === 'ata' ? r.compra?.valor : (r.valor_estimado || r.valor_homologado)
  return {
    objeto: (r.objeto || '').slice(0, 400), orgao: r.orgao?.nome || null, uf: r.unidade?.uf || null,
    valor: Number(valor) > 0 ? Number(valor) : null, prazo: r.data_encerramento_proposta || r.vigencia_fim || null,
    estagio: r.estagio || null, pncp: r.links?.pncp || null, score: r.classificacao?.score ?? null,
  }
}

export const aberta = (c) => ABERTAS.includes(c.etapa)
export const pedidoPendente = (c, me) => Boolean(c.atribuido_por && c.atribuido_por !== c.dono && c.dono === me && !c.visto_em)

/** Agenda do dia: acompanhamentos de hoje (e atrasados), próximos 7 dias, pedidos não vistos. */
export function agenda(rows, me, hoje = hojeISO()) {
  const limite = somaDias(hoje, 7)
  const ab = rows.filter(aberta)
  const porData = (a, b) => (a.proximo_acompanhamento || '').localeCompare(b.proximo_acompanhamento || '')
  return {
    hoje: ab.filter((c) => c.proximo_acompanhamento && c.proximo_acompanhamento <= hoje).sort(porData),
    atrasados: ab.filter((c) => c.proximo_acompanhamento && c.proximo_acompanhamento < hoje).length,
    semana: ab.filter((c) => c.proximo_acompanhamento && c.proximo_acompanhamento > hoje && c.proximo_acompanhamento <= limite).sort(porData),
    semData: ab.filter((c) => !c.proximo_acompanhamento),
    pedidos: rows.filter((c) => pedidoPendente(c, me)),
  }
}

/** Resumo por vendedor para o gestor. */
export function resumoPorDono(rows, hoje = hojeISO()) {
  const out = {}
  for (const c of rows) {
    const s = out[c.dono] ||= { abertas: 0, hoje: 0, atrasados: 0, pedidos: 0, proposta: 0, ganhos: 0, valorAberto: 0 }
    if (aberta(c)) {
      s.abertas += 1
      s.valorAberto += Number(c.valor_negocio ?? c.snapshot?.valor ?? 0) || 0
      if (c.proximo_acompanhamento && c.proximo_acompanhamento <= hoje) s.hoje += 1
      if (c.proximo_acompanhamento && c.proximo_acompanhamento < hoje) s.atrasados += 1
    }
    if (['proposta', 'negociacao'].includes(c.etapa)) s.proposta += 1
    if (c.etapa === 'ganho') s.ganhos += 1
    if (c.atribuido_por && c.atribuido_por !== c.dono && !c.visto_em) s.pedidos += 1
  }
  return out
}

/** Eventos de histórico para o modo local (no Supabase quem registra é o gatilho do banco). */
export function diffEventos(old, novo, autor, agora = new Date().toISOString()) {
  const ev = (tipo, texto, a = autor) => ({ id: `${agora}-${tipo}-${Math.random().toString(36).slice(2, 7)}`, crm_id: novo.id, autor: a, tipo, texto, criado_em: agora })
  const br = (d) => (d ? d.split('-').reverse().join('/') : 'sem data')
  const out = []
  const atribuiu = novo.atribuido_por && novo.atribuido_por !== novo.dono
  if (!old) {
    out.push(ev('criado', `etapa: ${novo.etapa}`))
    if (atribuiu) out.push(ev('atribuido', novo.mensagem_atribuicao || null, novo.atribuido_por))
    return out
  }
  if (old.etapa !== novo.etapa) out.push(ev('etapa', `${old.etapa} → ${novo.etapa}`))
  if ((old.proximo_acompanhamento || null) !== (novo.proximo_acompanhamento || null)) out.push(ev('acompanhamento', br(novo.proximo_acompanhamento)))
  if ((old.codigo_oportunidade || null) !== (novo.codigo_oportunidade || null)) out.push(ev('codigo', novo.codigo_oportunidade || null))
  if (novo.atribuido_por && (old.atribuido_por !== novo.atribuido_por || old.mensagem_atribuicao !== novo.mensagem_atribuicao)) {
    out.push(ev('atribuido', novo.mensagem_atribuicao || null, novo.atribuido_por))
  }
  return out
}

/** Linhas do CRM em CSV (abre no Excel em pt-BR: separador ";"). */
export function crmCSV(rows, nomeDe = (x) => x) {
  const cols = [
    ['Etapa', (c) => ETAPA[c.etapa]?.label], ['Próximo acompanhamento', (c) => c.proximo_acompanhamento],
    ['Código da oportunidade / SC', (c) => c.codigo_oportunidade], ['Vendedor', (c) => nomeDe(c.dono)],
    ['Órgão', (c) => c.snapshot?.orgao], ['UF', (c) => c.snapshot?.uf], ['Objeto', (c) => c.snapshot?.objeto],
    ['Valor do negócio', (c) => c.valor_negocio], ['Valor estimado (PNCP)', (c) => c.snapshot?.valor], ['Parceiro', (c) => c.parceiro],
    ['Motivo da perda', (c) => c.motivo_perda], ['Observação', (c) => c.observacao], ['ID PNCP', (c) => c.item_id],
    ['Link PNCP', (c) => c.snapshot?.pncp], ['Atualizado em', (c) => c.atualizado_em],
  ]
  const q = (v) => {
    const s = v == null ? '' : String(v)
    return /[;"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return '﻿' + [cols.map(([h]) => h).join(';'), ...rows.map((c) => cols.map(([, f]) => q(f(c))).join(';'))].join('\r\n')
}
