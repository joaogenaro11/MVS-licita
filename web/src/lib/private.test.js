import { test } from 'node:test'
import assert from 'node:assert/strict'

// private.js usa import.meta.env (Vite); testamos apenas o parser, isolado.
const src = await import('node:fs').then((fs) => fs.readFileSync(new URL('./private.js', import.meta.url), 'utf8'))
const start = src.indexOf('export function parseConfigText')
const fnSrc = src.slice(start).replace(/export /g, '')
const { parseConfigText, configToText } = new Function(`${fnSrc}; return { parseConfigText, configToText }`)()

test('parser da configuração comercial (formato YAML simples)', () => {
  const cfg = parseConfigText(`
# comentário
offers:
  networking: {fit_factor: 1.0}
priority_orgs:
  - ADVOCACIA-GERAL DA UNIAO
  - 00394460000141
partners:
  - O2
vendor_notes:
  Oracle: "Sem fix do fabricante."
`)
  assert.deepEqual(cfg.priority_orgs, ['ADVOCACIA-GERAL DA UNIAO', '00394460000141'])
  assert.deepEqual(cfg.partners, ['O2'])
  assert.equal(cfg.vendor_notes.Oracle, 'Sem fix do fabricante.')
  assert.deepEqual(parseConfigText(configToText(cfg)), cfg)
})
