import { useMemo, useState } from 'react'
import { ADESAO, Badge, Empty, Field, inputCls, PortalLinks, ScoreBadge, Select, Star, VIGENCIA } from '../components/ui.jsx'
import { fmtDate, money, UFS } from '../lib/format.js'
import { filterAtas, matchesPartner, matchesPriority, SORTS, uniqueSorted } from '../lib/filters.js'

export const EMPTY_ATA_FILTERS = {
  q: '', orgao: '', vigencia: 'vigentes', adesao: '', oferta: '', fabricante: '', vmin: '', vmax: '', scoreMin: '', uf: '',
  prioritarios: false, favoritos: false,
}

const PAGE = 50

export default function Atas({ data, filters, setFilters, ctx, onOpen }) {
  const { atas } = data
  const [sort, setSort] = useState('score')
  const [limit, setLimit] = useState(PAGE)
  const opts = useMemo(() => ({
    ofertas: uniqueSorted(atas.flatMap((i) => i.classificacao?.ofertas || [])),
    fabricantes: uniqueSorted(atas.flatMap((i) => (i.classificacao?.fabricantes || []).map((f) => f.nome))),
  }), [atas])
  const result = useMemo(() => filterAtas(atas, filters, ctx).sort(SORTS[sort]), [atas, filters, ctx, sort])
  const set = (k) => (v) => { setFilters({ ...filters, [k]: v }); setLimit(PAGE) }

  return (
    <div className="flex flex-col gap-4">
      <div className="border-l-4 border-purple bg-white px-4 py-3 text-[12px] text-ink-2">
        <strong className="text-ink">Radar de Atas.</strong> Atas de registro de preços relacionadas ao portfólio TLS publicadas no PNCP.
        O potencial de adesão é <strong>indicativo</strong>: usa o campo oficial <code>possibilidadeAdesao</code> (quando preenchido), o texto público
        e contratos por adesão já publicados. Não há análise jurídica nem verificação de saldo — confirme no edital, na ata e com o órgão gerenciador.
      </div>
      <div className="grid grid-cols-2 gap-3 bg-white p-4 md:grid-cols-4 lg:grid-cols-6">
        <Field label="Palavra-chave" className="col-span-2"><input type="search" value={filters.q} onChange={(e) => set('q')(e.target.value)} className={inputCls} placeholder="objeto, órgão, fornecedor, fabricante" /></Field>
        <Field label="Vigência"><Select value={filters.vigencia} onChange={set('vigencia')} placeholder="Todas" options={[
          { value: 'vigentes', label: 'Vigentes' }, { value: 'vence_em_breve', label: 'Próximas do vencimento (90 dias)' },
          { value: 'a_conferir', label: 'Vigência a conferir' }, { value: 'encerradas', label: 'Encerradas/canceladas' }]} /></Field>
        <Field label="Adesão"><Select value={filters.adesao} onChange={set('adesao')} options={Object.entries(ADESAO).map(([value, v]) => ({ value, label: v.label }))} /></Field>
        <Field label="Órgão gerenciador"><input value={filters.orgao} onChange={(e) => set('orgao')(e.target.value)} className={inputCls} /></Field>
        <Field label="UF (quando identificada)"><Select value={filters.uf} onChange={set('uf')} options={UFS} /></Field>
        <Field label="Oferta TLS"><Select value={filters.oferta} onChange={set('oferta')} options={opts.ofertas} /></Field>
        <Field label="Fabricante"><Select value={filters.fabricante} onChange={set('fabricante')} options={opts.fabricantes} /></Field>
        <Field label="Valor mínimo (R$)"><input type="number" min="0" value={filters.vmin} onChange={(e) => set('vmin')(e.target.value)} className={inputCls} /></Field>
        <Field label="Valor máximo (R$)"><input type="number" min="0" value={filters.vmax} onChange={(e) => set('vmax')(e.target.value)} className={inputCls} /></Field>
        <Field label="Aderência mínima"><Select value={filters.scoreMin} onChange={set('scoreMin')} placeholder="Qualquer" options={[
          { value: '80', label: '80+' }, { value: '60', label: '60+' }, { value: '40', label: '40+' }]} /></Field>
        <div className="flex flex-col justify-end gap-1 text-[13px]">
          <label className="flex items-center gap-2"><input type="checkbox" checked={filters.prioritarios} onChange={(e) => set('prioritarios')(e.target.checked)} /> Órgãos prioritários</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={filters.favoritos} onChange={(e) => set('favoritos')(e.target.checked)} /> Favoritas</label>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
        <div className="text-ink-2"><strong className="num">{result.length.toLocaleString('pt-BR')}</strong> ata(s) na base coletada
          <button className="ml-3 text-brand hover:underline" onClick={() => setFilters(EMPTY_ATA_FILTERS)}>restaurar filtros</button></div>
        <label className="flex items-center gap-2 text-ink-2">Ordenar por
          <select value={sort} onChange={(e) => setSort(e.target.value)} className="h-8 bg-white px-2 ring-1 ring-line">
            <option value="score">Aderência</option><option value="vencimento">Vencimento mais próximo</option><option value="publicacao">Publicação</option>
          </select></label>
      </div>
      {result.length === 0 ? <Empty>Nenhuma ata com esses filtros na base coletada.</Empty> : (
        <ul className="flex flex-col gap-px bg-line">
          {result.slice(0, limit).map((a) => <AtaCard key={a.id} a={a} ctx={ctx} onOpen={onOpen} />)}
        </ul>
      )}
      {result.length > limit && (
        <button onClick={() => setLimit(limit + PAGE)} className="self-center bg-white px-4 py-2 text-[13px] text-brand ring-1 ring-line hover:bg-brand-soft">
          Mostrar mais ({(result.length - limit).toLocaleString('pt-BR')} restantes)</button>
      )}
    </div>
  )
}

