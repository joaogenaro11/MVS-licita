import { test } from 'node:test'
import assert from 'node:assert/strict'
import { aggregateValue, bySearchThen, filterAtas, filterItems, indexRecord, matchesPartner, matchesPriority, portfolioCounts, portfolioLabel, SORTS } from './filters.js'

const mk = (o) => indexRecord({
  tipo: 'contratacao', orgao: { nome: 'ORGAO A', esfera: 'F', cnpj: '00394460000141' },
  unidade: { uf: 'DF', municipio: 'Brasília', nome: 'UNIDADE' }, classificacao: { pontuacao: 3, ofertas: [], portfolio: ['transversal'] },
  ...o,
})

const items = [
  mk({ id: '1', objeto: 'Manutenção de switches Cisco', valor_estimado: 100, estagio: 'propostas_abertas',
    classificacao: { pontuacao: 9, ofertas: ['Suporte multivendor Cisco'], portfolio: ['mvs'], termos: ['Cisco'] },
    data_publicacao: '2026-10-01T10:00', data_encerramento_proposta: '2026-11-20T10:00' }),
  mk({ id: '2', objeto: 'Aquisição de storage', valor_estimado: null, estagio: 'publicada',
    orgao: { nome: 'MUNICIPIO X', esfera: 'M', cnpj: '1' }, unidade: { uf: 'SP', municipio: 'Campinas' } }),
  mk({ id: '3', tipo: 'pca', objeto: 'Suporte a firewall', valor_estimado: 50, estagio: 'planejamento',
    classificacao: { pontuacao: 4.5, ofertas: [], portfolio: ['logo', 'mvs'] } }),
  mk({ id: '3', tipo: 'pca', objeto: 'duplicado', valor_estimado: 50 }),
]

test('busca por palavra ignora acentos e exige todas as palavras', () => {
  assert.deepEqual(filterItems(items, { q: 'manutencao CISCO' }).map((r) => r.id), ['1'])
  assert.deepEqual(filterItems(items, { q: 'switches storage' }), [])
})

test('busca com vírgula traz qualquer termo e ordena por quantidade de termos casados', () => {
  const r = filterItems(items, { q: 'storage, firewall, "switches cisco", manutenção' })
  assert.deepEqual(r.map((x) => x.id).sort(), ['1', '2', '3'])   // o 2º '3' (duplicado) não tem nenhum termo
  const ordered = [...r].sort(bySearchThen(SORTS.score))
  assert.equal(ordered[0].id, '1')                         // casou 2 termos: frase + manutenção
  assert.deepEqual(ordered[0]._casou, ['switches cisco', 'manutenção'])
  assert.deepEqual(filterItems(items, { q: 'storage, firewall', uf: 'SP' }).map((x) => x.id), ['2']) // combina com filtros
})

test('filtro de portfólio Tudo / Logo / MVS e contadores', () => {
  assert.deepEqual(filterItems(items, { portfolio: 'mvs' }).map((r) => r.id), ['1', '3'])
  assert.deepEqual(filterItems(items, { portfolio: 'logo' }).map((r) => r.id), ['3'])
  assert.equal(filterItems(items, { portfolio: 'tudo' }).length, 4)
  assert.deepEqual(portfolioCounts(items), { tudo: 4, logo: 1, mvs: 2 })
  assert.equal(portfolioLabel(['logo', 'mvs']), 'Logo IBM + MVS')
  assert.equal(portfolioLabel(['transversal']), 'Transversal')
})

test('filtros combinados', () => {
  assert.deepEqual(filterItems(items, { uf: 'DF', estagio: 'propostas_abertas' }).map((r) => r.id), ['1'])
  assert.deepEqual(filterItems(items, { oferta: 'Suporte multivendor Cisco', scoreMin: 6 }).map((r) => r.id), ['1'])
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
