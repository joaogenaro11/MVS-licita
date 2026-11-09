import { useMemo, useState } from 'react'
import { Badge, Casou, Empty, FAIXA_OPTS, FamiliaChips, Field, Highlight, inputCls, PortalLinks, PortfolioBadge, PortfolioSwitch, ScoreBadge, SEARCH_HINT, Select, Selos, Star, TIPO } from '../components/ui.jsx'
import { daysUntil, fmtDate, money, relDays, UFS } from '../lib/format.js'
import { bySearchThen, filterItems, matchesPriority, portfolioCounts, SORTS, uniqueSorted } from '../lib/filters.js'

export const EMPTY_FILTERS = {
  q: '', portfolio: 'tudo', orgao: '', uf: '', municipio: '', modalidade: '', estagio: '', oferta: '', selo: '', vmin: '', vmax: '',
  pubDe: '', pubAte: '', prazoAte: '', faixa: '', familia: '', tipo: '', foco: '', prioritarios: false, favoritos: false,
}
export const familiaOpts = (meta) => (meta.lookups?.familias || []).map((f) => ({ value: f.id, label: f.nome }))
export const SELO_OPTS = [
  { value: 'falso_positivo', label: 'Possível falso positivo' }, { value: 'indisponivel_brasil', label: 'Oferta indisponível no Brasil' }]

const PAGE = 50

