import { test } from 'node:test'
import assert from 'node:assert/strict'
import { agenda, resumoPorDono, snapshotDe } from './crm.js'

const rows = [
  { id: 1, dono: 'a', etapa: 'novo', proximo_acompanhamento: '2026-11-25' },
  { id: 2, dono: 'a', etapa: 'proposta', proximo_acompanhamento: '2026-11-20', valor_negocio: 1000 },
  { id: 3, dono: 'a', etapa: 'ganho', proximo_acompanhamento: '2026-11-20' },
  { id: 4, dono: 'a', etapa: 'qualificando', proximo_acompanhamento: '2026-11-30' },
  { id: 5, dono: 'a', etapa: 'novo', atribuido_por: 'g', visto_em: null },
  { id: 6, dono: 'b', etapa: 'negociacao', snapshot: { valor: 500 } },
]

test('agenda: hoje inclui atrasados, só etapas abertas; semana e pedidos do gestor', () => {
  const ag = agenda(rows.filter((r) => r.dono === 'a'), 'a', '2026-11-25')
  assert.deepEqual(ag.hoje.map((c) => c.id), [2, 1])       // ganho não entra; atrasado primeiro
  assert.equal(ag.atrasados, 1)
  assert.deepEqual(ag.semana.map((c) => c.id), [4])
  assert.deepEqual(ag.pedidos.map((c) => c.id), [5])
  assert.deepEqual(ag.semData.map((c) => c.id), [5])
})

test('resumo por vendedor para o gestor', () => {
  const r = resumoPorDono(rows, '2026-11-25')
  assert.equal(r.a.abertas, 4)
  assert.equal(r.a.hoje, 2)
  assert.equal(r.a.atrasados, 1)
  assert.equal(r.a.ganhos, 1)
  assert.equal(r.a.pedidos, 1)
  assert.equal(r.a.valorAberto, 1000)
  assert.equal(r.b.valorAberto, 500)
  assert.equal(r.b.proposta, 1)
})

test('retrato da oportunidade guardado no CRM', () => {
  const s = snapshotDe({ tipo: 'contratacao', objeto: 'x'.repeat(500), orgao: { nome: 'ORG' }, unidade: { uf: 'DF' },
    valor_estimado: 0, valor_homologado: 10, estagio: 'publicada', links: { pncp: 'https://pncp.gov.br/x' }, classificacao: { score: 77 } })
  assert.equal(s.objeto.length, 400)
  assert.equal(s.valor, 10)
  assert.equal(s.score, 77)
})

test('histórico local espelha o gatilho do banco', async () => {
  const { diffEventos, crmCSV } = await import('./crm.js')
  const novo = { id: 'x', dono: 'a', etapa: 'novo', atribuido_por: 'g', mensagem_atribuicao: 'olha essa' }
  assert.deepEqual(diffEventos(null, novo, 'g').map((e) => e.tipo), ['criado', 'atribuido'])
  const mudou = { ...novo, etapa: 'proposta', proximo_acompanhamento: '2026-12-01', codigo_oportunidade: 'SC-1' }
  const ev = diffEventos(novo, mudou, 'a')
  assert.deepEqual(ev.map((e) => e.tipo), ['etapa', 'acompanhamento', 'codigo'])
  assert.equal(ev[1].texto, '01/12/2026')
  const csv = crmCSV([{ ...mudou, observacao: 'tem; ponto e "aspas"' }])
  assert.match(csv, /"tem; ponto e ""aspas"""/)
  assert.match(csv, /^﻿Etapa;/)
})
