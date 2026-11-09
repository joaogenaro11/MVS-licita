// Destaque dos termos que deram match: mesma normalização do classificador (sem acento,
// minúsculas, pontuação = espaço, palavra inteira), mapeada de volta para o texto original.

function normalizeWithMap(text) {
  const chars = []
  const idx = []
  const src = text || ''
  for (let i = 0; i < src.length; i++) {
    for (let c of src[i].normalize('NFD')) {
      if (/[̀-ͯ]/.test(c)) continue
      c = c.toLowerCase()
      if (!/[a-z0-9]/.test(c)) c = ' '
      if (c === ' ' && (!chars.length || chars[chars.length - 1] === ' ')) continue
      chars.push(c)
      idx.push(i)
    }
  }
  return { n: chars.join(''), idx }
}

const normTerm = (t) => normalizeWithMap(t).n.trim()
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Intervalos [início, fim) do texto original onde aparecem os termos (palavra inteira). */
export function highlightRanges(text, terms) {
  if (!text || !terms?.length) return []
  const { n, idx } = normalizeWithMap(text)
  const ranges = []
  const uniq = [...new Set(terms.map(normTerm).filter(Boolean))].sort((a, b) => b.length - a.length)
  for (const t of uniq) {
    const rx = new RegExp(`(?<![a-z0-9])${esc(t)}(?![a-z0-9])`, 'g')
    let m
    while ((m = rx.exec(n))) {
      const start = idx[m.index]
      const endChar = idx[m.index + t.length - 1]
      ranges.push([start, endChar + 1])
    }
  }
  ranges.sort((a, b) => a[0] - b[0])
  const merged = []
  for (const r of ranges) {
    const last = merged[merged.length - 1]
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]); else merged.push([...r])
  }
  return merged
}

/** Divide o texto em partes { text, hit } para renderização. */
export function highlightParts(text, terms) {
  const ranges = highlightRanges(text, terms)
  if (!ranges.length) return [{ text: text || '', hit: false }]
  const out = []
  let pos = 0
  for (const [a, b] of ranges) {
    if (a > pos) out.push({ text: text.slice(pos, a), hit: false })
    out.push({ text: text.slice(a, b), hit: true })
    pos = b
  }
  if (pos < text.length) out.push({ text: text.slice(pos), hit: false })
  return out
}
