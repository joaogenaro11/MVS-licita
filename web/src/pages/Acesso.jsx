import { useState } from 'react'
import { inputCls } from '../components/ui.jsx'
import { loginLockState } from '../lib/private.js'

function Shell({ children, title }) {
  return (
    <div className="flex min-h-screen items-start justify-center bg-[#f4f4f4] px-4 pt-16 sm:pt-24">
      <div className="w-full max-w-sm bg-white p-6 shadow-sm">
        <div className="mb-5 flex items-center gap-2">
          <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="10" fill="none" stroke="#0f62fe" strokeWidth="2" /><circle cx="16" cy="16" r="5" fill="none" stroke="#0f62fe" strokeWidth="2" /><path d="M16 16 L25 9" stroke="#4589ff" strokeWidth="2.5" strokeLinecap="round" /><circle cx="16" cy="16" r="1.8" fill="#161616" /></svg>
          <span className="text-[16px] tracking-wide"><span className="font-semibold">RADAR</span> TLS</span>
        </div>
        <h1 className="mb-4 text-[20px] font-light">{title}</h1>
        {children}
      </div>
    </div>
  )
}

export function Login({ auth }) {
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <Shell title="Entrar">
      <form className="flex flex-col gap-3" onSubmit={async (e) => {
        e.preventDefault(); setErr(''); setBusy(true)
        try { await auth.signIn(usuario, senha) } catch (x) { setErr(x.message || 'Falha no login') } finally { setBusy(false) }
      }}>
        <label className="flex flex-col gap-1 text-[12px] text-ink-2">Usuário
          <input className={`${inputCls} h-10 text-[14px]`} autoComplete="username" autoCapitalize="none" spellCheck="false"
            value={usuario} onChange={(e) => setUsuario(e.target.value)} required name="usuario" />
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-ink-2">Senha
          <input className={`${inputCls} h-10 text-[14px]`} type="password" autoComplete="current-password"
            value={senha} onChange={(e) => setSenha(e.target.value)} required name="senha" />
        </label>
        <button disabled={busy || loginLockState().bloqueado} className="mt-1 bg-brand py-2.5 text-[14px] text-white hover:bg-brand-dark disabled:opacity-60">
          {busy ? 'Entrando…' : 'Entrar'}
        </button>
        {err ? <p role="alert" className="text-[13px] text-bad">{err}</p> : null}
        <p className="text-[11px] text-muted">Acesso individual da equipe. Não tem usuário ou esqueceu a senha? Fale com o administrador.</p>
      </form>
    </Shell>
  )
}

export function TrocarSenha({ auth, obrigatoria = false, onDone }) {
  const [atual, setAtual] = useState('')
  const [nova, setNova] = useState('')
  const [conf, setConf] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const form = (
    <form className="flex flex-col gap-3" onSubmit={async (e) => {
      e.preventDefault(); setMsg('')
      if (nova !== conf) { setMsg('A confirmação não confere com a nova senha.'); return }
      setBusy(true)
      try { await auth.trocarSenha(atual, nova); setMsg('Senha alterada.'); onDone?.() } catch (x) { setMsg(x.message) } finally { setBusy(false) }
    }}>
      {obrigatoria ? <p className="text-[13px] text-ink-2">Olá, {auth.perfil?.nome}. No primeiro acesso (ou depois de uma redefinição) é preciso criar uma senha pessoal.</p> : null}
      <label className="flex flex-col gap-1 text-[12px] text-ink-2">Senha atual{obrigatoria ? ' (temporária)' : ''}
        <input className={inputCls} type="password" autoComplete="current-password" value={atual} onChange={(e) => setAtual(e.target.value)} required name="senha-atual" /></label>
      <label className="flex flex-col gap-1 text-[12px] text-ink-2">Nova senha
        <input className={inputCls} type="password" autoComplete="new-password" minLength={10} value={nova} onChange={(e) => setNova(e.target.value)} required name="senha-nova" /></label>
      <label className="flex flex-col gap-1 text-[12px] text-ink-2">Confirme a nova senha
        <input className={inputCls} type="password" autoComplete="new-password" minLength={10} value={conf} onChange={(e) => setConf(e.target.value)} required name="senha-confirma" /></label>
      <p className="text-[11px] text-muted">Mínimo de 10 caracteres, com letras e números.</p>
      <div className="flex items-center gap-3">
        <button disabled={busy} className="bg-brand px-4 py-2 text-[13px] text-white hover:bg-brand-dark disabled:opacity-60">Salvar nova senha</button>
        {obrigatoria ? <button type="button" onClick={auth.signOut} className="text-[13px] text-brand hover:underline">Sair</button> : null}
      </div>
      {msg ? <p role="status" className="text-[13px] text-ink-2">{msg}</p> : null}
    </form>
  )
  return obrigatoria ? <Shell title="Criar senha pessoal">{form}</Shell> : form
}

export function SemAcesso({ auth }) {
  return (
    <Shell title="Acesso não autorizado">
      <p className="text-[13px] text-ink-2">
        {auth.perfil?.erro ? `Não foi possível verificar seu acesso: ${auth.perfil.erro}` : 'Seu usuário não está ativo no Radar TLS. Fale com o administrador.'}
      </p>
      <button onClick={auth.signOut} className="mt-4 bg-ink px-4 py-2 text-[13px] text-white">Sair</button>
    </Shell>
  )
}
