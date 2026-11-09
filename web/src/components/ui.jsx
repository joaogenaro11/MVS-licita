import { fmtDate, money } from '../lib/format.js'
import { portfolioLabel } from '../lib/filters.js'
import { highlightParts } from '../lib/highlight.js'

export const ADESAO = {
  potencial_verificar: { label: 'Potencial de adesão a verificar', cls: 'bg-[#f6f2ff] text-[#6929c4] ring-[#d4bbff]' },
  restricao_identificada: { label: 'Restrição de adesão identificada', cls: 'bg-[#fff1f1] text-[#a2191f] ring-[#ffb3b8]' },
  nao_determinada: { label: 'Adesão não determinada', cls: 'bg-field text-ink-2 ring-line' },
  encerrada: { label: 'Ata encerrada/vencida', cls: 'bg-field text-muted ring-line' },
}

export const VIGENCIA = {
  vigente: { label: 'Vigente', cls: 'bg-[#defbe6] text-[#0e6027] ring-[#a7f0ba]' },
  vence_em_breve: { label: 'Vence em breve', cls: 'bg-[#fcf4d6] text-[#8e6a00] ring-[#f1c21b]' },
  encerrada: { label: 'Encerrada', cls: 'bg-field text-muted ring-line' },
  cancelada: { label: 'Cancelada', cls: 'bg-[#fff1f1] text-[#a2191f] ring-[#ffb3b8]' },
  inconsistente: { label: 'Vigência a conferir', cls: 'bg-[#fcf4d6] text-[#8e6a00] ring-[#f1c21b]' },
  sem_data: { label: 'Vigência não informada', cls: 'bg-field text-muted ring-line' },
}

export const TIPO = { contratacao: 'Contratação', pca: 'PCA', contrato: 'Contrato', ata: 'Ata' }

const PORTFOLIO_CLS = {
  'Logo IBM': 'bg-[#0f62fe] text-white ring-[#0f62fe]',
  MVS: 'bg-[#6929c4] text-white ring-[#6929c4]',
  'Logo IBM + MVS': 'bg-[#002d9c] text-white ring-[#002d9c]',
  Transversal: 'bg-field text-ink-2 ring-line',
}
export const SELO_CLS = {
  falso_positivo: 'bg-[#fcf4d6] text-[#8e6a00] ring-[#f1c21b]',
  indisponivel_brasil: 'bg-[#fff1f1] text-[#a2191f] ring-[#ffb3b8]',
}

