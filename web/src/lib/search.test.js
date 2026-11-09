import { test } from 'node:test'
import assert from 'node:assert/strict'
import { matchQuery, normSearch, parseQuery, searchText } from './search.js'

const labels = (q) => parseQuery(q).terms.map((t) => [t.label, t.phrase])
const T = (s) => searchText([s])
const hits = (q, s) => (matchQuery(parseQuery(q), T(s)) || []).map((t) => t.label)

test('termo único: igual a antes', () => {
  const p = parseQuery('Cisco')
  assert.equal(p.mode, 'simples')
  assert.deepEqual(hits('Cisco', 'Manutenção de switches CISCO'), ['Cisco'])
  assert.deepEqual(hits('Cisco', 'Rua São Francisco'), [])   // casa no início da palavra
  assert.deepEqual(hits('manut', 'Manutenção preventiva'), ['manut'])
  assert.deepEqual(hits('switch', 'aquisição de switches'), ['switch'])
})

test('várias palavras sem vírgula e sem aspas: comportamento atual (todas as palavras, qualquer ordem)', () => {
  assert.equal(parseQuery('Cisco Red Hat').mode, 'simples')
  assert.deepEqual(hits('Cisco Red Hat', 'Suporte Red Hat Enterprise e switches Cisco'), ['Cisco Red Hat'])
  assert.deepEqual(hits('Cisco Red Hat', 'Suporte Red Hat Enterprise'), [])
})

test('vírgula: qualquer um dos termos (OU), sem precisar estar juntos', () => {
  assert.deepEqual(labels('Cisco, Red Hat, Fortinet'), [['Cisco', false], ['Red Hat', false], ['Fortinet', false]])
  assert.deepEqual(hits('Cisco, Red Hat, Fortinet', 'Subscrição Red Hat'), ['Red Hat'])
  assert.deepEqual(hits('Cisco, Red Hat, Fortinet', 'Firewall Fortinet e switch Cisco'), ['Cisco', 'Fortinet'])
  assert.deepEqual(hits('Cisco, Red Hat, Fortinet', 'Aquisição de mobiliário'), [])
})

test('aspas: frase exata, nessa ordem', () => {
  assert.deepEqual(labels('"switch core Cisco"'), [['switch core Cisco', true]])
  assert.deepEqual(hits('"switch core Cisco"', 'Aquisição de switch core Cisco Nexus'), ['switch core Cisco'])
  assert.deepEqual(hits('"switch core Cisco"', 'Switch Cisco core'), [])
  assert.deepEqual(hits('"switch core Cisco"', 'switch core Ciscoxyz'), [])
})

test('mistura de frase e termos', () => {
  assert.deepEqual(labels('"suporte técnico", Cisco, Red Hat'), [['suporte técnico', true], ['Cisco', false], ['Red Hat', false]])
  assert.deepEqual(hits('"suporte técnico", Cisco, Red Hat', 'Suporte técnico Red Hat'), ['suporte técnico', 'Red Hat'])
})

test('vírgula dentro de aspas faz parte da frase', () => {
  assert.deepEqual(labels('"manutenção, suporte", Cisco'), [['manutenção, suporte', true], ['Cisco', false]])
  assert.deepEqual(hits('"manutenção, suporte"', 'serviços de manutenção, suporte e garantia'), ['manutenção, suporte'])
})

test('espaços nas pontas e termos vazios são ignorados', () => {
  assert.deepEqual(labels('Cisco,,'), [['Cisco', false]])
  assert.deepEqual(labels('  Cisco ,  , Red   Hat ,'), [['Cisco', false], ['Red Hat', false]])
  assert.equal(parseQuery(' , , ').mode, 'vazio')
  assert.equal(parseQuery('').mode, 'vazio')
  assert.equal(parseQuery('""').mode, 'vazio')
})

test('aspas sem fechamento: o resto vira frase', () => {
  assert.deepEqual(labels('Cisco, "switch core'), [['Cisco', false], ['switch core', true]])
  assert.deepEqual(labels('"switch core, Cisco'), [['switch core, Cisco', true]])
})

test('aspas curvas e retas', () => {
  assert.deepEqual(labels('“switch core Cisco”'), [['switch core Cisco', true]])
  assert.deepEqual(labels('“suporte técnico”, "Red Hat"'), [['suporte técnico', true], ['Red Hat', true]])
})

test('sem acento e sem diferenciar maiúsculas', () => {
  assert.equal(normSearch('Manutenção TÉCNICA'), 'manutencao tecnica')
  assert.deepEqual(hits('manutencao', 'Manutenção preventiva'), ['manutencao'])
  assert.deepEqual(hits('"MANUTENCAO PREVENTIVA"', 'manutenção preventiva'), ['MANUTENCAO PREVENTIVA'])
  assert.deepEqual(hits('CISCO, red hat', 'Red Hat'), ['red hat'])
})

test('termos repetidos contam uma vez', () => {
  assert.deepEqual(labels('Cisco, cisco, CISCO'), [['Cisco', false]])
})
