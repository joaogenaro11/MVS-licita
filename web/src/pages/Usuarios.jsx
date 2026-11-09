import { useCallback, useEffect, useState } from 'react'
import { Badge, Field, inputCls, Select } from '../components/ui.jsx'
import { fmtDate } from '../lib/format.js'
import { adminApi } from '../lib/private.js'

/** Administração (só papel admin; o banco recusa as chamadas de quem não é admin). */
export default function Usuarios({ ctx }) {
  const [rows, setRows] = useState([])
  const [err, setErr] = useState('')
  const [senha, setSenha] = useState(null) // { usuario, senha } mostrada UMA vez
  const [novo, setNovo] = useState({ usuario: '', nome: '', papel: 'usuario' })
  const me = ctx.auth.perfil?.user_id

  const load = useCallback(async () => {
    try { setRows(await adminApi.listar()); setErr('') } catch (e) { setErr(e.message) }
  }, [])
  useEffect(() => { load() }, [load])

  const run = async (fn) => { setErr(''); try { await fn(); await load() } catch (e) { setErr(e.message) } }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <section className="flex flex-col gap-2 lg:col-span-2">
        <h2 className="text-[16px] font-semibold">Usuários</h2>
        {err ? <p role="alert" className="bg-white px-3 py-2 text-[13px] text-bad">{err}</p> : null}
        {senha ? (
          <div role="status" className="border-l-4 border-warn bg-white px-4 py-3 text-[13px]">
            Senha temporária de <strong>{senha.usuario}</strong>: <code className="select-all bg-field px-2 py-0.5 font-mono text-[14px]">{senha.senha}</code>
            <p className="mt-1 text-[12px] text-ink-2">Ela aparece só agora. Repasse por um canal privado; no primeiro acesso a pessoa cria a própria senha.</p>
            <button className="mt-1 text-[12px] text-brand hover:underline" onClick={() => setSenha(null)}>Já anotei, ocultar</button>
          </div>
        ) : null}
        <div className="overflow-x-auto bg-white">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11px] text-muted"><tr>
              <th className="px-3 py-2">Usuário</th><th className="px-3">Nome</th><th className="px-3">Papel</th><th className="px-3">Situação</th>
              <th className="px-3">Último acesso</th><th className="px-3 text-right">Ações</th></tr></thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.user_id} className="border-t border-line">
                  <td className="px-3 py-2 font-mono">{u.usuario}</td>
                  <td className="px-3">{u.nome}</td>
                  <td className="px-3">{u.papel === 'admin' ? <Badge className="bg-ink text-white ring-ink">admin</Badge> : 'usuário'}</td>
                  <td className="px-3">{u.ativo ? (u.trocar_senha ? <Badge className="bg-[#fcf4d6] text-[#8e6a00] ring-[#f1c21b]">senha temporária</Badge> : <Badge className="bg-[#defbe6] text-[#0e6027] ring-[#a7f0ba]">ativo</Badge>) : <Badge className="bg-[#fff1f1] text-[#a2191f] ring-[#ffb3b8]">desativado</Badge>}</td>
                  <td className="px-3 text-[12px] text-ink-2">{fmtDate(u.ultimo_acesso, true) || 'nunca'}</td>
                  <td className="whitespace-nowrap px-3 text-right text-[12px]">
                    <button className="text-brand hover:underline" onClick={() => run(async () => {
                      if (!window.confirm(`Gerar nova senha temporária para ${u.usuario}? As sessões abertas dele serão encerradas.`)) return
                      setSenha({ usuario: u.usuario, senha: await adminApi.redefinir(u.user_id) })
                    })}>Redefinir senha</button>
                    {u.user_id !== me ? (
                      <button className="ml-3 text-brand hover:underline" onClick={() => run(() => adminApi.ativo(u.user_id, !u.ativo))}>
                        {u.ativo ? 'Desativar' : 'Reativar'}</button>
                    ) : null}
                  </td>
                </tr>
              ))}
              {!rows.length && !err ? <tr><td colSpan={6} className="px-3 py-4 text-muted">Carregando…</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>
      <aside className="flex flex-col gap-6">
        <form className="flex flex-col gap-3 bg-white p-4" onSubmit={(e) => {
          e.preventDefault()
          run(async () => {
            const r = await adminApi.criar(novo.usuario, novo.nome, novo.papel)
            setSenha({ usuario: r.usuario, senha: r.senha_temporaria })
            setNovo({ usuario: '', nome: '', papel: 'usuario' })
          })
        }}>
          <h2 className="text-[14px] font-semibold">Novo usuário</h2>
          <Field label="Usuário (login: minúsculas, sem espaço)"><input className={inputCls} value={novo.usuario} required pattern="[a-z0-9][a-z0-9._\-]{1,31}"
            onChange={(e) => setNovo({ ...novo, usuario: e.target.value.toLowerCase().replace(/\s/g, '') })} /></Field>
          <Field label="Nome"><input className={inputCls} value={novo.nome} required onChange={(e) => setNovo({ ...novo, nome: e.target.value })} /></Field>
          <Field label="Papel"><Select value={novo.papel} onChange={(v) => setNovo({ ...novo, papel: v || 'usuario' })} placeholder="usuário"
            options={[{ value: 'admin', label: 'administrador' }]} /></Field>
          <button className="bg-ink py-2 text-[13px] text-white hover:bg-ink-2">Criar e gerar senha temporária</button>
        </form>
        <BaseOfertas />
      </aside>
    </div>
  )
}

function BaseOfertas() {
  const [atual, setAtual] = useState(null)
  const [msg, setMsg] = useState('')
  const load = useCallback(() => adminApi.ofertasAtuais().then(setAtual).catch((e) => setMsg(e.message)), [])
  useEffect(() => { load() }, [load])
  return (
    <section className="flex flex-col gap-2 bg-white p-4 text-[13px]">
      <h2 className="text-[14px] font-semibold">Base de ofertas TLS</h2>
      <p className="text-[12px] text-ink-2">
        {atual ? <>Versão <strong>{atual.versao || '—'}</strong>, enviada por {atual.atualizado_por || '—'} em {fmtDate(atual.atualizado_em, true)}.</>
          : 'Nenhuma base enviada ainda: a coleta não classifica sem ela.'}
      </p>
      <label className="text-[12px] text-ink-2">Enviar nova versão (<code>ofertas_tls_radar.json</code>)
        <input type="file" accept="application/json,.json" className="mt-1 block w-full text-[12px]" onChange={async (e) => {
          const f = e.target.files?.[0]
          if (!f) return
          setMsg('Validando…')
          try {
            const json = JSON.parse(await f.text())
            setMsg(`Base salva: ${await adminApi.salvarOfertas(json)}. Vale a partir da próxima coleta (ou de uma "Nova busca").`)
            load()
          } catch (x) { setMsg(`Erro: ${x.message}`) }
          e.target.value = ''
        }} />
      </label>
      {msg ? <p role="status" className="text-[12px]">{msg}</p> : null}
      <p className="text-[11px] text-muted">A base é privada: fica no banco protegido e nunca é publicada no site nem no GitHub.</p>
    </section>
  )
}
