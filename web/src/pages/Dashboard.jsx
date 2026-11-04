import { useMemo } from 'react'
import { Kpi } from '../components/ui.jsx'
import { fmtDate, moneyCompact } from '../lib/format.js'
import { aggregateValue, SORTS } from '../lib/filters.js'
import { OppCard } from './Oportunidades.jsx'
import { AtaCard } from './Atas.jsx'

const FONTE_LABEL = {
  contratacoes_atualizacao: 'Contratações (atualizações diárias)',
  propostas_abertas: 'Contratações com propostas abertas',
  atas_atualizacao: 'Atas (atualizações diárias)',
  contratos_atualizacao: 'Contratos (atualizações diárias)',
  pca: 'Planos de Contratações Anuais (PCA)',
  atas_varredura: 'Varredura de atas vigentes',
  backfill_contratacoes: 'Carga histórica de contratações (12 meses)',
  backfill_contratos: 'Carga histórica de contratos',
  enriquecimento: 'Itens e documentos oficiais',
}
const STATUS = { ok: ['OK', '#198038'], parcial: ['Parcial', '#b28600'], falha: ['Falha', '#da1e28'], executando: ['Interrompida', '#da1e28'] }

export default function Dashboard({ data, ctx, go, onOpen }) {
  const { items, atas, meta } = data
  const k = useMemo(() => {
    const abertas = items.filter((i) => i.estagio === 'propostas_abertas')
    const atasVig = atas.filter((a) => ['vigente', 'vence_em_breve'].includes(a.vigencia_status))
    return {
      total: items.length,
      abertas: abertas.length,
      planejamento: items.filter((i) => i.estagio === 'planejamento').length,
      alta: items.filter((i) => i.classificacao?.faixa === 'alta').length,
      atasVig: atasVig.length,
      adesao: atasVig.filter((a) => a.adesao_status === 'potencial_verificar').length,
      vencendo: atasVig.filter((a) => a.vigencia_status === 'vence_em_breve').length,
      valor: aggregateValue(items),
      dfFed: items.filter((i) => i.orgao?.esfera === 'F' || i.unidade?.uf === 'DF').length,
      topAbertas: abertas.filter((i) => (i.classificacao?.score || 0) >= 60).sort(SORTS.score).slice(0, 6),
      topAtas: atasVig.filter((a) => (a.classificacao?.score || 0) >= 60).sort(SORTS.score).slice(0, 4),
      porOferta: Object.entries(items.reduce((acc, i) => {
        for (const o of i.classificacao?.ofertas?.slice(0, 1) || []) acc[o] = (acc[o] || 0) + 1
        return acc
      }, {})).sort((a, b) => b[1] - a[1]),
    }
  }, [items, atas])
  const maxOferta = Math.max(1, ...k.porOferta.map(([, n]) => n))
  const fontes = Object.entries(meta.fontes || {})
  const hist = meta.carga_historica || {}

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-4">
        <Kpi label="Oportunidades encontradas" value={k.total.toLocaleString('pt-BR')} hint={`aderência ≥ ${meta.publicado?.score_minimo ?? 35}`} onClick={() => go('oportunidades', {})} />
        <Kpi label="Propostas abertas" value={k.abertas.toLocaleString('pt-BR')} accent="#0f62fe" onClick={() => go('oportunidades', { estagio: 'propostas_abertas' })} />
        <Kpi label="Demandas em planejamento (PCA)" value={k.planejamento.toLocaleString('pt-BR')} onClick={() => go('oportunidades', { estagio: 'planejamento' })} />
        <Kpi label="Alta aderência (80+)" value={k.alta.toLocaleString('pt-BR')} accent="#198038" onClick={() => go('oportunidades', { scoreMin: '80' })} />
        <Kpi label="Atas vigentes relevantes" value={k.atasVig.toLocaleString('pt-BR')} hint={`${k.vencendo} vencem em até 90 dias`} onClick={() => go('atas', { vigencia: 'vigentes' })} />
        <Kpi label="Atas com potencial de adesão a avaliar" value={k.adesao.toLocaleString('pt-BR')} accent="#6929c4" onClick={() => go('atas', { vigencia: 'vigentes', adesao: 'potencial_verificar' })} />
        <Kpi label="Valor estimado agregado" value={moneyCompact(k.valor.total)} hint={`${k.valor.n.toLocaleString('pt-BR')} registros únicos com valor; sigilosos/ausentes excluídos`} />
        <Kpi label="Foco DF + órgãos federais" value={k.dfFed.toLocaleString('pt-BR')} onClick={() => go('oportunidades', { foco: 'df_federal' })} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="flex flex-col gap-2 lg:col-span-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[16px] font-semibold">Propostas abertas com aderência 60+</h2>
            <button className="text-[13px] text-brand hover:underline" onClick={() => go('oportunidades', { estagio: 'propostas_abertas', scoreMin: '60' })}>ver todas</button>
          </div>
          {k.topAbertas.length ? (
            <ul className="flex flex-col gap-px bg-line">{k.topAbertas.map((r) => <OppCard key={r.id} r={r} L={meta.lookups || {}} ctx={ctx} onOpen={onOpen} />)}</ul>
          ) : <p className="bg-white p-4 text-[13px] text-muted">Nenhuma proposta aberta com aderência 60+ na base atual.</p>}
        </section>
        <aside className="flex flex-col gap-6">
          <section className="bg-white p-4">
            <h2 className="mb-1 text-[14px] font-semibold">Atualização dos dados</h2>
            <p className="text-[13px]">Última coleta: <strong>{fmtDate(meta.gerado_em, true) || '—'}</strong></p>
            <p className="text-[12px]" style={{ color: (STATUS[meta.status] || STATUS.falha)[1] }}>
              Status geral: {(STATUS[meta.status] || ['Desconhecido'])[0]}{meta.fontes_com_falha?.length ? ` — ${meta.fontes_com_falha.length} fonte(s) com falha (dados anteriores mantidos)` : ''}
            </p>
            <ul className="mt-3 flex flex-col gap-1.5 text-[12px]">
              {fontes.map(([key, f]) => (
                <li key={key} className="flex items-start justify-between gap-2">
                  <span className="text-ink-2">{FONTE_LABEL[key] || key}{f.progresso != null && f.progresso < 100 ? ` · ${f.progresso}%` : ''}
                    {f.erro ? <span className="block text-[11px] text-muted">{String(f.erro).slice(0, 140)}</span> : null}</span>
                  <span className="shrink-0 font-medium" style={{ color: (STATUS[f.status] || STATUS.falha)[1] }}>{(STATUS[f.status] || [f.status])[0]}</span>
                </li>
              ))}
            </ul>
            {hist.contratacoes?.progresso != null && !hist.contratacoes?.concluido ? (
              <p className="mt-3 text-[11px] text-muted">Carga histórica de 12 meses em andamento ({hist.contratacoes.progresso}%). Os resultados crescem a cada execução.</p>
            ) : null}
          </section>
          <section className="bg-white p-4">
            <h2 className="mb-2 text-[14px] font-semibold">Oportunidades por oferta principal</h2>
            <ul className="flex flex-col gap-2">
              {k.porOferta.map(([o, n]) => (
                <li key={o}>
                  <button className="w-full text-left" onClick={() => go('oportunidades', { oferta: o })}>
                    <div className="flex justify-between text-[12px]"><span>{o}</span><span className="num text-muted">{n.toLocaleString('pt-BR')}</span></div>
                    <div className="mt-0.5 h-1.5 bg-field"><div className="h-1.5 bg-brand" style={{ width: `${(n / maxOferta) * 100}%` }} /></div>
                  </button>
                </li>
              ))}
              {!k.porOferta.length ? <li className="text-[12px] text-muted">Sem dados.</li> : null}
            </ul>
          </section>
        </aside>
      </div>

      <section className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between">
          <h2 className="text-[16px] font-semibold">Atas vigentes com aderência 60+</h2>
          <button className="text-[13px] text-brand hover:underline" onClick={() => go('atas', { vigencia: 'vigentes', scoreMin: '60' })}>ver todas</button>
        </div>
        {k.topAtas.length ? <ul className="flex flex-col gap-px bg-line">{k.topAtas.map((a) => <AtaCard key={a.id} a={a} ctx={ctx} onOpen={onOpen} />)}</ul>
          : <p className="bg-white p-4 text-[13px] text-muted">Nenhuma ata vigente com aderência 60+ na base atual.</p>}
      </section>

      <details className="bg-white p-4 text-[12px] text-ink-2">
        <summary className="cursor-pointer font-medium text-ink">Fontes, cobertura e limitações</summary>
        <ul className="mt-2 list-disc pl-5">{(meta.limitacoes || []).map((l) => <li key={l}>{l}</li>)}</ul>
      </details>
    </div>
  )
}
