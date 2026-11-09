import { test } from 'node:test'
import assert from 'node:assert/strict'
import { highlightParts, highlightRanges } from './highlight.js'

const hits = (t, terms) => highlightParts(t, terms).filter((p) => p.hit).map((p) => p.text)

test('destaca termos por palavra inteira, sem acento e sem diferenciar maiúsculas', () => {
  assert.deepEqual(hits('Manutenção de firewall Fortinet FortiGate', ['fortinet', 'manutencao']), ['Manutenção', 'Fortinet'])
  assert.deepEqual(hits('Rua São Francisco', ['Cisco']), [])
  assert.deepEqual(hits('Rede SDN Cisco ACI, 24x7', ['Cisco ACI', '24x7', 'SDN']), ['SDN', 'Cisco ACI', '24x7'])
})

test('pontuação e hífen equivalem a espaço; sobreposições são unidas', () => {
  assert.deepEqual(hits('Pontos de acesso Wi-Fi 6E', ['Wi-Fi']), ['Wi-Fi'])
  assert.deepEqual(hits('switch SAN Brocade', ['switch SAN', 'SAN Brocade']), ['switch SAN Brocade'])
  assert.deepEqual(highlightRanges('', ['x']), [])
  assert.deepEqual(highlightParts('abc', []), [{ text: 'abc', hit: false }])
})
