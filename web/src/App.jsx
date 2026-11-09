import { useCallback, useEffect, useMemo, useState } from 'react'
import Detail from './components/Detail.jsx'
import { loadAll } from './lib/data.js'
import { indexRecord } from './lib/filters.js'
import { fmtDate } from './lib/format.js'
import { useAuth, useCommercialConfig, useFavoritos, useMigracaoLocal, usePreferencias, useTracking } from './lib/private.js'
import { Login, SemAcesso, TrocarSenha } from './pages/Acesso.jsx'
import Acompanhamento from './pages/Acompanhamento.jsx'
import Atas, { EMPTY_ATA_FILTERS } from './pages/Atas.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Oportunidades, { EMPTY_FILTERS } from './pages/Oportunidades.jsx'
import Usuarios from './pages/Usuarios.jsx'

const NAV = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'oportunidades', label: 'Oportunidades' },
  { key: 'atas', label: 'Radar de Atas' },
  { key: 'acompanhamento', label: 'Acompanhamento' },
  { key: 'analise', label: 'Análise de Compras', soon: true },
  { key: 'usuarios', label: 'Usuários', admin: true },
]
const TITLES = {
  dashboard: 'Radar de Demanda Pública', oportunidades: 'Oportunidades', atas: 'Radar de Atas',
  acompanhamento: 'Acompanhamento', usuarios: 'Administração', senha: 'Trocar senha',
}

