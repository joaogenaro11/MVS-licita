// Teste funcional da interface (Playwright), independente dos dados: roda tanto com dados
// sintéticos locais quanto com o site construído a partir de dados REAIS no CI.
//
//   node tests-e2e/ui-check.mjs http://localhost:4173/ [pasta-de-screenshots]
//
// Sai com código 1 se qualquer verificação falhar. Imprime um checklist PASS/FAIL.
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:4173/'
const SHOTS = process.argv[3] || ''
const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}
const safe = async (name, fn) => {
  try { await fn() } catch (e) { check(name, false, e.message.split('\n')[0]) }
}

const browser = await chromium.launch()
const errors = []
const newPage = async (opts = {}, collectErrors = true) => {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, ...opts })
  const p = await ctx.newPage()
  if (collectErrors) {
    p.on('pageerror', (e) => errors.push(e.message))
    p.on('console', (m) => { if (m.type() === 'error' && !/favicon|fonts\.g/.test(m.text())) errors.push(m.text()) })
  }
  return p
}
const shot = async (p, name) => { if (SHOTS) await p.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }) }
const nav = async (p, label) => { await p.locator('nav[aria-label="Navegação principal"] button', { hasText: label }).click() }
const countText = async (p) => {
  const t = await p.locator('text=/resultado\\(s\\) na base coletada/').first().innerText()
  return Number(t.replace(/\D/g, '').slice(0, 7) || 0)
}

const page = await newPage()
await page.goto(BASE, { waitUntil: 'networkidle' })

// 1. Dashboard
await safe('Dashboard carrega com KPIs e data da última coleta', async () => {
  await page.waitForSelector('text=Radar de Demanda Pública', { timeout: 15000 })
  const kpis = ['Oportunidades encontradas', 'Propostas abertas', 'Demandas em planejamento (PCA)', 'Logo IBM / MVS',
    'Atas vigentes relevantes', 'Atas com potencial de adesão a avaliar', 'Valor estimado agregado']
  const missing = []
  for (const k of kpis) if (!(await page.locator(`text=${k}`).count())) missing.push(k)
  const ultima = await page.locator('text=Última coleta:').count()
  check('Dashboard carrega com KPIs e data da última coleta', missing.length === 0 && ultima > 0,
    missing.length ? `faltando: ${missing.join(', ')}` : '')
})
await safe('Card "Atualização dos dados" só com título, última coleta e status geral', async () => {
  const card = page.locator('section[aria-label="Atualização dos dados"]')
  const t = await card.innerText()
  const linhas = t.split('\n').map((x) => x.trim()).filter(Boolean)
  const proibidos = ['Contratações (atualizações diárias)', 'Carga histórica', 'Varredura de atas', 'Itens e documentos oficiais', 'PCA']
  const sobra = proibidos.filter((x) => t.includes(x))
  check('Card "Atualização dos dados" só com título, última coleta e status geral',
    linhas.length === 3 && /^Atualização dos dados$/.test(linhas[0]) && /^Última coleta: /.test(linhas[1]) && /^Status geral: /.test(linhas[2]) && !sobra.length,
    linhas.join(' | '))
})
await safe('Aba "Análise de Compras" visível, com "Em breve" e não clicável', async () => {
  const item = page.locator('nav[aria-label="Navegação principal"] [aria-disabled="true"]', { hasText: 'Análise de Compras' })
  const visible = await item.isVisible()
  const badge = await item.locator('text=Em breve').count()
  const before = page.url()
  await item.click({ force: true })
  check('Aba "Análise de Compras" visível, com "Em breve" e não clicável', visible && badge > 0 && page.url() === before)
})
await shot(page, '01-dashboard')

