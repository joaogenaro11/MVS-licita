const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const BRL_COMPACT = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 })

export function money(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v)) || Number(v) <= 0) return null
  return BRL.format(Number(v))
}

export function moneyCompact(v) {
  if (!v) return 'R$ 0'
  return 'R$ ' + BRL_COMPACT.format(v)
}

export function parseDate(s) {
  if (!s) return null
  const d = new Date(s.length === 10 ? s + 'T00:00:00' : s)
  return Number.isNaN(d.getTime()) ? null : d
}

export function fmtDate(s, withTime = false) {
  const d = parseDate(s)
  if (!d) return null
  const opts = { day: '2-digit', month: '2-digit', year: 'numeric' }
  if (withTime && s.length > 10) Object.assign(opts, { hour: '2-digit', minute: '2-digit' })
  return d.toLocaleString('pt-BR', opts)
}

export function daysUntil(s, now = new Date()) {
  const d = parseDate(s)
  if (!d) return null
  return Math.ceil((d - now) / 86400000)
}

export function relDays(n) {
  if (n === null || n === undefined) return ''
  if (n === 0) return 'hoje'
  if (n === 1) return 'amanhã'
  if (n > 1) return `em ${n} dias`
  if (n === -1) return 'ontem'
  return `há ${-n} dias`
}

/** minúsculas, sem acentos — igual à normalização do coletor */
export function norm(s) {
  return (s || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9/.\- ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export const ESFERAS = { F: 'Federal', E: 'Estadual', M: 'Municipal', D: 'Distrital', N: 'Não informada' }

export const UFS = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE',
  'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO']