function useHashRoute(isAdmin) {
  const get = () => (window.location.hash.replace(/^#\/?/, '').split('?')[0] || 'dashboard')
  const [route, setRoute] = useState(get)
  useEffect(() => {
    const on = () => setRoute(get())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const nav = useCallback((r) => { window.location.hash = `/${r}`; window.scrollTo(0, 0) }, [])
  const ok = route === 'senha' || NAV.some((n) => n.key === route && !n.soon && (!n.admin || isAdmin))
  return [ok ? route : 'dashboard', nav]
}

/** Portão de acesso: com Supabase configurado, nada (nem os dados) carrega sem login. */
export default function App() {
  const auth = useAuth()
  if (auth.enabled) {
    if (!auth.ready) return <div className="p-6 text-[14px] text-muted">Carregando…</div>
    if (!auth.session) return <Login auth={auth} />
    if (!auth.perfil) return <div className="p-6 text-[14px] text-muted">Verificando acesso…</div>
    if (!auth.perfil.ativo) return <SemAcesso auth={auth} />
    if (auth.perfil.trocar_senha) return <TrocarSenha auth={auth} obrigatoria />
  }
  return <Radar auth={auth} />
}

function Radar({ auth }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [route, nav] = useHashRoute(auth.isAdmin)
  const [filters, setFiltersState] = useState(EMPTY_FILTERS)
  const [ataFilters, setAtaFiltersState] = useState(EMPTY_ATA_FILTERS)
  const [sort, setSortState] = useState('score')
  const [open, setOpen] = useState(null)
  const [menu, setMenu] = useState(false)

  const favoritos = useFavoritos(auth)
  const prefs = usePreferencias(auth)
  const tracking = useTracking(auth)
  const commercial = useCommercialConfig(auth)
  useMigracaoLocal(auth, favoritos, prefs, tracking)

  useEffect(() => {
    loadAll().then((d) => {
      d.items.forEach(indexRecord)
      d.atas.forEach(indexRecord)
      setData(d)
    }).catch((e) => setError(e.message))
  }, [])

  // Preferências pessoais: filtros, ordenação e portfólio voltam como cada usuário deixou.
  useEffect(() => {
    if (!prefs.loaded) return
    const p = prefs.prefs
    // só filtros que ainda existem (ex.: o antigo "Aderência Alta/Média/Baixa" virou "Aderência mínima")
    const conhecidos = (base, salvo) => Object.fromEntries(Object.entries(salvo || {}).filter(([k]) => k in base))
    setFiltersState({ ...EMPTY_FILTERS, ...conhecidos(EMPTY_FILTERS, p.filtros_oportunidades), ...(p.portfolio ? { portfolio: p.portfolio } : {}) })
    setAtaFiltersState({ ...EMPTY_ATA_FILTERS, ...conhecidos(EMPTY_ATA_FILTERS, p.filtros_atas), ...(p.portfolio ? { portfolio: p.portfolio } : {}) })
    if (p.ordenacao) setSortState(p.ordenacao)
  }, [prefs.loaded]) // eslint-disable-line react-hooks/exhaustive-deps

  const setFilters = useCallback((f) => {
    setFiltersState(f)
    setAtaFiltersState((a) => ({ ...a, portfolio: f.portfolio }))
    prefs.update({ filtros_oportunidades: f, portfolio: f.portfolio })
  }, [prefs])
  const setAtaFilters = useCallback((f) => {
    setAtaFiltersState(f)
    setFiltersState((o) => ({ ...o, portfolio: f.portfolio }))
    prefs.update({ filtros_atas: f, portfolio: f.portfolio })
  }, [prefs])
  const setSort = useCallback((s) => { setSortState(s); prefs.update({ ordenacao: s }) }, [prefs])

  const familias = useMemo(() => Object.fromEntries((data?.meta?.lookups?.familias || []).map((f) => [f.id, f])), [data])
  const ctx = useMemo(() => ({
    isFav: favoritos.isFav, toggleFav: favoritos.toggle, favoritos, tracking, auth, commercial, prefs, familias,
    config: commercial.config, priorityOrgs: commercial.config.priority_orgs,
  }), [favoritos, tracking, auth, commercial, prefs, familias])

  const go = useCallback((r, f) => {
    // atalhos do Dashboard mantêm as escolhas pessoais de portfólio e de valor mínimo
    const pessoal = (x) => ({ portfolio: x.portfolio, vmin: x.vmin, ocultarSemValor: x.ocultarSemValor })
    if (r === 'oportunidades') setFilters({ ...EMPTY_FILTERS, ...pessoal(filters), ...f })
    if (r === 'atas') setAtaFilters({ ...EMPTY_ATA_FILTERS, ...pessoal(ataFilters), vigencia: '', ...f })
    nav(r)
  }, [nav, setFilters, setAtaFilters, filters, ataFilters])

  const navItems = NAV.filter((n) => !n.admin || auth.isAdmin)

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 bg-ink text-white">
        <div className="mx-auto flex h-12 max-w-7xl items-center gap-4 px-4">
          <a href="#/dashboard" className="flex items-center gap-2 whitespace-nowrap">
            <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="10" fill="none" stroke="#4589ff" strokeWidth="2" /><circle cx="16" cy="16" r="5" fill="none" stroke="#4589ff" strokeWidth="2" /><path d="M16 16 L25 9" stroke="#78a9ff" strokeWidth="2.5" strokeLinecap="round" /><circle cx="16" cy="16" r="1.8" fill="#fff" /></svg>
            <span className="text-[14px] tracking-wide"><span className="font-semibold">RADAR</span> TLS</span>
          </a>
          <nav className="hidden h-full items-stretch lg:flex" aria-label="Navegação principal">
            {navItems.map((n) => <NavItem key={n.key} n={n} active={route === n.key} onClick={() => nav(n.key)} />)}
          </nav>
          <div className="ml-auto hidden items-center gap-4 whitespace-nowrap text-[11px] text-[#c6c6c6] 2xl:flex">
            {data ? <span>Dados de {fmtDate(data.meta.gerado_em, true)}</span> : null}
          </div>
          {auth.enabled && auth.perfil ? (
            <div className="ml-auto hidden items-center gap-3 whitespace-nowrap text-[12px] lg:flex 2xl:ml-0" aria-label="Usuário conectado">
              <span className="text-white">{auth.perfil.nome}</span>
              <button className="text-[#c6c6c6] hover:text-white" onClick={() => nav('senha')}>Trocar senha</button>
              <button className="text-[#c6c6c6] hover:text-white" onClick={auth.signOut}>Sair</button>
            </div>
          ) : null}
          <button className="ml-auto p-2 lg:hidden" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>
            <svg width="20" height="20" viewBox="0 0 20 20"><path d="M2 5h16M2 10h16M2 15h16" stroke="#fff" strokeWidth="1.5" /></svg>
          </button>
        </div>
        {menu ? (
          <nav className="flex flex-col border-t border-[#393939] lg:hidden">
            {navItems.map((n) => <NavItem key={n.key} n={n} mobile active={route === n.key} onClick={() => { setMenu(false); nav(n.key) }} />)}
            {auth.enabled && auth.perfil ? (
              <div className="flex items-center gap-4 border-t border-[#393939] px-4 py-3 text-[13px]">
                <span>{auth.perfil.nome}</span>
                <button className="text-[#c6c6c6]" onClick={() => { setMenu(false); nav('senha') }}>Trocar senha</button>
                <button className="text-[#c6c6c6]" onClick={auth.signOut}>Sair</button>
              </div>
            ) : null}
          </nav>
        ) : null}
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {error ? (
          <div className="bg-white p-6 text-[14px]">
            <p className="font-semibold text-bad">Não foi possível carregar os dados.</p>
            <p className="mt-1 text-ink-2">{error}. Se o site acabou de ser implantado, aguarde a primeira execução do workflow "Atualizar Radar TLS".</p>
          </div>
        ) : !data ? (
          <div className="p-6 text-[14px] text-muted">Carregando dados…</div>
        ) : (
          <>
            <h1 className="mb-4 text-[24px] font-light">{TITLES[route]}</h1>
            {route === 'dashboard' && <Dashboard data={data} ctx={ctx} go={go} onOpen={setOpen}
              filtroValor={{ vmin: filters.vmin, ocultarSemValor: filters.ocultarSemValor }} />}
            {route === 'oportunidades' && <Oportunidades data={data} filters={filters} setFilters={setFilters} sort={sort} setSort={setSort} ctx={ctx} onOpen={setOpen} />}
            {route === 'atas' && <Atas data={data} filters={ataFilters} setFilters={setAtaFilters} ctx={ctx} onOpen={setOpen} />}
            {route === 'acompanhamento' && <Acompanhamento data={data} ctx={ctx} onOpen={setOpen} />}
            {route === 'usuarios' && auth.isAdmin && <Usuarios ctx={ctx} />}
            {route === 'senha' && <div className="max-w-sm bg-white p-4"><TrocarSenha auth={auth} /></div>}
          </>
        )}
      </main>
      <footer className="mx-auto max-w-7xl px-4 pb-8 text-[11px] text-muted">
        Radar TLS · dados públicos do Portal Nacional de Contratações Públicas (PNCP). Ferramenta interna de inteligência comercial; não é um serviço oficial.
      </footer>
      {open && data ? <Detail r={open} meta={data.meta} ctx={ctx} onClose={() => setOpen(null)} /> : null}
    </div>
  )
}

function NavItem({ n, active, onClick, mobile }) {
  if (n.soon) {
    return (
      <span aria-disabled="true" title="Em breve: análise do planejamento de compras de um órgão (PCA, PDTI/PDTIC, PETI, ETP)"
        className={`flex cursor-default items-center gap-2 whitespace-nowrap px-3 text-[13px] text-[#8d8d8d] ${mobile ? 'py-3' : ''}`}>
        {n.label}<span className="rounded-sm bg-[#393939] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[#c6c6c6]">Em breve</span>
      </span>
    )
  }
  return (
    <button onClick={onClick} aria-current={active ? 'page' : undefined}
      className={`flex items-center whitespace-nowrap px-3 text-[13px] ${mobile ? 'py-3 text-left' : 'border-b-2'} ${active ? 'border-brand bg-[#262626] text-white' : 'border-transparent text-[#c6c6c6] hover:bg-[#262626] hover:text-white'}`}>
      {n.label}
    </button>
  )
}
