import { useCallback, useEffect, useMemo, useState } from 'react'
import Detail from './components/Detail.jsx'
import { loadAll } from './lib/data.js'
import { indexRecord } from './lib/filters.js'
import { fmtDate } from './lib/format.js'
import { useAuth, useCommercialConfig, useTracking } from './lib/private.js'
import Acompanhamento from './pages/Acompanhamento.jsx'
import Atas, { EMPTY_ATA_FILTERS } from './pages/Atas.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Oportunidades, { EMPTY_FILTERS } from './pages/Oportunidades.jsx'

const NAV = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'oportunidades', label: 'Oportunidades' },
  { key: 'atas', label: 'Radar de Atas' },
  { key: 'acompanhamento', label: 'Acompanhamento' },
  { key: 'analise', label: 'Análise de Compras', soon: true },
]

function useHashRoute() {
  const get = () => (window.location.hash.replace(/^#\/?/, '').split('?')[0] || 'dashboard')
  const [route, setRoute] = useState(get)
  useEffect(() => {
    const on = () => setRoute(get())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const nav = useCallback((r) => { window.location.hash = `/${r}`; window.scrollTo(0, 0) }, [])
  return [NAV.some((n) => n.key === route && !n.soon) ? route : 'dashboard', nav]
}

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [route, nav] = useHashRoute()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [ataFilters, setAtaFilters] = useState(EMPTY_ATA_FILTERS)
  const [open, setOpen] = useState(null)
  const [menu, setMenu] = useState(false)

  const auth = useAuth()
  const tracking = useTracking(auth.user)
  const commercial = useCommercialConfig(auth.user)

  useEffect(() => {
    loadAll().then((d) => {
      d.items.forEach(indexRecord)
      d.atas.forEach(indexRecord)
      setData(d)
    }).catch((e) => setError(e.message))
  }, [])

  const toggleFav = useCallback((r) => {
    tracking.save(r.id, r.tipo, { favorito: !tracking.rows[r.id]?.favorito }).catch(() => {})
  }, [tracking])

  const ctx = useMemo(() => ({
    isFav: tracking.isFav, toggleFav, tracking, auth, commercial,
    config: commercial.config, priorityOrgs: commercial.config.priority_orgs,
  }), [tracking, toggleFav, auth, commercial])

  const go = useCallback((r, f) => {
    if (r === 'oportunidades') setFilters({ ...EMPTY_FILTERS, ...f })
    if (r === 'atas') setAtaFilters({ ...EMPTY_ATA_FILTERS, vigencia: '', ...f })
    nav(r)
  }, [nav])

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 bg-ink text-white">
        <div className="mx-auto flex h-12 max-w-7xl items-center gap-6 px-4">
          <a href="#/dashboard" className="flex items-center gap-2 whitespace-nowrap">
            <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="10" fill="none" stroke="#4589ff" strokeWidth="2" /><circle cx="16" cy="16" r="5" fill="none" stroke="#4589ff" strokeWidth="2" /><path d="M16 16 L25 9" stroke="#78a9ff" strokeWidth="2.5" strokeLinecap="round" /><circle cx="16" cy="16" r="1.8" fill="#fff" /></svg>
            <span className="text-[14px] tracking-wide"><span className="font-semibold">RADAR</span> TLS</span>
          </a>
          <nav className="hidden h-full items-stretch md:flex" aria-label="Navegação principal">
            {NAV.map((n) => <NavItem key={n.key} n={n} active={route === n.key} onClick={() => nav(n.key)} />)}
          </nav>
          <div className="ml-auto hidden text-[11px] text-[#c6c6c6] sm:block">
            {data ? <>Dados de {fmtDate(data.meta.gerado_em, true)}{data.meta.status !== 'ok' ? <span className="ml-2 text-[#f1c21b]">● coleta {data.meta.status}</span> : null}</> : null}
          </div>
          <button className="ml-auto p-2 md:hidden" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>
            <svg width="20" height="20" viewBox="0 0 20 20"><path d="M2 5h16M2 10h16M2 15h16" stroke="#fff" strokeWidth="1.5" /></svg>
          </button>
        </div>
        {menu ? (
          <nav className="flex flex-col border-t border-[#393939] md:hidden">
            {NAV.map((n) => <NavItem key={n.key} n={n} mobile active={route === n.key} onClick={() => { setMenu(false); nav(n.key) }} />)}
          </nav>
        ) : null}
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {error ? (
          <div className="bg-white p-6 text-[14px]">
            <p className="font-semibold text-bad">Não foi possível carregar os dados publicados.</p>
            <p className="mt-1 text-ink-2">{error}. Se o site acabou de ser implantado, aguarde a primeira execução do workflow "Atualizar Radar TLS".</p>
          </div>
        ) : !data ? (
          <div className="p-6 text-[14px] text-muted">Carregando dados…</div>
        ) : (
          <>
            <h1 className="mb-4 text-[24px] font-light">{{
              dashboard: 'Radar de Demanda Pública', oportunidades: 'Oportunidades', atas: 'Radar de Atas', acompanhamento: 'Acompanhamento',
            }[route]}</h1>
            {route === 'dashboard' && <Dashboard data={data} ctx={ctx} go={go} onOpen={setOpen} />}
            {route === 'oportunidades' && <Oportunidades data={data} filters={filters} setFilters={setFilters} ctx={ctx} onOpen={setOpen} />}
            {route === 'atas' && <Atas data={data} filters={ataFilters} setFilters={setAtaFilters} ctx={ctx} onOpen={setOpen} />}
            {route === 'acompanhamento' && <Acompanhamento data={data} ctx={ctx} onOpen={setOpen} />}
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
        className={`flex cursor-default items-center gap-2 px-4 text-[13px] text-[#8d8d8d] ${mobile ? 'py-3' : ''}`}>
        {n.label}<span className="rounded-sm bg-[#393939] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-[#c6c6c6]">Em breve</span>
      </span>
    )
  }
  return (
    <button onClick={onClick} aria-current={active ? 'page' : undefined}
      className={`flex items-center px-4 text-[13px] ${mobile ? 'py-3 text-left' : 'border-b-2'} ${active ? 'border-brand bg-[#262626] text-white' : 'border-transparent text-[#c6c6c6] hover:bg-[#262626] hover:text-white'}`}>
      {n.label}
    </button>
  )
}
