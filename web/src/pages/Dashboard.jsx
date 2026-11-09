import { useMemo } from 'react'
import { Kpi } from '../components/ui.jsx'
import { fmtDate, moneyCompact } from '../lib/format.js'
import { aggregateValue, passaValor, SORTS } from '../lib/filters.js'
import { OppCard } from './Oportunidades.jsx'
import { AtaCard } from './Atas.jsx'

const STATUS = { ok: ['OK', '#198038'], parcial: ['Parcial', '#b28600'], falha: ['Falha', '#da1e28'], executando: ['Interrompida', '#da1e28'] }

const REPO = import.meta.env.VITE_GITHUB_REPO

/** Abre o workflow no GitHub para disparar uma busca manual (exige login no GitHub com acesso
 *  ao repositório). O site não guarda token: disparar direto daqui exporia credenciais. */
export function NovaBusca({ className = '' }) {
  if (!REPO) return null
  return (
    <div className={className}>
      <a href={`https://github.com/${REPO}/actions/workflows/update-radar.yml`} target="_blank" rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 bg-ink px-3 py-1.5 text-[13px] font-medium text-white hover:bg-ink-2">
        Nova busca ↗
      </a>
      <p className="mt-1 text-[11px] text-muted">
        Buscas automáticas: 06:23 e 17:41 (Brasília). Para buscar agora: abre o GitHub, clique em <strong>Run workflow</strong> →
        <strong> Run workflow</strong>. Leva cerca de 40 minutos; ao final, recarregue a página.
      </p>
    </div>
  )
}

export default function Dashboard({ data, ctx, go, onOpen, filtroValor = {} }) {
  const { items, atas, meta } = data
  const k = useMemo(() => {
    const abertas = items.filter((i) => i.estagio === 'propostas_abertas')
    const atasVig = atas.filter((a) => ['vigente', 'vence_em_breve'].includes(a.vigencia_status))
    return {
      total: items.length,
      abertas: abertas.length,
      planejamento: items.filter((i) => i.estagio === 'planejamento').length,
      alta: items.filter((i) => (i.classificacao?.score ?? 0) >= 80).length,
      atasVig: atasVig.length,
      adesao: atasVig.filter((a) => a.adesao_status === 'potencial_verificar').length,
      vencendo: atasVig.filter((a) => a.vigencia_status === 'vence_em_breve').length,
      valor: aggregateValue(items),
      dfFed: items.filter((i) => i.orgao?.esfera === 'F' || i.unidade?.uf === 'DF').length,
      topAbertas: abertas.filter((i) => (i.classificacao?.score ?? 0) >= 60).sort(SORTS.score).slice(0, 6),
      topAtas: atasVig.filter((a) => (a.classificacao?.score ?? 0) >= 60).sort(SORTS.score).slice(0, 4),
      porFamilia: (meta.lookups?.familias || []).map((f) => {
        const rs = items.filter((i) => (i.classificacao?.familias || []).includes(f.id) && passaValor(i, filtroValor))
        const top = Object.entries(rs.reduce((acc, i) => {
          for (const o of i.classificacao?.ofertas_casadas || []) if (o.familia === f.id) acc[o.nome_pt] = (acc[o.nome_pt] || 0) + 1
          return acc
        }, {})).sort((a, b) => b[1] - a[1]).slice(0, 3)
        const soFamilia = rs.filter((i) => i.classificacao?.via === 'familia').length
        return { ...f, n: rs.length, valor: aggregateValue(rs).total, top, soFamilia }
      }),
    }
  }, [items, atas, meta, filtroValor])
  const maxFamilia = Math.max(1, ...k.porFamilia.map((f) => f.n))

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-4">
        <Kpi label="Oportunidades encontradas" value={k.total.toLocaleString('pt-BR')} hint="casaram oferta ou família TLS" onClick={() => go('oportunidades', {})} />
        <Kpi label="Propostas abertas" value={k.abertas.toLocaleString('pt-BR')} accent="#0f62fe" onClick={() => go('oportunidades', { estagio: 'propostas_abertas' })} />
        <Kpi label="Demandas em planejamento (PCA)" value={k.planejamento.toLocaleString('pt-BR')} onClick={() => go('oportunidades', { estagio: 'planejamento' })} />
        <Kpi label="Alta aderência (80+)" value={k.alta.toLocaleString('pt-BR')} accent="#198038" onClick={() => go('oportunidades', { scoreMin: '80' })} />
        <Kpi label="Atas vigentes relevantes" value={k.atasVig.toLocaleString('pt-BR')} hint={`${k.vencendo} vencem em até 90 dias`} onClick={() => go('atas', { vigencia: 'vigentes' })} />
        <Kpi label="Atas com potencial de adesão a avaliar" value={k.adesao.toLocaleString('pt-BR')} accent="#6929c4" onClick={() => go('atas', { vigencia: 'vigentes', adesao: 'potencial_verificar' })} />
        <Kpi label="Valor estimado agregado" value={moneyCompact(k.valor.total)} hint={`contratações + PCA, sem duplicidade (${k.valor.n.toLocaleString('pt-BR')} registros com valor)`} />
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
          <section className="bg-white p-4" aria-label="Atualização dos dados">
            <h2 className="mb-1 text-[14px] font-semibold">Atualização dos dados</h2>
            <p className="text-[13px]">Última coleta: <strong>{fmtDate(meta.gerado_em, true) || '—'}</strong></p>
            <p className="text-[13px]">Status geral: <strong style={{ color: (STATUS[meta.status] || STATUS.falha)[1] }}>{(STATUS[meta.status] || ['Desconhecido'])[0]}</strong></p>
          </section>
          <NovaBusca className="bg-white p-4" />
          <section className="bg-white p-4" aria-label="Oportunidades por família">
            <h2 className="mb-2 text-[14px] font-semibold">Oportunidades por família</h2>
            <ul className="flex flex-col gap-2">
              {k.porFamilia.map((f) => (
                <li key={f.id}>
                  <button className="w-full text-left disabled:cursor-default" disabled={!f.n} onClick={() => go('oportunidades', { familia: f.id })}
                    title={f.top.length ? `Ofertas mais frequentes: ${f.top.map(([o, n]) => `${o} (${n})`).join(' · ')}${f.soFamilia ? ` · ${f.soFamilia} só pela família` : ''}`
                      : f.soFamilia ? `${f.soFamilia} pela família, sem oferta específica` : 'Sem oportunidades'}>
                    <div className="flex justify-between gap-2 text-[12px]">
                      <span className={f.n ? '' : 'text-muted'}>{f.nome}</span>
                      <span className="num shrink-0 text-muted">{f.n.toLocaleString('pt-BR')}{f.valor ? ` · ${moneyCompact(f.valor)}` : ''}</span>
                    </div>
                    <div className="mt-0.5 h-1.5 bg-field"><div className="h-1.5 bg-brand" style={{ width: `${(f.n / maxFamilia) * 100}%` }} /></div>
                  </button>
                </li>
              ))}
              {!k.porFamilia.length ? <li className="text-[12px] text-muted">Sem dados.</li> : null}
            </ul>
            <p className="mt-2 text-[11px] text-muted">
              Uma oportunidade pode estar em duas famílias. Passe o mouse para ver as ofertas mais frequentes.
              {Number(filtroValor.vmin) > 0 ? ` Com seu valor mínimo de ${moneyCompact(Number(filtroValor.vmin))}.` : ''}
              {filtroValor.ocultarSemValor ? ' Sem os registros sem valor.' : ''}
            </p>
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