// 2. Oportunidades: busca e filtros
let total = 0
await nav(page, 'Oportunidades')
await safe('Listagem de oportunidades com dados coletados', async () => {
  await page.waitForSelector('text=/resultado\\(s\\) na base coletada/')
  total = await countText(page)
  check('Listagem de oportunidades com dados coletados', total > 0, `${total} oportunidades`)
})
await safe('Card: valor, pontuação, selo de portfólio, ofertas casadas (chips) e termos destacados', async () => {
  const card = page.locator('main ul > li').first()
  const txt = await card.innerText()
  const chips = await card.locator('span.rounded-full').count()
  const marks = await page.locator('main ul > li mark').count()
  const ok = /Valor estimado:/.test(txt) && /pontuação/.test(txt) && /(Logo IBM \+ MVS|Logo IBM|MVS|Transversal)/.test(txt) &&
    /Termos:/.test(txt) && chips > 0 && marks > 0
  check('Card: valor, pontuação, selo de portfólio, ofertas casadas (chips) e termos destacados', ok, `${chips} chips, ${marks} destaques na página`)
})
await safe('Filtro de portfólio Tudo / Logo / MVS com contadores', async () => {
  const radios = page.locator('[role="radiogroup"][aria-label="Portfólio"] [role="radio"]')
  const labels = await radios.allInnerTexts()
  const num = (i) => Number((labels[i].match(/\(([\d.]+)\)/) || [0, '0'])[1].replace(/\./g, ''))
  const [tudo, logo, mvs] = [num(0), num(1), num(2)]
  await radios.nth(2).click(); await page.waitForTimeout(200)
  const nMvs = await countText(page)
  const badges = await page.locator('main ul > li').evaluateAll((els) => els.slice(0, 30).map((e) => e.innerText))
  const soMvs = badges.every((t) => /MVS/.test(t))
  await radios.nth(1).click(); await page.waitForTimeout(200)
  const nLogo = await countText(page)
  const badgesL = await page.locator('main ul > li').evaluateAll((els) => els.slice(0, 30).map((e) => e.innerText))
  const soLogo = badgesL.every((t) => /Logo IBM/.test(t))
  await radios.nth(0).click(); await page.waitForTimeout(200)
  check('Filtro de portfólio Tudo / Logo / MVS com contadores',
    tudo === total && nMvs === mvs && nLogo === logo && soMvs && soLogo && (await countText(page)) === total,
    `Tudo ${tudo} · Logo ${logo} · MVS ${mvs}`)
})
await safe('Links oficiais: abrem em nova aba, https/http válidos, sem link genérico', async () => {
  const links = page.locator('main ul > li a[target="_blank"]')
  const n = await links.count()
  let bad = 0
  for (let i = 0; i < Math.min(n, 60); i++) {
    const a = links.nth(i)
    const href = await a.getAttribute('href')
    const rel = await a.getAttribute('rel')
    if (!/^https?:\/\/[^/]+\.[^/]+\/.+/.test(href || '') || !/noopener/.test(rel || '')) bad++
  }
  const portal = await page.locator('main ul > li a', { hasText: /Abrir no (Portal de Compras|PNCP)/ }).count()
  check('Links oficiais: abrem em nova aba, https/http válidos, sem link genérico', n > 0 && bad === 0 && portal > 0,
    `${n} links, ${bad} inválidos, ${portal} botões de acesso direto`)
})
await safe('Busca: dica, vírgula = qualquer termo, aspas = frase exata, "casou:" no card', async () => {
  const dica = await page.locator('text=Separe termos por vírgula para buscar qualquer um deles. Use aspas para frase exata.').count()
  const cnt = async (q) => { await page.fill('input[type="search"]', q); await page.waitForTimeout(250); return countText(page) }
  const a = await cnt('cisco'); const b = await cnt('firewall')
  const ou = await cnt('cisco, firewall')
  const casou = await page.locator('main ul > li >> text=casou:').count()
  const frase = await cnt('"suporte tecnico"')
  const palavras = await cnt('suporte tecnico')
  await page.fill('input[type="search"]', '')
  check('Busca: dica, vírgula = qualquer termo, aspas = frase exata, "casou:" no card',
    dica > 0 && ou >= Math.max(a, b) && ou <= a + b && casou > 0 && frase <= palavras,
    `cisco ${a} · firewall ${b} · "cisco, firewall" ${ou} · frase ${frase} ≤ palavras ${palavras}`)
})
await safe('Busca por palavra-chave filtra resultados', async () => {
  const first = await page.locator('main ul > li button.text-left').first().innerText()
  const word = (first.normalize('NFD').replace(/[̀-ͯ]/g, '').match(/[A-Za-z]{6,}/g) || ['suporte'])[0]
  await page.fill('input[type="search"]', word)
  await page.waitForTimeout(300)
  const n = await countText(page)
  check('Busca por palavra-chave filtra resultados', n > 0 && n <= total, `"${word}" → ${n} de ${total}`)
  await page.fill('input[type="search"]', 'zzzzpalavrainexistentezzzz')
  await page.waitForTimeout(200)
  const none = await page.locator('text=Nenhuma oportunidade com esses filtros').count()
  check('Busca sem resultado mostra mensagem (sem inventar resultados)', none > 0)
  await page.fill('input[type="search"]', '')
})
await safe('Filtros avançados (UF, pontuação, valor, prazo, foco DF/federal)', async () => {
  await page.click('text=Mais filtros')
  const labels = ['Órgão / unidade', 'UF', 'Município', 'Modalidade', 'Selo', 'Valor mínimo (R$)', 'Valor máximo (R$)',
    'Publicado a partir de', 'Prazo de propostas até', 'Pontuação mínima', 'Foco']
  const missing = []
  for (const l of labels) if (!(await page.locator(`label:has-text("${l}")`).count())) missing.push(l)
  check('Filtros avançados presentes', missing.length === 0, missing.join(', '))
  await page.locator('label:has-text("Pontuação mínima") select').selectOption('4.5')
  await page.waitForTimeout(200)
  const scores = await page.locator('main ul > li .num.text-2xl').allInnerTexts()
  const allOk = scores.every((s) => Number(s.replace(',', '.')) >= 4.5)
  check('Filtro de pontuação mínima respeitado em todos os cards', allOk, `${scores.length} cards`)
  await page.locator('label:has-text("Valor mínimo (R$)") input').fill('999999999999')
  await page.waitForTimeout(200)
  const n = await countText(page)
  check('Filtro de valor mínimo exclui registros', n === 0)
  await page.click('text=limpar filtros')
  await page.waitForTimeout(200)
  check('Limpar filtros restaura a listagem', (await countText(page)) === total)
})
await safe('Ordenação por prazo/valor/publicação', async () => {
  for (const v of ['prazo', 'valor', 'publicacao', 'score']) await page.locator('select:near(:text("Ordenar por"))').first().selectOption(v)
  check('Ordenação por prazo/valor/publicação', (await countText(page)) === total)
})
await shot(page, '02-oportunidades')

