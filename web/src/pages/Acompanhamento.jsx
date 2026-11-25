import { useMemo, useState } from 'react'
import { EtapaBadge } from '../components/CRMSection.jsx'
import { Badge, Empty, FAIXA, inputCls, Kpi, TIPO } from '../components/ui.jsx'
import { ABERTAS, agenda, crmCSV, ETAPAS, hojeISO, resumoPorDono } from '../lib/crm.js'
import { fmtDate, moneyCompact } from '../lib/format.js'
import { configToText, parseConfigText } from '../lib/private.js'

const somar = (n) => hojeISO(new Date(Date.now() + n * 86400000))

/** CRM: agenda do dia, pedidos do gestor, funil por etapa; gestor vê a equipe e filtra por vendedor. */
export default function Acompanhamento({ data, ctx, onOpen }) {
  const crm = ctx.crm
  const porId = useMemo(() => new Map([...data.items, ...data.atas].map((r) => [r.id, r])), [data])
  const [vendedor, setVendedor] = useState(crm.isGestor ? '' : crm.me)   // '' = toda a equipe (gestor)
  const [busca, setBusca] = useState('')
  const [encerradas, setEncerradas] = useState(false)
  const hoje = hojeISO()

  const visiveis = useMemo(() => {
    const base = crm.isGestor ? (vendedor ? crm.rows.filter((c) => c.dono === vendedor) : crm.rows) : crm.meus
    const q = busca.trim().toLowerCase()
    if (!q) return base
    return base.filter((c) => [c.codigo_oportunidade, c.snapshot?.objeto, c.snapshot?.orgao, c.parceiro, c.observacao, c.item_id]
      .some((v) => (v || '').toLowerCase().includes(q)))
  }, [crm.rows, crm.meus, crm.isGestor, vendedor, busca])
  const ag = useMemo(() => agenda(visiveis, crm.me, hoje), [visiveis, crm.me, hoje])
  const resumo = useMemo(() => resumoPorDono(crm.rows, hoje), [crm.rows, hoje])
  const abertas = visiveis.filter((c) => ABERTAS.includes(c.etapa))
  const valorAberto = abertas.reduce((s, c) => s + (Number(c.valor_negocio ?? c.snapshot?.valor ?? 0) || 0), 0)
  const mostraDono = crm.isGestor && !vendedor && crm.equipe.length > 1

  const abrir = (c) => { const r = porId.get(c.item_id); if (r) onOpen(r) }
  const adiar = (c, n) => crm.salvar({ id: c.item_id, tipo: c.tipo }, { proximo_acompanhamento: somar(n) }, c.dono).catch(() => {})
  const exportar = () => {
    const blob = new Blob([crmCSV(visiveis, crm.nomeDe)], { type: 'text/csv;charset=utf-8' })
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `crm-radar-tls-${hoje}.csv` })
    a.click(); URL.revokeObjectURL(a.href)
  }
  const card = (c, extra) => <CrmCard key={c.id} c={c} r={porId.get(c.item_id)} crm={crm} hoje={hoje} mostraDono={mostraDono} onOpen={abrir} onAdiar={adiar} extra={extra} />

  return (
    <div className="flex flex-col gap-6">
      {!crm.shared ? (
        <p className="border-l-4 border-warn bg-white px-3 py-2 text-[12px]">
          CRM salvo <strong>somente neste navegador</strong> (Supabase não configurado — ver README).
        </p>
      ) : null}
      {crm.error || ctx.favoritos.error ? <p className="text-[12px] text-bad">Erro no banco: {crm.error || ctx.favoritos.error}</p> : null}

      <div className="flex flex-wrap items-end gap-3">
        {crm.isGestor && crm.equipe.length > 1 ? (
          <label className="flex w-64 flex-col gap-1 text-[11px] text-ink-2">Vendedor
            <select className={inputCls} value={vendedor} onChange={(e) => setVendedor(e.target.value)} aria-label="Vendedor">
              <option value="">Toda a equipe</option>
              {crm.equipe.map((u) => <option key={u.user_id} value={u.user_id}>{crm.nomeDe(u.user_id)}</option>)}
            </select></label>
        ) : null}
        <label className="flex w-72 flex-col gap-1 text-[11px] text-ink-2">Buscar no CRM
          <input className={inputCls} placeholder="código/SC, órgão, objeto, parceiro…" value={busca} onChange={(e) => setBusca(e.target.value)} /></label>
        <button className="ml-auto h-9 px-3 text-[13px] text-brand ring-1 ring-line hover:bg-brand-soft" onClick={exportar} disabled={!visiveis.length}>Exportar CSV</button>
      </div>

      <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-5">
        <Kpi label="Acompanhamentos de hoje" value={ag.hoje.length} accent={ag.atrasados ? '#da1e28' : '#0f62fe'} hint={ag.atrasados ? `${ag.atrasados} atrasado(s)` : 'em dia'} />
        <Kpi label="Pedidos do gestor" value={ag.pedidos.length} accent="#6929c4" hint="ainda não vistos" />
        <Kpi label="Em aberto" value={abertas.length} hint={`${ag.semData.length} sem data de acompanhamento`} />
        <Kpi label="Proposta / negociação" value={visiveis.filter((c) => ['proposta', 'negociacao'].includes(c.etapa)).length} accent="#8a3ffc" />
        <Kpi label="Valor em aberto" value={moneyCompact(valorAberto) || 'R$ 0'} hint="valor do negócio ou estimado" />
      </div>

      {mostraDono && crm.equipe.length > 1 ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-[16px] font-semibold">Equipe</h2>
          <div className="overflow-x-auto bg-white">
            <table className="w-full text-left text-[13px]">
              <thead className="text-[11px] text-muted"><tr>
                <th className="px-3 py-2">Vendedor</th><th className="px-3 text-right">Em aberto</th><th className="px-3 text-right">Hoje</th>
                <th className="px-3 text-right">Atrasados</th><th className="px-3 text-right">Pedidos não vistos</th><th className="px-3 text-right">Proposta/negoc.</th>
                <th className="px-3 text-right">Ganhos</th><th className="px-3 text-right">Valor em aberto</th></tr></thead>
              <tbody>
                {crm.equipe.map((u) => {
                  const s = resumo[u.user_id] || {}
                  return (
                    <tr key={u.user_id} className="border-t border-line">
                      <td className="px-3 py-2"><button className="text-brand hover:underline" onClick={() => setVendedor(u.user_id)}>{crm.nomeDe(u.user_id)}</button>
                        {u.papel !== 'usuario' ? <span className="ml-1 text-[11px] text-muted">({u.papel})</span> : null}</td>
                      <td className="num px-3 text-right">{s.abertas || 0}</td>
                      <td className="num px-3 text-right">{s.hoje || 0}</td>
                      <td className={`num px-3 text-right ${s.atrasados ? 'text-bad' : ''}`}>{s.atrasados || 0}</td>
                      <td className="num px-3 text-right">{s.pedidos || 0}</td>
                      <td className="num px-3 text-right">{s.proposta || 0}</td>
                      <td className="num px-3 text-right">{s.ganhos || 0}</td>
                      <td className="num px-3 text-right">{moneyCompact(s.valorAberto) || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="flex flex-col gap-2 lg:col-span-2">
          <h2 className="text-[16px] font-semibold">Acompanhamentos de hoje{ag.atrasados ? <span className="ml-2 text-[13px] font-normal text-bad">({ag.atrasados} atrasado{ag.atrasados > 1 ? 's' : ''})</span> : null}</h2>
          {ag.hoje.length ? <ul className="flex flex-col gap-px bg-line">{ag.hoje.map((c) => card(c))}</ul>
            : <Empty>Nada para hoje. {ag.semana.length ? `${ag.semana.length} acompanhamento(s) nos próximos 7 dias.` : ''}</Empty>}
          {ag.semana.length ? (
            <details className="bg-white">
              <summary className="cursor-pointer px-3 py-2 text-[13px] text-brand">Próximos 7 dias ({ag.semana.length})</summary>
              <ul className="flex flex-col gap-px bg-line">{ag.semana.map((c) => card(c))}</ul>
            </details>
          ) : null}
        </section>
        <aside className="flex flex-col gap-2">
          <h2 className="text-[16px] font-semibold">Pedidos do gestor</h2>
          {ag.pedidos.length ? (
            <ul className="flex flex-col gap-px bg-line">
              {ag.pedidos.map((c) => card(c, (
                <button className="text-[12px] text-brand hover:underline" onClick={() => crm.marcarVisto(c)}>Ok, vi</button>
              )))}
            </ul>
          ) : <Empty>Nenhum pedido pendente.</Empty>}
        </aside>
      </div>

      <section className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between">
          <h2 className="text-[16px] font-semibold">Funil</h2>
          <button className="text-[13px] text-brand hover:underline" onClick={() => setEncerradas(!encerradas)}>
            {encerradas ? 'ocultar encerradas' : `ver encerradas (${visiveis.length - abertas.length})`}</button>
        </div>
        {!visiveis.length ? <Empty>{crm.loaded ? 'Nenhuma oportunidade no CRM. Abra uma oportunidade e use “Salvar no meu CRM”.' : 'Carregando…'}</Empty> : (
          <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-4">
            {ETAPAS.filter((e) => encerradas || ABERTAS.includes(e.id)).map((e) => {
              const lista = visiveis.filter((c) => c.etapa === e.id)
                .sort((a, b) => (a.proximo_acompanhamento || '9999').localeCompare(b.proximo_acompanhamento || '9999'))
              return (
                <div key={e.id} className="flex min-w-0 flex-col gap-px bg-line" data-etapa={e.id}>
                  <div className="flex items-center justify-between bg-white px-3 py-2" style={{ borderTop: `3px solid ${e.cor}` }}>
                    <strong className="text-[13px]">{e.label}</strong><span className="num text-[12px] text-muted">{lista.length}</span>
                  </div>
                  {lista.map((c) => card(c))}
                  {!lista.length ? <div className="bg-white px-3 py-3 text-[12px] text-muted">—</div> : null}
                </div>
              )
            })}
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <Favoritos data={data} ctx={ctx} onOpen={onOpen} />
        <ConfigEditor ctx={ctx} />
      </div>
    </div>
  )
}

function CrmCard({ c, r, crm, hoje, mostraDono, onOpen, onAdiar, extra }) {
  const s = c.snapshot || {}
  const atrasado = c.proximo_acompanhamento && c.proximo_acompanhamento < hoje && ABERTAS.includes(c.etapa)
  const pedido = c.atribuido_por && c.atribuido_por !== c.dono
  return (
    <li className="flex flex-col gap-1 bg-white p-3" data-crm-id={c.id}>
      <div className="flex flex-wrap items-center gap-1.5">
        <EtapaBadge etapa={c.etapa} />
        {c.codigo_oportunidade ? <span className="font-mono text-[11px] text-ink-2">{c.codigo_oportunidade}</span> : null}
        {mostraDono ? <span className="text-[11px] text-ink-2">· {crm.nomeDe(c.dono)}</span> : null}
        {pedido && !c.visto_em ? <Badge className="bg-[#f6f2ff] text-[#6929c4] ring-[#d4bbff]">pedido de {crm.nomeDe(c.atribuido_por)}</Badge> : null}
      </div>
      {r ? (
        <button className="text-left text-[13px] hover:text-brand" onClick={() => onOpen(c)}><span className="clamp-2">{r.objeto || s.objeto}</span></button>
      ) : (
        <span className="text-[13px]"><span className="clamp-2">{s.objeto || c.item_id}</span>
          <span className="text-[11px] text-muted"> (fora da base publicada{s.pncp ? <> · <a className="text-brand" href={s.pncp} target="_blank" rel="noopener noreferrer">PNCP ↗</a></> : null})</span></span>
      )}
      <div className="text-[11px] text-muted">{r?.orgao?.nome || s.orgao}{s.uf ? ` · ${s.uf}` : ''}
        {c.valor_negocio != null || s.valor ? ` · ${moneyCompact(c.valor_negocio ?? s.valor)}` : ''}</div>
      {pedido && c.mensagem_atribuicao ? <p className="text-[12px] text-[#6929c4]">“{c.mensagem_atribuicao}”</p> : null}
      <div className="flex flex-wrap items-center gap-3 text-[11px]">
        {c.proximo_acompanhamento ? (
          <span className={atrasado ? 'font-semibold text-bad' : 'text-ink-2'}>
            {c.proximo_acompanhamento === hoje ? 'Hoje' : atrasado ? `Atrasado (${fmtDate(c.proximo_acompanhamento)})` : fmtDate(c.proximo_acompanhamento)}</span>
        ) : <span className="text-muted">sem data</span>}
        {ABERTAS.includes(c.etapa) ? (
          <>
            <button className="text-brand hover:underline" onClick={() => onAdiar(c, 1)} title="Próximo acompanhamento amanhã">amanhã</button>
            <button className="text-brand hover:underline" onClick={() => onAdiar(c, 7)} title="Próximo acompanhamento em 1 semana">+1 semana</button>
          </>
        ) : null}
        {extra}
      </div>
    </li>
  )
}

function Favoritos({ data, ctx, onOpen }) {
  const favs = useMemo(() => [...data.items, ...data.atas].filter((r) => ctx.isFav(r.id)), [data, ctx])
  return (
    <section className="flex flex-col gap-2 lg:col-span-2">
      <h2 className="text-[16px] font-semibold">Meus favoritos <span className="text-[12px] font-normal text-muted">(pessoais)</span></h2>
      {!favs.length ? <Empty>Nenhum favorito. Use a estrela nas oportunidades.</Empty> : (
        <ul className="flex flex-col gap-px bg-line">
          {favs.map((r) => (
            <li key={r.id} className="flex items-start gap-3 bg-white p-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap gap-1.5">
                  <Badge className="bg-ink text-white ring-ink">{TIPO[r.tipo]}</Badge>
                  {ctx.crm.doItem(r.id).filter((c) => c.dono === ctx.crm.me).map((c) => <EtapaBadge key={c.id} etapa={c.etapa} />)}
                </div>
                <button className="mt-1 block text-left text-[13px] hover:text-brand" onClick={() => onOpen(r)}><span className="clamp-2">{r.objeto}</span></button>
                <div className="text-[11px] text-muted">{r.orgao?.nome}</div>
              </div>
              {r.classificacao?.score != null ? (
                <span className="num text-[18px] font-semibold" style={{ color: (FAIXA[r.classificacao.faixa] || FAIXA.baixa).bar }}>{r.classificacao.score}</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ConfigEditor({ ctx }) {
  const { config, save, shared } = ctx.commercial
  const [text, setText] = useState(() => configToText(config))
  const [msg, setMsg] = useState('')
  const [open, setOpen] = useState(false)
  return (
    <section className="self-start bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-semibold">Configuração comercial privada</h2>
        <button className="text-[12px] text-brand hover:underline" onClick={() => { setText(configToText(config)); setOpen(!open) }}>{open ? 'fechar' : 'editar'}</button>
      </div>
      <p className="mt-1 text-[11px] text-muted">
        Órgãos prioritários ({config.priority_orgs.length}), parceiros de referência ({config.partners.length}) e notas por fabricante
        ({Object.keys(config.vendor_notes || {}).length}). {shared ? 'Compartilhada com a equipe (banco protegido por login).' : 'Salva somente neste navegador.'} Nunca é publicada no site.
      </p>
      {open ? (
        <div className="mt-2 flex flex-col gap-2">
          <textarea rows={14} className={`${inputCls} h-auto py-2 font-mono text-[12px]`} value={text} onChange={(e) => setText(e.target.value)} />
          <button className="bg-ink py-1.5 text-[13px] text-white" onClick={async () => {
            try { await save(parseConfigText(text)); setMsg('Configuração salva.') } catch (e) { setMsg(`Erro: ${e.message}`) }
          }}>Salvar configuração</button>
          <span className="text-[12px] text-muted">{msg}</span>
        </div>
      ) : null}
    </section>
  )
}