export function Badge({ children, className = '', title }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-medium leading-4 ring-1 ring-inset ${className || 'bg-field text-ink-2 ring-line'}`}>
      {children}
    </span>
  )
}

export function PortfolioBadge({ c }) {
  const label = portfolioLabel(c?.portfolio)
  if (!label) return null
  return <Badge className={PORTFOLIO_CLS[label]}>{label}</Badge>
}

/** Pontuação da base de ofertas: termo exato = 3; marca + serviço = 2; x1,5 prioridade alta; soma. */
export function ScoreBadge({ c }) {
  if (!c) return null
  return (
    <div className="flex flex-col items-end gap-1" title="Pontuação TLS: termo exato = 3, marca + serviço = 2, x1,5 se prioridade alta; soma das ofertas que casaram">
      <div className="num text-2xl font-semibold leading-none text-ink">{(c.pontuacao ?? 0).toLocaleString('pt-BR')}</div>
      <span className="text-[11px] text-muted">pontuação</span>
      <PortfolioBadge c={c} />
    </div>
  )
}

export function OfertaChips({ c, max = 99 }) {
  const list = c?.ofertas_casadas || []
  if (!list.length) return null
  return (
    <div className="flex flex-wrap gap-1">
      {list.slice(0, max).map((o) => (
        <span key={o.id} title={`${o.via === 'termo_exato' ? 'Termo exato' : 'Marca + serviço'} · ${o.pontos} pts · ${o.termos.join(', ')}`}
          className="rounded-full bg-brand-soft px-2 py-0.5 text-[11px] font-medium text-brand-dark">{o.nome_pt}</span>
      ))}
      {list.length > max ? <span className="px-1 text-[11px] text-muted">+{list.length - max}</span> : null}
    </div>
  )
}

export function Selos({ c, detalhe = false }) {
  const selos = c?.selos || []
  if (!selos.length) return null
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap gap-1">
        {selos.map((s) => <Badge key={s.tipo} className={SELO_CLS[s.tipo]} title={s.detalhe}>{s.texto}</Badge>)}
      </div>
      {detalhe ? selos.map((s) => <p key={s.tipo} className="text-[12px] text-ink-2">{s.detalhe}</p>) : null}
    </div>
  )
}

/** Texto com os termos que deram match destacados. */
export function Highlight({ text, terms }) {
  return highlightParts(text, terms).map((p, i) => (p.hit
    ? <mark key={i} className="bg-[#fcf4d6] px-0.5 text-inherit">{p.text}</mark>
    : <span key={i}>{p.text}</span>))
}

export function Casou({ r }) {
  if (!r._casou?.length) return null
  return <p className="mt-1 text-[12px] text-brand-dark"><span className="text-muted">casou: </span>{r._casou.join(', ')}</p>
}

/** Controle segmentado Tudo / Logo / MVS, com contadores que respeitam os demais filtros. */
export function PortfolioSwitch({ value, onChange, counts }) {
  const opts = [['tudo', 'Tudo'], ['logo', 'Logo'], ['mvs', 'MVS']]
  return (
    <div role="radiogroup" aria-label="Portfólio" className="inline-flex bg-white ring-1 ring-line">
      {opts.map(([k, label]) => {
        const on = (value || 'tudo') === k
        return (
          <button key={k} type="button" role="radio" aria-checked={on} onClick={() => onChange(k)}
            className={`px-4 py-1.5 text-[13px] ${on ? 'bg-ink text-white' : 'text-ink-2 hover:bg-field'}`}>
            {label} <span className={`num ${on ? 'text-[#c6c6c6]' : 'text-muted'}`}>({(counts?.[k] ?? 0).toLocaleString('pt-BR')})</span>
          </button>
        )
      })}
    </div>
  )
}

export const SEARCH_HINT = 'Separe termos por vírgula para buscar qualquer um deles. Use aspas para frase exata.'

export function isSafeUrl(u) {
  return typeof u === 'string' && /^https?:\/\/[^\s"<>]+\.[^\s"<>]+$/i.test(u)
}

export function ExtLink({ href, children, className = '', title }) {
  if (!isSafeUrl(href)) return null
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" title={title || href} className={className}>
      {children}
    </a>
  )
}

const ArrowIcon = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0"><path fill="currentColor" d="M13 14H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h4v1H3v10h10V9h1v4a1 1 0 0 1-1 1zM10 1v1h3.3L8.6 6.7l.7.7L14 2.7V6h1V1z" /></svg>
)

/** Botões de acesso direto: portal de origem (link oficial informado ao PNCP) + PNCP. */
export function PortalLinks({ links, compact = false }) {
  const origem = isSafeUrl(links?.origem) ? links.origem : null
  const btn = 'inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium whitespace-nowrap'
  return (
    <div className="flex flex-wrap items-center gap-2">
      {origem ? (
        <ExtLink href={origem} className={`${btn} bg-brand text-white hover:bg-brand-dark`} title={`Abrir no portal de origem: ${origem}`}>
          Abrir no Portal de Compras <ArrowIcon />
        </ExtLink>
      ) : null}
      <ExtLink href={links?.pncp} className={`${btn} ${origem ? 'bg-white text-brand ring-1 ring-inset ring-brand hover:bg-brand-soft' : 'bg-brand text-white hover:bg-brand-dark'}`}>
        {origem ? 'PNCP' : 'Abrir no PNCP'} <ArrowIcon />
      </ExtLink>
      {!compact && (
        <ExtLink href={links?.processo_eletronico} className={`${btn} text-brand hover:underline`}>Processo eletrônico <ArrowIcon /></ExtLink>
      )}
      {origem && links?.origem_portal ? (
        <span className="text-[11px] text-muted">Portal: {links.origem_portal}</span>
      ) : null}
      {!origem ? (
        <span className="text-[11px] text-muted">Endereço direto do portal de origem não identificado — use o PNCP.</span>
      ) : null}
    </div>
  )
}

export function Kpi({ label, value, hint, accent, onClick }) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag onClick={onClick} className={`flex flex-col gap-1 bg-white p-4 text-left ${onClick ? 'cursor-pointer hover:bg-[#e8e8e8]' : ''}`}>
      <span className="text-[12px] text-ink-2">{label}</span>
      <span className="num text-[28px] font-normal leading-tight" style={accent ? { color: accent } : undefined}>{value}</span>
      {hint ? <span className="text-[11px] text-muted">{hint}</span> : null}
    </Tag>
  )
}

export function Field({ label, children, className = '' }) {
  return (
    <label className={`flex min-w-0 flex-col gap-1 ${className}`}>
      <span className="text-[11px] text-ink-2">{label}</span>
      {children}
    </label>
  )
}

export const inputCls = 'h-9 w-full min-w-0 border-0 border-b border-[#8d8d8d] bg-field px-2 text-[13px] outline-none focus:border-brand focus:ring-2 focus:ring-brand focus:ring-inset'

export function Select({ value, onChange, options, placeholder = 'Todos' }) {
  return (
    <select value={value ?? ''} onChange={(e) => onChange(e.target.value)} className={inputCls}>
      <option value="">{placeholder}</option>
      {options.map((o) => (typeof o === 'string'
        ? <option key={o} value={o}>{o}</option>
        : <option key={o.value} value={o.value}>{o.label}</option>))}
    </select>
  )
}

export function Star({ on, onClick, title }) {
  return (
    <button type="button" onClick={onClick} title={title || (on ? 'Remover dos favoritos' : 'Favoritar')}
      aria-pressed={on} className={`p-1 text-[18px] leading-none ${on ? 'text-[#f1c21b]' : 'text-[#c6c6c6] hover:text-ink-2'}`}>
      {on ? '★' : '☆'}
    </button>
  )
}

export function KV({ k, v, mono }) {
  return (
    <div className="flex flex-col gap-0.5 py-1.5">
      <dt className="text-[11px] text-muted">{k}</dt>
      <dd className={`text-[13px] break-words ${mono ? 'font-mono' : ''}`}>{v ?? <span className="text-muted">Não informado</span>}</dd>
    </div>
  )
}

export const valueOrNA = (v) => money(v) || 'Não informado'
export const dateOrNA = (s, t) => fmtDate(s, t) || 'Não informado'

export function Empty({ children }) {
  return <div className="bg-white p-8 text-center text-[13px] text-muted">{children}</div>
}