// 3. Detalhes
await safe('Tela de detalhes: ofertas casadas, como casou, termos, pontuação e coleta', async () => {
  await page.locator('main ul > li button:has-text("Detalhes")').first().click()
  await page.waitForSelector('[role="dialog"]')
  const t = await page.locator('[role="dialog"]').innerText()
  const ok = /Classificação TLS/.test(t) && /Portfólio:/.test(t) && /Como casou/.test(t) && /(Termo exato|Marca \+ serviço)/.test(t) &&
    /Coletado pelo Radar em/.test(t) && /PDFs não são lidos/.test(t)
  check('Tela de detalhes: ofertas casadas, como casou, termos, pontuação e coleta', ok)
  const access = await page.locator('[role="dialog"] a', { hasText: /Abrir no (Portal de Compras|PNCP)/ }).count()
  check('Botão de acesso direto também na tela de detalhes', access > 0)
  await shot(page, '03-detalhe')
})
await safe('Acompanhamento comercial salva (status/responsável/observação)', async () => {
  const dlg = page.locator('[role="dialog"]')
  await dlg.locator('label:has-text("Status comercial") select').selectOption('Em análise')
  await dlg.locator('label:has-text("Responsável") input').fill('Teste automatizado')
  await dlg.locator('label:has-text("Observação") textarea').fill('Verificação funcional')
  await dlg.locator('button:has-text("Salvar acompanhamento")').click()
  await page.waitForSelector('text=Salvo.', { timeout: 5000 })
  check('Acompanhamento comercial salva (status/responsável/observação)', true)
  await dlg.locator('button[aria-pressed]').first().click() // favoritar
  await page.keyboard.press('Escape')
  check('Detalhes fecham com Esc', (await page.locator('[role="dialog"]').count()) === 0)
})

