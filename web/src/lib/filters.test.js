import { test } from 'node:test'
import assert from 'node:assert/strict'
import { aggregateValue, filterAtas, filterItems, indexRecord, matchesPartner, matchesPriority } from './filters.js'

const mk = (o) => indexRecord({
  tipo: 'contratacao', orgao: { nome: 'ORGAO A', esfera: 'F', cnpj: '00394460000141' },
  unidade: { uf: 'DF', municipio: 'Brasília', nome: 'UNIDADE' }, classificacao: { score: 50, ofertas: [], fabricantes: [] },
  ...o,
})

const items = [
  mk({ id: '1', objeto: 'Manutenção de switches Cisco', valor_estimado: 100, estagio: 'propostas_abertas',
    classificacao: { score: 90, ofertas: ['Networking'], fabricantes: [{ nome: 'Cisco' }], relacao: 'direta' },
    data_publicacao: '2026-10-01T10:00', data_encerramento_proposta: '2026-11-20T10:00' }),
  mk({ id: '2', objeto: 'Aquisição de storage', valor_estimado: null, estagio: 'publicada',
    orgao: { nome: 'MUNICIPIO X', esfera: 'M', cnpj: '1' }, unidade: { uf: 'SP', municipio: 'Campinas' } }),
  mk({ id: '3', tipo: 'pca', objeto: 'Suporte a firewall', valor_estimado: 50, estagio: 'planejamento' }),
  mk({ id: '3', tipo: 'pca', objeto: 'duplicado', valor_estimado: 50 }),
]

test('busca por palavra ignora acentos e exige todas as palavras', () => {
  assert.deepEqual(filterItems(items, { q: 'manutencao CISCO' }).map((r) => r.id), ['1'])
  assert.deepEqual(filterItems(items, { q: 'switches storage' }), [])
})

test('filtros combinados', () => {
  assert.deepEqual(filterItems(items, { uf: 'DF', estagio: 'propostas_abertas' }).map((r) => r.id), ['1'])
  assert.deepEqual(filterItems(items, { fabricante: 'Cisco', scoreMin: 80 }).map((r) => r.id), ['1'])
  assert.deepEqual(filterItems(items, { vmin: 60 }).map((r) => r.id), ['1'])
  assert.deepEqual(filterItems(items, { prazoAte: '2026-11-30' }).map((r) => r.id), ['1'])
  assert.deepEqual(filterItems(items, { foco: 'df_federal' }).map((r) => r.id), ['1', '3', '3'])
  assert.deepEqual(filterItems(items, { municipio: 'campinas' }).map((r) => r.id), ['2'])
})

test('valor agregado não duplica nem soma ausentes', () => {
  assert.deepEqual(aggregateValue(items), { total: 150, n: 2 })
})

test('órgãos prioritários por nome ou CNPJ', () => {
  assert.equal(matchesPriority(items[0], ['orgão a']), true)
  assert.equal(matchesPriority(items[0], ['00.394.460']), true)
  assert.equal(matchesPriority(items[1], ['orgão a']), false)
})

test('parceiros reconhecidos por palavra inteira', () => {
  const a = indexRecord({ fornecedores: [{ nome: 'O2 SOLUCOES LTDA' }], orgao: {}, unidade: {} })
  assert.deepEqual(matchesPartner(a, ['O2', 'G4F']), ['O2'])
  const b = indexRecord({ fornecedores: [{ nome: 'CO2 AMBIENTAL' }], orgao: {}, unidade: {} })
  assert.deepEqual(matchesPartner(b, ['O2']), [])
})

test('filtro de atas por vigência e adesão', () => {
  const atas = [
    indexRecord({ id: 'a', objeto: 'switch', vigencia_status: 'vigente', adesao_status: 'potencial_verificar', orgao: {}, unidade: {} }),
    indexRecord({ id: 'b', objeto: 'switch', vigencia_status: 'encerrada', adesao_status: 'encerrada', orgao: {}, unidade: {} }),
    indexRecord({ id: 'c', objeto: 'switch', vigencia_status: 'vence_em_breve', adesao_status: 'nao_determinada', orgao: {}, unidade: {} }),
  ]
  assert.deepEqual(filterAtas(atas, { vigencia: 'vigentes' }).map((a) => a.id), ['a', 'c'])
  assert.deepEqual(filterAtas(atas, { vigencia: 'vence_em_breve' }).map((a) => a.id), ['c'])
  assert.deepEqual(filterAtas(atas, { adesao: 'potencial_verificar' }).map((a) => a.id), ['a'])
})
