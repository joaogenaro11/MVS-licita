import { useMemo, useState } from 'react'
import { Badge, Empty, inputCls, TIPO } from '../components/ui.jsx'
import { fmtDate } from '../lib/format.js'
import { configToText, parseConfigText } from '../lib/private.js'

export default function Acompanhamento({ data, ctx, onOpen }) {
  const all = useMemo(() => [...data.items, ...data.atas], [data])
  const rows = ctx.tracking.rows
  const tracked = useMemo(() => all.filter((r) => rows[r.id] && (rows[r.id].favorito || rows[r.id].status || rows[r.id].observacao))
    .sort((a, b) => (rows[a.id].proximo_acompanhamento || '9999').localeCompare(rows[b.id].proximo_acompanhamento || '9999')), [all, rows])
  const orphan = Object.keys(rows).filter((id) => !all.some((r) => r.id === id) && (rows[id].favorito || rows[id].status))

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <section className="flex flex-col gap-2 lg:col-span-2">
        <h2 className="text-[16px] font-semibold">Favoritos e acompanhamento</h2>
        {!ctx.tracking.shared ? (
          <p className="border-l-4 border-warn bg-white px-3 py-2 text-[12px]">
            Favoritos e anotações estão salvos <strong>somente neste navegador</strong> e não são compartilhados entre computadores.
            {ctx.auth.enabled ? ' Entre com seu usuário para usar o acompanhamento compartilhado da equipe.' : ' Para compartilhar entre os usuários, configure o Supabase (ver README).'}
          </p>
        ) : null}
        {ctx.tracking.error ? <p className="text-[12px] text-bad">Erro no banco compartilhado: {ctx.tracking.error}</p> : null}
        {tracked.length === 0 ? <Empty>Nenhum item favoritado ou em acompanhamento.</Empty> : (
          <ul className="flex flex-col gap-px bg-line">
            {tracked.map((r) => {
              const t = rows[r.id]
              return (
                <li key={r.id} className="flex items-start gap-3 bg-white p-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge className="bg-ink text-white ring-ink">{TIPO[r.tipo]}</Badge>
                      {t.status ? <Badge className="bg-brand-soft text-brand-dark ring-[#a6c8ff]">{t.status}</Badge> : null}
                      {t.favorito ? <Badge>★ favorito</Badge> : null}
                    </div>
                    <button className="mt-1 block text-left text-[13px] hover:text-brand" onClick={() => onOpen(r)}><span className="clamp-2">{r.objeto}</span></button>
                    <div className="text-[11px] text-muted">{r.orgao?.nome}{t.responsavel ? ` · Responsável: ${t.responsavel}` : ''}
                      {t.proximo_acompanhamento ? ` · Próximo acompanhamento: ${fmtDate(t.proximo_acompanhamento)}` : ''}</div>
                    {t.observacao ? <p className="mt-1 text-[12px] text-ink-2">{t.observacao}</p> : null}
                  </div>
                  <span className="num text-[18px] font-semibold text-ink-2">{r.classificacao?.score}</span>
                </li>
              )
            })}
          </ul>
        )}
        {orphan.length ? <p className="text-[11px] text-muted">{orphan.length} item(ns) acompanhados não estão mais na base publicada (score abaixo do mínimo ou fora do período): {orphan.slice(0, 5).join(', ')}</p> : null}
      </section>
      <aside className="flex flex-col gap-6">
        <Login ctx={ctx} />
        <ConfigEditor ctx={ctx} />
      </aside>
    </div>
  )
}

function Login({ ctx }) {
  const { auth } = ctx
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  if (!auth.enabled) {
    return (
      <section className="bg-white p-4 text-[12px] text-ink-2">
        <h2 className="mb-1 text-[14px] font-semibold text-ink">Acesso da equipe</h2>
        Banco compartilhado não configurado. Os dados públicos de licitações não exigem login; dados comerciais internos
        (status, responsável, observações, órgãos prioritários) exigem o Supabase com autenticação real — instruções no README.
      </section>
    )
  }
  if (auth.user) {
    return (
      <section className="bg-white p-4 text-[13px]">
        <h2 className="mb-1 text-[14px] font-semibold">Acesso da equipe</h2>
        Conectado como <strong>{auth.user.email}</strong>.
        <button onClick={auth.signOut} className="ml-2 text-brand hover:underline">Sair</button>
      </section>
    )
  }
  return (
    <form className="flex flex-col gap-2 bg-white p-4" onSubmit={async (e) => {
      e.preventDefault(); setErr('')
      try { await auth.signIn(email, pw) } catch (x) { setErr(x.message || 'Falha no login') }
    }}>
      <h2 className="text-[14px] font-semibold">Entrar (equipe)</h2>
      <input className={inputCls} type="email" autoComplete="username" placeholder="e-mail" value={email} onChange={(e) => setEmail(e.target.value)} required />
      <input className={inputCls} type="password" autoComplete="current-password" placeholder="senha" value={pw} onChange={(e) => setPw(e.target.value)} required />
      <button className="bg-brand py-2 text-[13px] text-white hover:bg-brand-dark">Entrar</button>
      {err ? <p className="text-[12px] text-bad">{err}</p> : null}
      <p className="text-[11px] text-muted">Autenticação Supabase. Usuários são criados pelo administrador (cadastro público desativado).</p>
    </form>
  )
}

function ConfigEditor({ ctx }) {
  const { config, save, shared } = ctx.commercial
  const [text, setText] = useState(() => configToText(config))
  const [msg, setMsg] = useState('')
  const [open, setOpen] = useState(false)
  if (ctx.auth.enabled && !ctx.auth.user) return null
  return (
    <section className="bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-semibold">Configuração comercial privada</h2>
        <button className="text-[12px] text-brand hover:underline" onClick={() => { setText(configToText(config)); setOpen(!open) }}>{open ? 'fechar' : 'editar'}</button>
      </div>
      <p className="mt-1 text-[11px] text-muted">
        Órgãos prioritários ({config.priority_orgs.length}), parceiros de referência ({config.partners.length}) e notas por fabricante
        ({Object.keys(config.vendor_notes || {}).length}). {shared ? 'Salva no banco protegido (somente usuários autenticados).' : 'Salva somente neste navegador.'} Nunca é publicada no site.
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
