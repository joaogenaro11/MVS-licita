import { test } from 'node:test'
import assert from 'node:assert/strict'
import { hashId, linkDe } from './link.js'

test('link próprio da oportunidade: id com barra vai codificado e volta igual', () => {
  const loc = { origin: 'https://exemplo.github.io', pathname: '/MVS-licita/' }
  const id = '00348003000110-1-001574/2026'
  const url = linkDe({ id, tipo: 'contratacao' }, loc)
  assert.equal(url, 'https://exemplo.github.io/MVS-licita/#/oportunidades?id=00348003000110-1-001574%2F2026')
  assert.equal(hashId(url.slice(url.indexOf('#'))), id)
  assert.match(linkDe({ id: 'x', tipo: 'ata' }, loc), /#\/atas\?id=x$/)
  assert.equal(hashId('#/oportunidades'), null)
})