export default function Oportunidades({ data, filters, setFilters, sort = 'score', setSort, ctx, onOpen }) {
  const { items, meta } = data
  const [limit, setLimit] = useState(PAGE)
  const [more, setMore] = useState(false)
  const L = meta.lookups || {}

  const opts = useMemo(() => ({
    modalidades: uniqueSorted(items.map((i) => i.modalidade?.nome)),
    ofertas: uniqueSorted(items.flatMap((i) => i.classificacao?.ofertas || [])),
  }), [items])

  const { result, counts } = useMemo(() => {
    const semPortfolio = filterItems(items, { ...filters, portfolio: 'tudo' }, ctx)
    const counts = portfolioCounts(semPortfolio)
    const r = filterItems(items, filters, ctx)
    return { result: r.sort(bySearchThen(SORTS[sort] || SORTS.score)), counts }
  }, [items, filters, ctx, sort])

  const set = (k) => (v) => { setFilters({ ...filters, [k]: v }); setLimit(PAGE) }
  const active = Object.entries(filters).filter(([k, v]) => v !== '' && v !== false && !(k === 'portfolio' && v === 'tudo')).length

  return (
    <div className="flex flex-col gap-4">
      <PortfolioSwitch value={filters.portfolio} onChange={set('portfolio')} counts={counts} />
      <div className="bg-white p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start">
          <div className="flex flex-1 flex-col gap-1">
            <Field label="Palavra-chave (objeto, itens, órgão, oferta, nº PNCP)">
              <input value={filters.q} onChange={(e) => set('q')(e.target.value)} placeholder='ex.: Cisco, Red Hat, "suporte técnico"'
                className={`${inputCls} h-10 text-[14px]`} type="search" aria-describedby="dica-busca" />
            </Field>
            <p id="dica-busca" className="text-[11px] text-muted">{SEARCH_HINT}</p>
            <BuscasSalvas filters={filters} setFilters={setFilters} ctx={ctx} />
          </div>
          <Field label="Estágio" className="md:w-56">
            <Select value={filters.estagio} onChange={set('estagio')} options={Object.entries(L.estagios || {}).map(([value, label]) => ({ value, label }))} />
          </Field>
          <Field label="Família" className="md:w-56">
            <Select value={filters.familia} onChange={set('familia')} options={familiaOpts(meta)} />
          </Field>
          <Field label="Aderência" className="md:w-40">
            <Select value={filters.faixa} onChange={set('faixa')} placeholder="Todas" options={FAIXA_OPTS} />
          </Field>
          <button type="button" onClick={() => setMore(!more)} className="h-10 self-end px-3 text-[13px] text-brand hover:bg-brand-soft md:self-auto md:mt-4">
            {more ? 'Menos filtros' : 'Mais filtros'}{active ? ` (${active})` : ''}
          </button>
        </div>
        {more && (
          <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
            <Field label="Órgão / unidade"><input value={filters.orgao} onChange={(e) => set('orgao')(e.target.value)} className={inputCls} /></Field>
            <Field label="UF"><Select value={filters.uf} onChange={set('uf')} options={UFS} /></Field>
            <Field label="Município"><input value={filters.municipio} onChange={(e) => set('municipio')(e.target.value)} className={inputCls} /></Field>
            <Field label="Modalidade"><Select value={filters.modalidade} onChange={set('modalidade')} options={opts.modalidades} /></Field>
            <Field label="Selo"><Select value={filters.selo} onChange={set('selo')} options={SELO_OPTS} /></Field>
            <Field label="Tipo de registro"><Select value={filters.tipo} onChange={set('tipo')} options={[
              { value: 'contratacao', label: 'Contratação (edital/aviso)' }, { value: 'pca', label: 'Item de PCA' }, { value: 'contrato', label: 'Contrato' }]} /></Field>
            <Field label="Valor mínimo (R$)"><input type="number" min="0" value={filters.vmin} onChange={(e) => set('vmin')(e.target.value)} className={inputCls} /></Field>
            <Field label="Valor máximo (R$)"><input type="number" min="0" value={filters.vmax} onChange={(e) => set('vmax')(e.target.value)} className={inputCls} /></Field>
            <Field label="Publicado a partir de"><input type="date" value={filters.pubDe} onChange={(e) => set('pubDe')(e.target.value)} className={inputCls} /></Field>
            <Field label="Publicado até"><input type="date" value={filters.pubAte} onChange={(e) => set('pubAte')(e.target.value)} className={inputCls} /></Field>
            <Field label="Prazo de propostas até"><input type="date" value={filters.prazoAte} onChange={(e) => set('prazoAte')(e.target.value)} className={inputCls} /></Field>
            <Field label="Oferta TLS"><Select value={filters.oferta} onChange={set('oferta')} options={opts.ofertas} /></Field>
            <Field label="Foco"><Select value={filters.foco} onChange={set('foco')} placeholder="Nacional" options={[{ value: 'df_federal', label: 'DF + órgãos federais' }]} /></Field>
            <label className="flex items-end gap-2 pb-2 text-[13px]"><input type="checkbox" checked={filters.prioritarios} onChange={(e) => set('prioritarios')(e.target.checked)} /> Órgãos prioritários</label>
            <label className="flex items-end gap-2 pb-2 text-[13px]"><input type="checkbox" checked={filters.favoritos} onChange={(e) => set('favoritos')(e.target.checked)} /> Somente favoritos</label>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
        <div className="text-ink-2">
          <strong className="num">{result.length.toLocaleString('pt-BR')}</strong> resultado(s) na base coletada pelo Radar
          {active ? <button className="ml-3 text-brand hover:underline" onClick={() => setFilters({ ...EMPTY_FILTERS, portfolio: filters.portfolio })}>limpar filtros</button> : null}
        </div>
        <label className="flex items-center gap-2 text-ink-2">Ordenar por
          <select value={sort} onChange={(e) => setSort(e.target.value)} className="h-8 bg-white px-2 ring-1 ring-line">
            <option value="score">Aderência</option><option value="prazo">Prazo de propostas</option>
            <option value="publicacao">Publicação mais recente</option><option value="valor">Valor estimado</option>
          </select>
        </label>
      </div>

      {result.length === 0 ? <Empty>Nenhuma oportunidade com esses filtros na base coletada.</Empty> : (
        <ul className="flex flex-col gap-px bg-line">
          {result.slice(0, limit).map((r) => (
            <OppCard key={r.id} r={r} L={L} ctx={ctx} onOpen={onOpen} />
          ))}
        </ul>
      )}
      {result.length > limit && (
        <button onClick={() => setLimit(limit + PAGE)} className="self-center bg-white px-4 py-2 text-[13px] text-brand ring-1 ring-line hover:bg-brand-soft">
          Mostrar mais ({(result.length - limit).toLocaleString('pt-BR')} restantes)
        </button>
      )}
    </div>
  )
}

export function OppCard({ r, L, ctx, onOpen }) {
  const c = r.classificacao || {}
  const prazo = r.data_encerramento_proposta
  const dias = daysUntil(prazo)
  const prio = matchesPriority(r, ctx.priorityOrgs)
  return (
    <li className="bg-white p-4 hover:bg-[#fafafa]">
      <div className="flex gap-4">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-1.5">
            <Badge className="bg-ink text-white ring-ink">{TIPO[r.tipo] || r.tipo}</Badge>
            <Badge>{(L.estagios || {})[r.estagio] || r.estagio}</Badge>
            {r.modalidade?.nome ? <Badge>{r.modalidade.nome}</Badge> : null}
            <FamiliaChips c={c} familias={ctx.familias} />
            <PortfolioBadge c={c} />
            {prio ? <Badge className="bg-[#f6f2ff] text-[#6929c4] ring-[#d4bbff]">Órgão prioritário</Badge> : null}
          </div>
          <div className="text-[12px] text-ink-2">
            <span className="font-medium text-ink">{r.orgao?.nome || 'Órgão não informado'}</span>
            {r.unidade?.uf ? <span> · {r.unidade.municipio ? `${r.unidade.municipio}/` : ''}{r.unidade.uf}</span> : null}
          </div>
          <button type="button" onClick={() => onOpen(r)} className="mt-1 block text-left text-[14px] leading-snug text-ink hover:text-brand">
            <span className="clamp-3">{r.objeto ? <Highlight text={r.objeto} terms={c.termos} /> : 'Objeto não informado'}</span>
          </button>
          <Casou r={r} />
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
            <div><dt className="inline text-muted">Valor estimado: </dt><dd className="num inline font-medium">{money(r.valor_estimado) || 'não informado'}</dd></div>
            {r.data_publicacao ? <div><dt className="inline text-muted">Publicação: </dt><dd className="inline">{fmtDate(r.data_publicacao)}</dd></div> : null}
            {prazo ? (
              <div><dt className="inline text-muted">Propostas até: </dt>
                <dd className={`inline ${dias !== null && dias >= 0 && dias <= 7 ? 'font-medium text-bad' : ''}`}>{fmtDate(prazo, true)} ({relDays(dias)})</dd></div>
            ) : null}
            {r.tipo === 'pca' && r.data_desejada ? <div><dt className="inline text-muted">Data desejada: </dt><dd className="inline">{fmtDate(r.data_desejada)}</dd></div> : null}
            {r.vence_em ? <div title={r.vence_motivo}><dt className="inline text-muted">No Radar até: </dt><dd className="inline">{fmtDate(r.vence_em)}</dd></div> : null}
          </dl>
          {(c.selos || []).length ? <div className="mt-2"><Selos c={c} /></div> : null}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <PortalLinks links={r.links} compact />
            <button type="button" onClick={() => onOpen(r)} className="text-[13px] text-brand hover:underline">Detalhes</button>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <ScoreBadge c={c} />
          <Star on={ctx.isFav(r.id)} onClick={() => ctx.toggleFav(r)} />
        </div>
      </div>
    </li>
  )
}

/** Buscas salvas (pessoais, guardadas nas preferências do usuário). */
function BuscasSalvas({ filters, setFilters, ctx }) {
  const salvas = ctx.prefs?.prefs?.buscas_salvas || []
  const salvar = () => {
    const q = (filters.q || '').trim()
    if (!q) return
    const nome = window.prompt('Nome para esta busca:', q.slice(0, 40))
    if (!nome) return
    const next = [...salvas.filter((b) => b.nome !== nome), { nome, filtros: filters }]
    ctx.prefs.update({ buscas_salvas: next.slice(-15) })
  }
  const remover = (nome) => ctx.prefs.update({ buscas_salvas: salvas.filter((b) => b.nome !== nome) })
  if (!ctx.prefs) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[12px]">
      {filters.q?.trim() ? <button type="button" onClick={salvar} className="text-brand hover:underline">Salvar esta busca</button> : null}
      {salvas.map((b) => (
        <span key={b.nome} className="inline-flex items-center bg-field ring-1 ring-line">
          <button type="button" className="px-2 py-0.5 hover:text-brand" title={b.filtros?.q} onClick={() => setFilters({ ...EMPTY_FILTERS, ...b.filtros })}>{b.nome}</button>
          <button type="button" className="px-1.5 text-muted hover:text-bad" aria-label={`Remover busca ${b.nome}`} onClick={() => remover(b.nome)}>×</button>
        </span>
      ))}
    </div>
  )
}
