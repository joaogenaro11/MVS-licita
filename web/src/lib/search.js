// Sintaxe da barra de pesquisa:
//   Cisco                         -> busca de um termo (como antes)
//   Cisco Red Hat                 -> como antes: todas as palavras, em qualquer posição
//   Cisco, Red Hat, Fortinet      -> QUALQUER um dos termos (OU); cada item segue a regra acima
//   "switch core Cisco"           -> frase exata, nessa ordem
//   "suporte técnico", Cisco      -> pode misturar
// Vírgula dentro de aspas faz parte da frase; aspas sem fechamento: o resto vira frase.
// Aspas retas ("), curvas (“ ”) e baixas („) são aceitas. Sem acento e sem diferenciar maiúsculas.

const OPEN_QUOTES = new Set(['"', '“', '”', '„', '«', '»'])

/** minúsculas, sem acento; pontuação vira espaço (para frases e termos). */
export function normSearch(s) {
  return (s || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

/**
 * @returns {{ mode: 'vazio'|'simples'|'termos', terms: Array<{ label: string, phrase: boolean, words: string[], n: string }> }}
 */
export function parseQuery(q) {
  const raw = (q || '').trim()
  if (!raw) return { mode: 'vazio', terms: [] }
  const hasSyntax = [...raw].some((ch) => ch === ',' || OPEN_QUOTES.has(ch))
  if (!hasSyntax) {
    const t = makeTerm(raw, false)
    return t ? { mode: 'simples', terms: [t] } : { mode: 'vazio', terms: [] }
  }
  const items = []
  let buf = ''
  let quoted = false
  let wasQuoted = false
  const flush = () => {
    const t = makeTerm(buf, wasQuoted)
    if (t) items.push(t)
    buf = ''
    wasQuoted = false
  }
  for (const ch of raw) {
    if (OPEN_QUOTES.has(ch)) {
      if (quoted) { quoted = false } else { quoted = true; wasQuoted = true }
      continue
    }
    if (ch === ',' && !quoted) { flush(); continue }
    buf += ch
  }
  flush() // aspas sem fechamento: o que sobrou é tratado como frase
  // remove repetidos (mesmo termo normalizado e mesmo tipo)
  const seen = new Set()
  const terms = items.filter((t) => {
    const k = `${t.phrase ? 'f' : 'p'}:${t.n}`
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
  return { mode: terms.length ? 'termos' : 'vazio', terms }
}

function makeTerm(text, phrase) {
  const label = text.trim().replace(/\s+/g, ' ')
  const n = normSearch(label)
  if (!n) return null
  return { label, phrase, n, words: n.split(' ') }
}

/** Texto pesquisável normalizado com espaços nas pontas (facilita limite de palavra em frases). */
export function searchText(parts) {
  return ` ${normSearch(parts.filter(Boolean).join(' '))} `
}

/** Um termo casa? Frase: sequência exata com limite de palavra. Sem aspas: todas as palavras
 *  aparecem em qualquer posição; cada palavra casa no INÍCIO de uma palavra do texto
 *  ("manut" acha "manutenção", "switch" acha "switches", mas "cisco" não acha "Francisco"). */
export function termMatches(term, text) {
  if (term.phrase) return text.includes(` ${term.n} `)
  return term.words.every((w) => text.includes(` ${w}`))
}

/** Termos da busca que casaram no registro (vazio = não casou). Para a busca simples, exige o termo. */
export function matchQuery(parsed, text) {
  if (!parsed || parsed.mode === 'vazio') return null
  return parsed.terms.filter((t) => termMatches(t, text))
}
