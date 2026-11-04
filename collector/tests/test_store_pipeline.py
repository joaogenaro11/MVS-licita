"""Testes de armazenamento e do pipeline com cliente simulado (sem rede)."""
import json
from pathlib import Path

import pytest

from radar.pipeline import Runner, export_site
from radar.pncp import SourceError
from radar.store import Store, StoreError

from test_normalize import REAL_COMPRA

CONFIG = Path(__file__).resolve().parents[2] / "config"

TI_COMPRA = dict(REAL_COMPRA,
                 numeroControlePNCP="00394460000141-1-000123/2026", sequencialCompra=123,
                 orgaoEntidade={"cnpj": "00394460000141", "razaoSocial": "ORGAO FEDERAL DE TESTE", "esferaId": "F"},
                 objetoCompra="Contratação de suporte técnico e manutenção preventiva e corretiva de switches e "
                              "roteadores Cisco com atendimento 24x7",
                 valorTotalEstimado=3_000_000.0, linkSistemaOrigem="https://cnetmobile.estaleiro.serpro.gov.br/x?compra=1")


class FakeClient:
    """Simula o PNCPClient: devolve páginas por endpoint; pode falhar sob demanda."""

    def __init__(self, compras=(), atas=(), fail=()):
        self.compras = list(compras)
        self.atas_rows = list(atas)
        self.fail = set(fail)
        from radar.pncp import ClientStats
        self.stats = ClientStats()

    def _pages(self, name, rows):
        if name in self.fail:
            raise SourceError(f"{name} indisponível", status=503)
        self.stats.requests += 1
        if rows:
            yield list(rows)

    def contratacoes_atualizacao(self, a, b, mod):
        return self._pages("atualizacao", [r for r in self.compras if r["modalidadeId"] == mod])

    def contratacoes_publicacao(self, a, b, mod):
        return self._pages("publicacao", [])

    def contratacoes_proposta(self, d):
        return self._pages("proposta", self.compras)

    def atas_atualizacao(self, a, b):
        return self._pages("atas", self.atas_rows)

    def contratos_atualizacao(self, a, b):
        return self._pages("contratos", [])

    def contratos(self, a, b):
        return self._pages("contratos", [])

    def pca_atualizacao(self, a, b):
        return self._pages("pca", [])

    def pca_por_classificacao(self, ano, code):
        return self._pages("pca", [])

    def get_json(self, url, params=None):
        if "atas" in self.fail:
            raise SourceError("atas indisponível", status=503)
        return None

    def compra_itens(self, *a, **k):
        return [{"numeroItem": 1, "descricao": "Serviço de suporte para switch Cisco Catalyst 9300", "quantidade": 10,
                 "valorTotal": 100.0, "orcamentoSigiloso": False}]

    def compra_arquivos(self, *a):
        return [{"url": "https://pncp.gov.br/pncp-api/v1/orgaos/00394460000141/compras/2026/123/arquivos/1",
                 "titulo": "Edital.pdf", "tipoDocumentoNome": "Edital", "statusAtivo": True}]

    def compra_detalhe(self, *a):
        return {}

    def ata_arquivos(self, *a):
        return []


def make_runner(tmp_path, client, budget=5):
    r = Runner(tmp_path, CONFIG, budget_min=budget, backfill=False)
    r.client = client
    return r


def test_pipeline_coleta_classifica_e_deduplica(tmp_path):
    client = FakeClient(compras=[REAL_COMPRA, TI_COMPRA])
    make_runner(tmp_path, client).run()
    items = json.loads((tmp_path / "items.json").read_text())["items"]
    ids = [i["id"] for i in items]
    assert ids == ["00394460000141-1-000123/2026"]           # só o relevante; sem duplicar (2 feeds)
    it = items[0]
    assert it["classificacao"]["score"] >= 80
    assert it["documentos"][0]["url"].startswith("https://pncp.gov.br/")
    assert it["itens"][0]["descricao"].startswith("Serviço de suporte")
    assert it["links"]["origem_portal"] == "Compras.gov.br"
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["status"] == "ok"
    assert meta["fontes"]["contratacoes_atualizacao"]["status"] == "ok"


def test_falha_de_fonte_nao_apaga_dados_e_e_registrada(tmp_path):
    make_runner(tmp_path, FakeClient(compras=[TI_COMPRA])).run()
    # segunda execução: todas as fontes de contratação indisponíveis
    make_runner(tmp_path, FakeClient(fail={"atualizacao", "proposta", "atas"})).run()
    items = json.loads((tmp_path / "items.json").read_text())["items"]
    assert len(items) == 1                                    # dados válidos preservados
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["status"] == "parcial"
    assert "contratacoes_atualizacao" in meta["fontes_com_falha"]
    assert "503" in meta["fontes"]["contratacoes_atualizacao"]["erro"]


def test_cursor_nao_avanca_em_falha(tmp_path):
    r = make_runner(tmp_path, FakeClient(fail={"atualizacao"}))
    r.feed_contratacoes_atualizacao()
    assert "ate" not in r.store.state.get("contratacoes_atualizacao", {})


def test_store_nunca_encolhe(tmp_path):
    s = Store(tmp_path).load()
    s.upsert(s.items, {"id": "a", "tipo": "contratacao"}, "t")
    s.save("t")
    s2 = Store(tmp_path).load()
    s2.items.clear()
    with pytest.raises(StoreError):
        s2.save("t2")
    assert json.loads((tmp_path / "items.json").read_text())["items"][0]["id"] == "a"


def test_upsert_preserva_valor_oficial_conhecido(tmp_path):
    s = Store(tmp_path)
    s.upsert(s.items, {"id": "a", "valor_estimado": 10.0, "feeds": ["x"]}, "t1")
    res = s.upsert(s.items, {"id": "a", "valor_estimado": None, "feeds": ["y"]}, "t2")
    assert s.items["a"]["valor_estimado"] == 10.0
    assert s.items["a"]["feeds"] == ["x", "y"]
    assert res == "same"


def test_export_site_publica_somente_relevantes(tmp_path):
    make_runner(tmp_path, FakeClient(compras=[TI_COMPRA])).run()
    out = tmp_path / "site"
    n = export_site(tmp_path, out, CONFIG)
    assert n["oportunidades"] == 1
    pub = json.loads((out / "opportunities.json").read_text())
    assert "itens_texto" not in pub["items"][0]
    meta = json.loads((out / "meta.json").read_text())
    assert meta["lookups"]["estagios"]["propostas_abertas"] == "Propostas abertas"