// 4. Acompanhamento + persistência local + configuração comercial privada
await safe('Favorito/acompanhamento aparece e persiste após recarregar (local)', async () => {
  await nav(page, 'Acompanhamento')
  await page.reload({ waitUntil: 'networkidle' })
  await nav(page, 'Acompanhamento')
  const t = await page.locator('main').innerText()
  check('Favorito/acompanhamento aparece e persiste após recarregar (local)', /Em análise/.test(t) && /Teste automatizado/.test(t) && /meu favorito/.test(t))
  check('Aviso explícito de que favoritos locais não são compartilhados', /somente neste navegador/.test(t))
})
await safe('Configuração comercial privada: órgão prioritário marca e filtra', async () => {
  await nav(page, 'Oportunidades')
  const org = (await page.locator('main ul > li .font-medium.text-ink').first().innerText()).trim()
  await nav(page, 'Acompanhamento')
  await page.click('button:has-text("editar")')
  await page.locator('textarea').last().fill(`priority_orgs:\n  - ${org}\n\npartners:\n  - EXEMPLO\n\nvendor_notes:\n  Cisco: "nota de teste"`)
  await page.click('button:has-text("Salvar configuração")')
  await page.waitForSelector('text=Configuração salva.')
  await nav(page, 'Oportunidades')
  await page.click('text=Mais filtros')
  await page.locator('label:has-text("Órgãos prioritários") input').check()
  await page.waitForTimeout(200)
  const n = await countText(page)
  const badge = await page.locator('main ul > li >> text=Órgão prioritário').count()
  check('Configuração comercial privada: órgão prioritário marca e filtra', n > 0 && badge > 0, `"${org}" → ${n}`)
  await page.click('text=limpar filtros')
})

// 5. Radar de Atas
await safe('Radar de Atas: aviso de adesão indicativa e filtros', async () => {
  await nav(page, 'Radar de Atas')
  await page.waitForSelector('text=Radar de Atas.')
  const t = await page.locator('main').innerText()
  const filters = ['Vigência', 'Adesão', 'Órgão gerenciador', 'Oferta TLS', 'Selo', 'Valor mínimo (R$)']
  const missing = filters.filter((f) => !t.includes(f))
  check('Radar de Atas: aviso de adesão indicativa e filtros', /indicativo/.test(t) && missing.length === 0, missing.join(', '))
  await page.locator('label:has-text("Vigência") select').selectOption('')
  await page.waitForTimeout(200)
  const cards = await page.locator('main ul > li').count()
  if (cards > 0) {
    const ct = await page.locator('main ul > li').first().innerText()
    check('Card de ata: vigência, fornecedor, situação de adesão (sem afirmar elegibilidade)',
      /Vigência:/.test(ct) && /Fornecedor:/.test(ct) && /(adesão|Ata encerrada)/i.test(ct))
    await page.locator('main ul > li button:has-text("Detalhes e documentos")').first().click()
    const dt = await page.locator('[role="dialog"]').innerText()
    check('Detalhe da ata: datas de vigência e ressalva legal (art. 86)', /Fim da vigência/.test(dt) && /art\. 86/.test(dt))
    await page.keyboard.press('Escape')
  } else {
    check('Radar de Atas sem atas: mensagem honesta (sem dados inventados)',
      (await page.locator('text=Nenhuma ata com esses filtros').count()) > 0, 'base sem atas nesta execução')
  }
  await shot(page, '04-atas')
})

// 6. Celular
await safe('Celular: sem rolagem horizontal, menu e navegação funcionam', async () => {
  const m = await newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  await m.goto(BASE, { waitUntil: 'networkidle' })
  await m.waitForSelector('text=Radar de Demanda Pública')
  const w1 = await m.evaluate(() => document.documentElement.scrollWidth)
  await m.click('[aria-label="Menu"]')
  await m.locator('header nav button', { hasText: 'Oportunidades' }).last().click()
  await m.waitForSelector('text=/resultado\\(s\\) na base coletada/')
  const w2 = await m.evaluate(() => document.documentElement.scrollWidth)
  check('Celular: sem rolagem horizontal, menu e navegação funcionam', w1 <= 390 && w2 <= 390, `largura ${w1}/${w2}px`)
  await shot(m, '05-celular')
})

// 7. Falha de dados → mensagem clara (não tela vazia)
await safe('Sem dados publicados: mensagem clara em vez de tela vazia', async () => {
  const e = await newPage({}, false) // erro 404 aqui é proposital
  await e.route('**/data/meta.json', (r) => r.fulfill({ status: 404, body: 'not found' }))
  await e.goto(BASE, { waitUntil: 'networkidle' })
  const ok = await e.locator('text=Não foi possível carregar os dados').count()
  check('Sem dados publicados: mensagem clara em vez de tela vazia', ok > 0)
})

check('Nenhum erro de JavaScript no navegador', errors.length === 0, errors.slice(0, 3).join(' | '))
await browser.close()
const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} verificações passaram`)
process.exit(failed.length ? 1 : 0)
