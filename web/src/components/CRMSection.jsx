import { useCallback, useEffect, useState } from 'react'
import { ETAPA, ETAPAS, EVENTO, hojeISO } from '../lib/crm.js'
import { fmtDate, money } from '../lib/format.js'
import { Badge, inputCls } from './ui.jsx'

const somar = (n) => hojeISO(new Date(Date.now() + n * 86400000))
const lbl = 'flex flex-col gap-1 text-[11px] text-ink-2'

export function EtapaBadge({ etapa }) {
  const e = ETAPA[etapa] || ETAPA.novo
  return <span title="Etapa no CRM" className="inline-flex items-center whitespace-nowrap px-1.5 py-0.5 text-[11px] font-medium text-white" style={{ background: e.cor }}>{e.label}</span>
}

/** Seção "Acompanhamento comercial (CRM)" do detalhe de uma oportunidade. */
export default function CRMSection({ r, ctx, Section }) {
  const crm = ctx.crm
  const linhas = crm.doItem(r.id)
  const [dono, setDono] = useState(crm.me)
  const c = linhas.find((x) => x.dono === dono)
  const outros = linhas.filter((x) => x.dono !== dono)

  // pedido do gestor visto quando o próprio vendedor abre a oportunidade
  useEffect(() => {
    const meu = linhas.find((x) => x.dono === crm.me)
    if (meu && meu.atribuido_por && meu.atribuido_por !== crm.me && !meu.visto_em) crm.marcarVisto(meu)
  }, [linhas.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const right = <span className="text-[11px] text-muted">{crm.shared ? (crm.isGestor ? 'Você é gestor: vê o CRM de toda a equipe' : 'Seu CRM pessoal') : 'Somente neste navegador'}</span>
  return (
    <Section title="Acompanhamento comercial (CRM)" right={right}>
      {crm.error ? <p className="mb-2 text-[12px] text-bad">Erro no banco: {crm.error}</p> : null}
      {crm.isGestor && crm.equipe.length > 1 ? (
        <label className="mb-3 flex max-w-sm flex-col gap-1 text-[11px] text-ink-2">CRM de
          <select className={inputCls} value={dono} onChange={(e) => setDono(e.target.value)}>
            {crm.equipe.map((u) => <option key={u.user_id} value={u.user_id}>{crm.nomeDe(u.user_id)}{linhas.some((x) => x.dono === u.user_id) ? ' ✓' : ''}</option>)}
          </select>
        </label>
      ) : null}
      {outros.length ? (
        <p className="mb-2 text-[12px] text-ink-2">Também no CRM de: {outros.map((x) => (
          <button key={x.id} className="mr-2 text-brand hover:underline" onClick={() => setDono(x.dono)} disabled={!crm.isGestor}>
            {crm.nomeDe(x.dono)} ({ETAPA[x.etapa]?.label})</button>))}
        </p>
      ) : null}
      {c ? <Ficha key={c.id} c={c} r={r} ctx={ctx} /> : <Novo r={r} ctx={ctx} dono={dono} />}
    </Section>
  )
}

function Novo({ r, ctx, dono }) {
  const crm = ctx.crm
  const [msg, setMsg] = useState('')
  const [pedido, setPedido] = useState({ para: '', mensagem: '', data: '' })
  const outro = dono !== crm.me
  const vendedores = crm.equipe.filter((u) => u.user_id !== crm.me)
  const add = async (patch, para = dono) => {
    try { await crm.salvar(r, patch, para); setMsg('') } catch (e) { setMsg(`Erro: ${e.message}`) }
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button className="bg-brand px-4 py-1.5 text-[13px] text-white hover:bg-brand-dark"
          onClick={() => add({ etapa: 'novo', proximo_acompanhamento: somar(1) })}>
          {outro ? `Adicionar ao CRM de ${crm.nomeDe(dono)}` : '+ Salvar no meu CRM'}</button>
        <span className="text-[11px] text-muted">Entra na etapa “Novo” com acompanhamento para amanhã (dá para mudar depois).</span>
      </div>
      {crm.isGestor && crm.shared && vendedores.length ? (
        <form className="flex flex-col gap-2 border-l-2 border-purple bg-[#f6f2ff] p-3" onSubmit={(e) => {
          e.preventDefault()
          if (!pedido.para) return
          add({ etapa: 'novo', atribuido_por: crm.me, mensagem_atribuicao: pedido.mensagem.trim() || null,
            proximo_acompanhamento: pedido.data || somar(1) }, pedido.para).then(() => setMsg(`Pedido enviado para ${crm.nomeDe(pedido.para)}.`))
        }}>
          <strong className="text-[12px]">Pedir para um vendedor olhar esta oportunidade</strong>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <label className={lbl}>Vendedor
              <select className={inputCls} value={pedido.para} required onChange={(e) => setPedido({ ...pedido, para: e.target.value })}>
                <option value="">Escolha…</option>
                {vendedores.map((u) => <option key={u.user_id} value={u.user_id}>{u.nome || u.usuario}</option>)}
              </select></label>
            <label className={`${lbl} sm:col-span-2`}>Mensagem
              <input className={inputCls} maxLength={500} placeholder="ex.: cliente da sua carteira, vê se dá para entrar com parceiro"
                value={pedido.mensagem} onChange={(e) => setPedido({ ...pedido, mensagem: e.target.value })} /></label>
            <label className={lbl}>Acompanhar em
              <input type="date" className={inputCls} value={pedido.data} onChange={(e) => setPedido({ ...pedido, data: e.target.value })} /></label>
          </div>
          <button className="self-start bg-ink px-3 py-1.5 text-[12px] text-white hover:bg-ink-2">Enviar pedido</button>
        </form>
      ) : null}
      {msg ? <p role="status" className="text-[12px]">{msg}</p> : null}
    </div>
  )
}

function Ficha({ c, r, ctx }) {
  const crm = ctx.crm
  const vazio = (v) => (v == null ? '' : String(v))
  const [f, setF] = useState(() => ({
    etapa: c.etapa, proximo_acompanhamento: vazio(c.proximo_acompanhamento), codigo_oportunidade: vazio(c.codigo_oportunidade),
    valor_negocio: vazio(c.valor_negocio), parceiro: vazio(c.parceiro), motivo_perda: vazio(c.motivo_perda), observacao: vazio(c.observacao),
  }))
  const [msg, setMsg] = useState('')
  const [hist, setHist] = useState(null)
  const [texto, setTexto] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const carregarHist = useCallback(() => crm.eventos(c.id).then(setHist).catch(() => setHist([])), [crm, c.id])
  useEffect(() => { carregarHist() }, [carregarHist, c.atualizado_em])

  const salvar = async (extra = {}) => {
    const g = { ...f, ...extra }
    const valor = g.valor_negocio === '' ? null : Number(String(g.valor_negocio).replace(/\./g, '').replace(',', '.'))
    if (valor != null && !(valor >= 0)) { setMsg('Valor do negócio inválido.'); return }
    const patch = {
      etapa: g.etapa, proximo_acompanhamento: g.proximo_acompanhamento || null, codigo_oportunidade: g.codigo_oportunidade.trim() || null,
      valor_negocio: valor, parceiro: g.parceiro.trim() || null, observacao: g.observacao.trim() || null,
      motivo_perda: ['perdido', 'descartado'].includes(g.etapa) ? (g.motivo_perda.trim() || null) : null,
    }
    try { await crm.salvar(r, patch, c.dono); setF(g); setMsg('Salvo.') } catch (e) { setMsg(`Erro: ${e.message}`) }
  }
  const pedido = c.atribuido_por && c.atribuido_por !== c.dono
  const atrasado = c.proximo_acompanhamento && c.proximo_acompanhamento < hojeISO() && ['novo', 'qualificando', 'proposta', 'negociacao'].includes(c.etapa)

  return (
    <div className="flex flex-col gap-3">
      {pedido ? (
        <p className="border-l-2 border-purple bg-[#f6f2ff] px-3 py-2 text-[12px]">
          <strong>{crm.nomeDe(c.atribuido_por)}</strong> pediu para {c.dono === crm.me ? 'você' : crm.nomeDe(c.dono)} olhar esta oportunidade
          {c.atribuido_em ? ` em ${fmtDate(c.atribuido_em)}` : ''}{c.mensagem_atribuicao ? `: “${c.mensagem_atribuicao}”` : '.'}
          {c.visto_em ? <span className="text-muted"> · visto em {fmtDate(c.visto_em, true)}</span> : <span className="text-muted"> · ainda não visto</span>}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-1" role="group" aria-label="Etapa">
        {ETAPAS.map((e) => (
          <button key={e.id} type="button" aria-pressed={f.etapa === e.id} onClick={() => setF({ ...f, etapa: e.id })}
            className={`px-2.5 py-1 text-[12px] ring-1 ${f.etapa === e.id ? 'text-white' : 'bg-white text-ink-2 ring-line hover:bg-field'}`}
            style={f.etapa === e.id ? { background: e.cor, '--tw-ring-color': e.cor } : undefined}>{e.label}</button>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className={lbl}>Próximo acompanhamento
          <input type="date" className={`${inputCls} ${atrasado ? 'text-bad' : ''}`} value={f.proximo_acompanhamento} onChange={set('proximo_acompanhamento')} />
          <span className="flex gap-2 text-[11px]">
            {[['amanhã', 1], ['+3 dias', 3], ['+1 semana', 7]].map(([t, n]) => (
              <button key={t} type="button" className="text-brand hover:underline" onClick={() => setF({ ...f, proximo_acompanhamento: somar(n) })}>{t}</button>))}
          </span></label>
        <label className={lbl}>Código da oportunidade / SC
          <input className={`${inputCls} font-mono`} maxLength={60} placeholder="ex.: SC 1234567 / OPP-…" value={f.codigo_oportunidade} onChange={set('codigo_oportunidade')} /></label>
        <label className={lbl}>Valor do negócio (R$)
          <input className={`${inputCls} num`} inputMode="decimal" placeholder={r.valor_estimado ? money(r.valor_estimado) : 'ex.: 250000'} value={f.valor_negocio} onChange={set('valor_negocio')} /></label>
        <label className={lbl}>Parceiro
          <input className={inputCls} maxLength={120} list="crm-parceiros" value={f.parceiro} onChange={set('parceiro')} />
          <datalist id="crm-parceiros">{(ctx.config?.partners || []).map((p) => <option key={p} value={p} />)}</datalist></label>
        {['perdido', 'descartado'].includes(f.etapa) ? (
          <label className={`${lbl} sm:col-span-2`}>Motivo {f.etapa === 'perdido' ? 'da perda' : 'do descarte'}
            <input className={inputCls} maxLength={500} placeholder="preço, prazo, sem atestado, sem parceiro, fora do escopo…" value={f.motivo_perda} onChange={set('motivo_perda')} /></label>
        ) : null}
        <label className={`${lbl} sm:col-span-3`}>Observação
          <textarea rows={3} maxLength={4000} className={`${inputCls} h-auto py-2`} value={f.observacao} onChange={set('observacao')} /></label>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={() => salvar()} className="bg-ink px-4 py-1.5 text-[13px] text-white hover:bg-ink-2">Salvar no CRM</button>
        <span role="status" className="text-[12px] text-muted">{msg}</span>
        <span className="text-[11px] text-muted">Última alteração: {fmtDate(c.atualizado_em, true)}{c.atualizado_por ? ` por ${crm.nomeDe(c.atualizado_por)}` : ''}</span>
        <button className="ml-auto text-[12px] text-bad hover:underline" onClick={async () => {
          if (!window.confirm('Tirar esta oportunidade do CRM? O histórico dela também é apagado.')) return
          try { await crm.remover(c.id) } catch (e) { setMsg(`Erro: ${e.message}`) }
        }}>Remover do CRM</button>
      </div>

      <div className="border-t border-line pt-3">
        <h4 className="mb-2 text-[12px] font-semibold">Histórico</h4>
        <form className="mb-2 flex gap-2" onSubmit={async (e) => {
          e.preventDefault()
          if (!texto.trim()) return
          try { await crm.nota(c.id, texto.trim()); setTexto(''); carregarHist() } catch (x) { setMsg(`Erro: ${x.message}`) }
        }}>
          <input className={inputCls} maxLength={2000} placeholder="Registrar contato, reunião, próximo passo…" value={texto} onChange={(e) => setTexto(e.target.value)} aria-label="Nova nota" />
          <button className="shrink-0 bg-field px-3 text-[12px] ring-1 ring-line hover:bg-line">Adicionar nota</button>
        </form>
        {hist === null ? <p className="text-[12px] text-muted">Carregando…</p> : (
          <ul className="flex flex-col gap-1.5 text-[12px]">
            {hist.map((e) => (
              <li key={e.id} className="flex gap-2">
                <span className="num w-28 shrink-0 text-muted">{fmtDate(e.criado_em, true)}</span>
                <span><strong>{EVENTO[e.tipo] || e.tipo}</strong>{e.texto ? `: ${e.tipo === 'etapa' ? e.texto.split(' → ').map((x) => ETAPA[x]?.label || x).join(' → ') : e.texto}` : ''}
                  <span className="text-muted"> — {crm.nomeDe(e.autor)}</span></span>
              </li>
            ))}
            {!hist.length ? <li className="text-muted">Sem registros.</li> : null}
          </ul>
        )}
      </div>
    </div>
  )
}