export function AtaCard({ a, ctx, onOpen }) {
  const c = a.classificacao || {}
  const vig = VIGENCIA[a.vigencia_status] || VIGENCIA.sem_data
  const ad = ADESAO[a.adesao_status] || ADESAO.nao_determinada
  const partners = matchesPartner(a, ctx.config?.partners)
  return (
    <li className="bg-white p-4 hover:bg-[#fafafa]">
      <div className="flex gap-4">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap gap-1.5">
            <Badge className="bg-ink text-white ring-ink">Ata {a.numero || ''}</Badge>
            <Badge className={vig.cls}>{vig.label}{a.dias_para_vencer != null && a.dias_para_vencer >= 0 ? ` · ${a.dias_para_vencer} dias` : ''}</Badge>
            <Badge className={ad.cls}>{ad.label}</Badge>
            {matchesPriority(a, ctx.priorityOrgs) ? <Badge className="bg-[#f6f2ff] text-[#6929c4] ring-[#d4bbff]">Órgão prioritário</Badge> : null}
            {partners.length ? <Badge className="bg-[#f6f2ff] text-[#6929c4] ring-[#d4bbff]">Parceiro: {partners.join(', ')}</Badge> : null}
          </div>
          <div className="text-[12px] font-medium">{a.orgao?.nome}{a.unidade?.uf ? <span className="font-normal text-ink-2"> · {a.unidade.uf}</span> : null}</div>
          <button type="button" onClick={() => onOpen(a)} className="mt-1 block text-left text-[14px] leading-snug hover:text-brand"><span className="clamp-3">{a.objeto}</span></button>
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
            <div><dt className="inline text-muted">Vigência: </dt><dd className="inline">{fmtDate(a.vigencia_inicio) || '?'} a {a.vigencia_status === 'inconsistente' ? 'data inconsistente' : fmtDate(a.vigencia_fim) || '?'}</dd></div>
            {a.vence_em ? <div title={a.vence_motivo}><dt className="inline text-muted">No Radar até: </dt><dd className="inline">{fmtDate(a.vence_em)}</dd></div> : null}
            <div><dt className="inline text-muted">Fornecedor: </dt><dd className="inline">{(a.fornecedores || []).map((f) => f.nome).join('; ') || 'não identificado'}</dd></div>
            <div><dt className="inline text-muted">Valor da contratação: </dt><dd className="num inline">{money(a.compra?.valor) || 'não informado'}</dd></div>
            {c.ofertas?.length ? <div><dt className="inline text-muted">Oferta TLS: </dt><dd className="inline font-medium">{c.ofertas.join(' + ')}</dd></div> : null}
            {c.fabricantes?.length ? <div><dt className="inline text-muted">Fabricante: </dt><dd className="inline">{c.fabricantes.map((f) => f.nome).join(', ')}</dd></div> : null}
          </dl>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <PortalLinks links={a.links} compact />
            <button type="button" onClick={() => onOpen(a)} className="text-[13px] text-brand hover:underline">Detalhes e documentos</button>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <ScoreBadge c={c} />
          <Star on={ctx.isFav(a.id)} onClick={() => ctx.toggleFav(a)} />
        </div>
      </div>
    </li>
  )
}
