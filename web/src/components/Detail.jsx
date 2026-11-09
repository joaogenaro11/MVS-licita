import { useEffect, useState } from 'react'
import { ESFERAS, fmtDate, money } from '../lib/format.js'
import { matchesPartner, matchesPriority } from '../lib/filters.js'
import { STATUS_COMERCIAL } from '../lib/private.js'
import { ADESAO, Badge, dateOrNA, ExtLink, FAIXA, FamiliaChips, Highlight, inputCls, KV, PortalLinks, PortfolioBadge, RELACAO, ScoreBadge, Selos, Star, TIPO, valueOrNA, VIGENCIA } from './ui.jsx'

function Section({ title, children, right }) {
  return (
    <section className="border-t border-line px-5 py-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-[14px] font-semibold">{title}</h3>{right}
      </div>
      {children}
    </section>
  )
}

export default function Detail({ r, meta, ctx, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [onClose])
  if (!r) return null
  const c = r.classificacao || {}
  const L = meta.lookups || {}
  const isAta = r.tipo === 'ata'
  const notes = Object.entries(ctx.config?.vendor_notes || {}).filter(([v]) => (c.termos || []).some((t) => t.toLowerCase() === v.toLowerCase()))
  const partners = matchesPartner(r, ctx.config?.partners)
  const prio = matchesPriority(r, ctx.priorityOrgs)

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose} role="dialog" aria-modal="true">
      <div className="h-full w-full max-w-3xl overflow-y-auto bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <header className="sticky top-0 z-10 flex items-start gap-3 border-b border-line bg-white px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex flex-wrap gap-1.5">
              <Badge className="bg-ink text-white ring-ink">{TIPO[r.tipo]}</Badge>
              <Badge>{(L.estagios || {})[r.estagio] || r.estagio}</Badge>
              {isAta && VIGENCIA[r.vigencia_status] ? <Badge className={VIGENCIA[r.vigencia_status].cls}>{VIGENCIA[r.vigencia_status].label}</Badge> : null}
              {isAta && ADESAO[r.adesao_status] ? <Badge className={ADESAO[r.adesao_status].cls}>{ADESAO[r.adesao_status].label}</Badge> : null}
              {prio ? <Badge className="bg-[#f6f2ff] text-[#6929c4] ring-[#d4bbff]">Órgão prioritário</Badge> : null}
            </div>
            <div className="text-[13px] font-medium">{r.orgao?.nome}</div>
            <div className="font-mono text-[11px] text-muted">{r.id}</div>
          </div>
          <Star on={ctx.isFav(r.id)} onClick={() => ctx.toggleFav(r)} />
          <button onClick={onClose} className="px-2 text-[22px] leading-none text-ink-2 hover:text-ink" aria-label="Fechar">×</button>
        </header>

        <div className="px-5 py-4">
          <p className="whitespace-pre-line text-[15px] leading-relaxed">{r.objeto ? <Highlight text={r.objeto} terms={c.termos} /> : 'Objeto não informado'}</p>
          {r.info_complementar && r.info_complementar !== r.objeto ? (
            <p className="mt-2 whitespace-pre-line text-[13px] text-ink-2"><span className="text-muted">Informação complementar: </span><Highlight text={r.info_complementar} terms={c.termos} /></p>
          ) : null}
          <div className="mt-4">
            <PortalLinks links={r.links} />
            {isAta && r.links?.pncp_compra ? (
              <div className="mt-2"><ExtLink href={r.links.pncp_compra} className="text-[13px] text-brand hover:underline">Contratação de origem no PNCP ↗</ExtLink></div>
            ) : null}
            <p className="mt-2 text-[11px] text-muted">
              Link do portal de origem conforme informado pelo órgão ao PNCP (campo oficial). Os links abrem em nova aba.
            </p>
          </div>
        </div>

        <Section title="Por que apareceu" right={<ScoreBadge c={c} />}>
          {c.justificativa ? <p className="mb-3 text-[13px]">{c.justificativa}</p> : null}
          {c.score != null ? (
            <div className="mb-3 grid grid-cols-1 gap-x-6 sm:grid-cols-2">
              <KV k="Aderência técnica / urgência comercial" v={`${c.score_tecnico}/100 · ${c.score_comercial}/100`} />
              <KV k="Faixa" v={FAIXA[c.faixa]?.label} />
              <KV k="Relação com TLS" v={RELACAO[c.relacao]} />
              <KV k="Tipo de serviço identificado" v={c.tipo_servico_label} />
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-1.5">
            <FamiliaChips c={c} familias={ctx.familias} />
            <PortfolioBadge c={c} />
          </div>
          {(c.ofertas_casadas || []).length ? (
            <ul className="mt-3 flex flex-col gap-1.5 text-[13px]">
              {c.ofertas_casadas.map((o) => (
                <li key={o.id}><strong>{o.nome_pt}</strong>
                  <span className="text-[12px] text-ink-2"> — {o.via === 'termo_exato' ? 'termo exato' : 'marca + serviço'}: </span>
                  {o.termos.map((t) => <mark key={t} className="mr-1 bg-[#fcf4d6] px-0.5 text-[12px]">{t}</mark>)}
                </li>
              ))}
            </ul>
          ) : null}
          {(c.familias_casadas || []).length ? (
            <ul className="mt-3 flex flex-col gap-1.5 text-[13px]">
              {c.familias_casadas.map((f) => (
                <li key={f.id}><strong>{f.nome}</strong>
                  <span className="text-[12px] text-ink-2"> — pela família (sem oferta específica): </span>
                  {f.termos.map((t) => <mark key={t} className="mr-1 bg-[#fcf4d6] px-0.5 text-[12px]">{t}</mark>)}
                </li>
              ))}
            </ul>
          ) : null}
          {!c.tls ? <p className="mt-2 text-[13px] text-muted">Nenhuma oferta nem família da base casou com o texto atual deste registro (mantido no Radar até vencer).</p> : null}
          {(c.selos || []).length ? <div className="mt-3"><Selos c={c} detalhe /></div> : null}
          {notes.length ? (
            <ul className="mt-3 border-l-2 border-purple bg-[#f6f2ff] px-3 py-2 text-[12px]">
              {notes.map(([n, t]) => <li key={n}><strong>{n}:</strong> {t}</li>)}
              <li className="text-[11px] text-muted">Nota comercial interna (configuração da equipe).</li>
            </ul>
          ) : null}
          <p className="mt-3 text-[11px] text-muted">
            Nota 0–100 = aderência técnica (portfólio, suporte, fabricante, evidências) + urgência comercial (valor e
            estágio), esta reduzida quando a aderência técnica é baixa. Faixas: 80+ alta prioridade · 60+ analisar ·
            40+ potencial indireto. Analisados: objeto, informação complementar{r.itens?.length ? ' e itens' : ''} publicados
            no PNCP (PDFs não são lidos). Validação humana necessária.
          </p>
        </Section>

        {isAta ? <AtaSection r={r} partners={partners} /> : <DadosSection r={r} />}

        {(r.itens || []).length ? (
          <Section title={`Itens (${r.itens_total ?? r.itens.length})`}>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[12px]">
                <thead className="text-muted"><tr><th className="py-1 pr-2">#</th><th className="pr-2">Descrição</th><th className="pr-2 text-right">Qtd.</th><th className="text-right">Valor total</th></tr></thead>
                <tbody>
                  {r.itens.map((i) => (
                    <tr key={i.numero} className="border-t border-line align-top">
                      <td className="py-1 pr-2 num">{i.numero}</td><td className="pr-2"><Highlight text={i.descricao} terms={c.termos} /></td>
                      <td className="num pr-2 text-right">{i.quantidade ?? '—'} {i.unidade || ''}</td>
                      <td className="num text-right">{i.sigiloso ? 'sigiloso' : money(i.valor_total) || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        ) : null}

        <Docs title="Documentos oficiais" docs={r.documentos} />
        {isAta ? <Docs title="Documentos da contratação de origem (edital/TR)" docs={r.documentos_compra} /> : null}

        <Tracking r={r} ctx={ctx} />

        <Section title="Coleta">
          <div className="grid grid-cols-2 gap-x-6 sm:grid-cols-4">
            <KV k="Fonte" v={r.fonte} />
            <KV k="Coletado pelo Radar em" v={fmtDate(r.coletado_em, true)} />
            <KV k="Última alteração detectada" v={fmtDate(r.atualizado_em, true)} />
            <KV k="Atualização na fonte" v={fmtDate(r.data_atualizacao_fonte, true)} />
            <KV k="Itens/documentos coletados em" v={r.enriquecido_em ? fmtDate(r.enriquecido_em, true) : 'Ainda não coletados'} />
            <KV k="Fica no Radar até" v={r.vence_em ? `${fmtDate(r.vence_em)} (${r.vence_motivo})` : (r.vence_motivo || 'Sem data de vencimento')} />
          </div>
        </Section>
      </div>
    </div>
  )
}

function DadosSection({ r }) {
  return (
    <Section title="Dados da contratação">
      <dl className="grid grid-cols-2 gap-x-6 sm:grid-cols-3">
        <KV k="Órgão" v={r.orgao?.nome} />
        <KV k="Esfera" v={ESFERAS[r.orgao?.esfera]} />
        <KV k="Unidade compradora" v={r.unidade?.nome} />
        <KV k="UF / Município" v={[r.unidade?.uf, r.unidade?.municipio].filter(Boolean).join(' / ') || null} />
        <KV k="Número / Processo" v={[r.numero, r.processo].filter(Boolean).join(' · ') || null} />
        <KV k="Modalidade" v={r.modalidade?.nome} />
        <KV k="Modo de disputa" v={r.modo_disputa} />
        <KV k="Instrumento" v={r.instrumento} />
        <KV k="Amparo legal" v={r.amparo_legal} />
        <KV k="Registro de preços (SRP)" v={r.tipo === 'contratacao' ? (r.srp ? 'Sim' : 'Não') : null} />
        <KV k="Situação" v={r.situacao} />
        <KV k="Valor estimado" v={valueOrNA(r.valor_estimado)} />
        <KV k="Valor homologado" v={valueOrNA(r.valor_homologado)} />
        <KV k="Publicação no PNCP" v={dateOrNA(r.data_publicacao, true)} />
        <KV k="Abertura de propostas" v={dateOrNA(r.data_abertura_proposta, true)} />
        <KV k="Encerramento de propostas" v={dateOrNA(r.data_encerramento_proposta, true)} />
        {r.tipo === 'pca' ? <>
          <KV k="Ano do PCA" v={r.ano} />
          <KV k="Categoria" v={r.categoria} />
          <KV k="Data desejada" v={dateOrNA(r.data_desejada)} />
          <KV k="Unidade requisitante" v={r.unidade_requisitante} />
          <KV k="Classificação" v={r.classificacao_superior?.nome} />
        </> : null}
        {r.tipo === 'contrato' ? <>
          <KV k="Fornecedor" v={r.fornecedor?.nome} />
          <KV k="Vigência" v={`${dateOrNA(r.vigencia_inicio)} a ${dateOrNA(r.vigencia_fim)}`} />
          <KV k="Fruto de adesão a ata" v={r.fruto_adesao ? 'Sim' : 'Não'} />
        </> : null}
      </dl>
    </Section>
  )
}

function AtaSection({ r, partners }) {
  return (
    <Section title="Ata de registro de preços">
      <dl className="grid grid-cols-2 gap-x-6 sm:grid-cols-3">
        <KV k="Órgão gerenciador" v={r.orgao?.nome} />
        <KV k="Esfera do gerenciador" v={ESFERAS[r.orgao?.esfera]} />
        <KV k="Unidade" v={r.unidade?.nome} />
        <KV k="Número da ata" v={r.numero} />
        <KV k="Assinatura" v={dateOrNA(r.data_assinatura)} />
        <KV k="Início da vigência" v={dateOrNA(r.vigencia_inicio)} />
        <KV k="Fim da vigência" v={r.vigencia_status === 'inconsistente'
          ? `Data publicada inconsistente (${r.vigencia_fim_publicada}) — conferir na ata`
          : dateOrNA(r.vigencia_fim)} />
        <KV k="Situação" v={VIGENCIA[r.vigencia_status]?.label} />
        <KV k="Dias para o vencimento" v={r.dias_para_vencer ?? null} />
        <KV k={`Valor ${r.compra?.valor_tipo || ''} da contratação de origem`} v={valueOrNA(r.compra?.valor)} />
        <KV k="Modalidade de origem" v={r.compra?.modalidade} />
        <KV k="Campo oficial 'possibilidadeAdesao'" v={r.possibilidade_adesao_pncp === true ? 'Sim' : r.possibilidade_adesao_pncp === false ? 'Não' : 'Não informado'} />
      </dl>
      <div className="mt-3">
        <div className="text-[11px] text-muted">Fornecedor(es)/detentor(es) identificados</div>
        {(r.fornecedores || []).length ? (
          <ul className="text-[13px]">{r.fornecedores.map((f) => <li key={f.ni || f.nome}>{f.nome} <span className="font-mono text-[11px] text-muted">{f.ni}</span>
            {partners.some((p) => (f.nome || '').toUpperCase().includes(p.toUpperCase())) ? <Badge className="ml-1 bg-[#f6f2ff] text-[#6929c4] ring-[#d4bbff]">Parceiro de referência</Badge> : null}</li>)}</ul>
        ) : <p className="text-[13px] text-muted">Não identificado nos dados coletados (consultar a ata).</p>}
        <p className="mt-1 text-[11px] text-muted">Identificados a partir de contratos publicados no PNCP que referenciam a ata. Saldo/quantitativos não são verificados.</p>
      </div>
      <div className="mt-4 border-l-2 border-purple bg-[#f6f2ff] px-3 py-2 text-[12px]">
        <div className="font-semibold">{ADESAO[r.adesao_status]?.label}</div>
        <ul className="mt-1 list-disc pl-4">{(r.adesao_motivos || []).map((m) => <li key={m}>{m}</li>)}</ul>
        {r.alerta_esfera_federal ? (
          <p className="mt-1">Gerenciador não federal: órgãos e entidades federais não podem aderir (Lei 14.133/2021, art. 86, §8º).</p>
        ) : null}
        <p className="mt-1 text-muted">
          Indicação preliminar, sem análise jurídica. A adesão por não participantes exige previsão no edital, justificativa,
          compatibilidade de preços, aceite do gerenciador e do fornecedor e respeito aos limites legais (Lei 14.133/2021, art. 86).
        </p>
      </div>
      {(r.contratos || []).length ? (
        <div className="mt-3 text-[12px]">
          <div className="text-[11px] text-muted">Contratos vinculados publicados no PNCP</div>
          <ul>{r.contratos.slice(0, 10).map((c) => <li key={c.contrato}>{c.orgao} · {fmtDate(c.data_assinatura) || 's/ data'} · {money(c.valor) || 'valor n/i'}{c.fruto_adesao ? ' · adesão' : ''}</li>)}</ul>
        </div>
      ) : null}
    </Section>
  )
}

function Docs({ title, docs }) {
  if (!docs) return null
  return (
    <Section title={title}>
      {docs.length ? (
        <ul className="flex flex-col gap-1 text-[13px]">
          {docs.map((d) => (
            <li key={d.url}><ExtLink href={d.url} className="text-brand hover:underline">{d.titulo}</ExtLink>
              <span className="text-[11px] text-muted"> · {d.tipo || 'documento'}{d.data ? ` · ${fmtDate(d.data)}` : ''}</span></li>
          ))}
        </ul>
      ) : <p className="text-[13px] text-muted">Nenhum documento publicado no PNCP até a última coleta.</p>}
    </Section>
  )
}

function Tracking({ r, ctx }) {
  const t = ctx.tracking.rows[r.id] || {}
  const [form, setForm] = useState({ status: t.status || '', responsavel: t.responsavel || '', observacao: t.observacao || '', proximo_acompanhamento: t.proximo_acompanhamento || '' })
  const [msg, setMsg] = useState('')
  const shared = ctx.tracking.shared
  const save = async () => {
    try { await ctx.tracking.save(r.id, r.tipo, form); setMsg('Salvo.') } catch (e) { setMsg(`Erro: ${e.message}`) }
  }
  return (
    <Section title="Acompanhamento comercial (equipe)" right={<span className="text-[11px] text-muted">{shared ? 'Compartilhado com a equipe' : 'Somente neste navegador'}</span>}>
      {!shared ? (
        <p className="mb-2 text-[12px] text-[#8e6a00]">Banco compartilhado não configurado: estes dados ficam apenas neste computador/navegador.</p>
      ) : <p className="mb-2 text-[11px] text-muted">Status, responsável e observação são vistos por toda a equipe. O favorito (estrela) é pessoal.</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-[11px] text-ink-2">Status comercial
          <select className={inputCls} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            <option value="">—</option>{STATUS_COMERCIAL.map((s) => <option key={s}>{s}</option>)}
          </select></label>
        <label className="flex flex-col gap-1 text-[11px] text-ink-2">Responsável
          <input className={inputCls} value={form.responsavel} onChange={(e) => setForm({ ...form, responsavel: e.target.value })} /></label>
        <label className="flex flex-col gap-1 text-[11px] text-ink-2">Próximo acompanhamento
          <input type="date" className={inputCls} value={form.proximo_acompanhamento} onChange={(e) => setForm({ ...form, proximo_acompanhamento: e.target.value })} /></label>
        <label className="flex flex-col gap-1 text-[11px] text-ink-2 sm:col-span-3">Observação
          <textarea rows={3} className={`${inputCls} h-auto py-2`} value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} /></label>
      </div>
      <div className="mt-2 flex items-center gap-3">
        <button onClick={save} className="bg-ink px-4 py-1.5 text-[13px] text-white hover:bg-ink-2">Salvar acompanhamento</button>
        <span className="text-[12px] text-muted">{msg}</span>
        {t.updated_by ? <span className="text-[11px] text-muted">Última edição: {t.updated_by} em {fmtDate(t.updated_at, true)}</span> : null}
      </div>
    </Section>
  )
}
