import { useMemo, useState } from 'react'
import { Badge, Empty, FAIXA, inputCls, TIPO } from '../components/ui.jsx'
import { fmtDate } from '../lib/format.js'
import { configToText, parseConfigText } from '../lib/private.js'

export default function Acompanhamento({ data, ctx, onOpen }) {
  const all = useMemo(() => [...data.items, ...data.atas], [data])
  const rows = ctx.tracking.rows
  const isFav = ctx.isFav
  const tracked = useMemo(() => all.filter((r) => isFav(r.id) || (rows[r.id] && (rows[r.id].status || rows[r.id].observacao)))
    .sort((a, b) => (rows[a.id]?.proximo_acompanhamento || '9999').localeCompare(rows[b.id]?.proximo_acompanhamento || '9999')), [all, rows, isFav])
  const known = useMemo(() => new Set(all.map((r) => r.id)), [all])
  const orphan = [...new Set([...ctx.favoritos.ids, ...Object.keys(rows).filter((id) => rows[id].status)])].filter((id) => !known.has(id))

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <section className="flex flex-col gap-2 lg:col-span-2">
        <h2 className="text-[16px] font-semibold">Meus favoritos e acompanhamento da equipe</h2>
        {!ctx.tracking.shared ? (
          <p className="border-l-4 border-warn bg-white px-3 py-2 text-[12px]">
            Favoritos e anotações estão salvos <strong>somente neste navegador</strong> (Supabase não configurado — ver README).
          </p>
        ) : <p className="text-[12px] text-ink-2">Favoritos são <strong>seus</strong> (cada pessoa tem os próprios). Status, responsável e observações são da <strong>equipe</strong>.</p>}
        {ctx.tracking.error || ctx.favoritos.error ? <p className="text-[12px] text-bad">Erro no banco: {ctx.tracking.error || ctx.favoritos.error}</p> : null}
        {tracked.length === 0 ? <Empty>Nenhum item favoritado ou em acompanhamento.</Empty> : (
          <ul className="flex flex-col gap-px bg-line">
            {tracked.map((r) => {
              const t = rows[r.id] || {}
              return (
                <li key={r.id} className="flex items-start gap-3 bg-white p-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge className="bg-ink text-white ring-ink">{TIPO[r.tipo]}</Badge>
                      {t.status ? <Badge className="bg-brand-soft text-brand-dark ring-[#a6c8ff]">{t.status}</Badge> : null}
                      {isFav(r.id) ? <Badge>★ meu favorito</Badge> : null}
                    </div>
                    <button className="mt-1 block text-left text-[13px] hover:text-brand" onClick={() => onOpen(r)}><span className="clamp-2">{r.objeto}</span></button>
                    <div className="text-[11px] text-muted">{r.orgao?.nome}{t.responsavel ? ` · Responsável: ${t.responsavel}` : ''}
                      {t.proximo_acompanhamento ? ` · Próximo acompanhamento: ${fmtDate(t.proximo_acompanhamento)}` : ''}</div>
                    {t.observacao ? <p className="mt-1 text-[12px] text-ink-2">{t.observacao}</p> : null}
                  </div>
                  {r.classificacao?.score != null ? (
                    <span className="num text-[18px] font-semibold" style={{ color: (FAIXA[r.classificacao.faixa] || FAIXA.baixa).bar }}
                      title={`Aderência TLS ${r.classificacao.score}/100 — ${(FAIXA[r.classificacao.faixa] || FAIXA.baixa).label}`}>{r.classificacao.score}</span>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
        {orphan.length ? <p className="text-[11px] text-muted">{orphan.length} item(ns) acompanhados não estão mais na base publicada (vencidos ou fora da base publicada): {orphan.slice(0, 5).join(', ')}</p> : null}
      </section>
      <aside className="flex flex-col gap-6">
        <ConfigEditor ctx={ctx} />
      </aside>
    </div>
  )
}

function ConfigEditor({ ctx }) {
  const { config, save, shared } = ctx.commercial
  const [text, setText] = useState(() => configToText(config))
  const [msg, setMsg] = useState('')
  const [open, setOpen] = useState(false)
  return (
    <section className="bg-white p-4">
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
