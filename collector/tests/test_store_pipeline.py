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
                 valorTotalEstimado=3_000_000.0, linkSistemaOrigem="https://cnetmobile.estaleiro.serpro.gov.br/x?compra=1",
                 # prazo distante: o teste não pode depender da data em que roda
                 dataAberturaProposta="2026-01-01T08:00:00", dataEncerramentoProposta="2099-12-31T18:00:00")


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
    assert "classificacao" not in it                         # branch público: classificação nunca é gravada
    assert it["publicado_em"]
    assert it["documentos"][0]["url"].startswith("https://pncp.gov.br/")
    assert it["itens"][0]["descricao"].startswith("Serviço de suporte")
    assert it["links"]["origem_portal"] == "Compras.gov.br"
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["fontes"]["contratacoes_atualizacao"]["status"] == "ok"
    assert meta["fontes"]["pca"]["status"] == "ok"
    assert meta["status"] == "ok" and meta["fontes_com_falha"] == []


def test_pca_sem_classes_configuradas_vira_pendencia_explicita(tmp_path):
    r = make_runner(tmp_path, FakeClient())
    r.cfg["pncp"]["pca"]["classificacoes"] = []
    r.feed_pca()
    rec = r.sources["pca"]
    assert rec["status"] == "falha" and "classificação" in rec["erro"]   # pendência explícita, não silêncio


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


def test_upsert_preserva_campos_enriquecidos_em_dicts(tmp_path):
    s = Store(tmp_path)
    s.upsert(s.atas, {"id": "a", "orgao": {"nome": "X", "esfera": None}, "unidade": {"uf": None}}, "t1")
    s.atas["a"]["orgao"]["esfera"] = "F"          # enriquecido depois
    s.atas["a"]["unidade"]["uf"] = "DF"
    s.upsert(s.atas, {"id": "a", "orgao": {"nome": "X", "esfera": None}, "unidade": {"uf": None}}, "t2")
    assert s.atas["a"]["orgao"]["esfera"] == "F" and s.atas["a"]["unidade"]["uf"] == "DF"


def test_export_site_publica_somente_relevantes(tmp_path):
    make_runner(tmp_path, FakeClient(compras=[TI_COMPRA])).run()
    out = tmp_path / "site"
    n = export_site(tmp_path, out, CONFIG)
    assert n["oportunidades"] == 1
    pub = json.loads((out / "opportunities.json").read_text())
    assert "itens_texto" not in pub["items"][0]
    c = pub["items"][0]["classificacao"]
    assert c["tls"] and c["portfolio"] == ["mvs"] and c["ofertas_casadas"][0]["id"] == "sint_suporte_cisco"
    assert "Cisco" in c["termos"] and c["pontuacao"] >= 3 and "sinais" not in c
    meta = json.loads((out / "meta.json").read_text())
    assert meta["lookups"]["estagios"]["propostas_abertas"] == "Propostas abertas"


def test_historico_de_sucesso_da_fonte_sobrevive_a_falha(tmp_path):
    """Regressão: meta.json grava 'fontes'; o runner deve relê-lo para manter o último sucesso."""
    make_runner(tmp_path, FakeClient(compras=[TI_COMPRA])).run()
    ok = json.loads((tmp_path / "meta.json").read_text())["fontes"]["contratacoes_atualizacao"]["ultimo_sucesso"]
    make_runner(tmp_path, FakeClient(fail={"atualizacao"})).run()
    f = json.loads((tmp_path / "meta.json").read_text())["fontes"]["contratacoes_atualizacao"]
    assert f["status"] == "falha" and f["ultimo_sucesso"] == ok and ok



def test_item_publicado_so_sai_do_site_quando_vence(tmp_path):
    """Regra de negócio: depois de entrar no site, só sai ao VENCER (não por reclassificação)."""
    make_runner(tmp_path, FakeClient(compras=[TI_COMPRA])).run()
    out = tmp_path / "site"
    assert export_site(tmp_path, out, CONFIG)["oportunidades"] == 1
    # reclassificação deixa de casar oferta (texto mudou na fonte): continua no site (ainda não venceu)
    s = Store(tmp_path).load()
    it = s.items["00394460000141-1-000123/2026"]
    assert it["publicado_em"]
    it["objeto"], it["itens"] = "Aquisição de mobiliário", []
    s.save("t")
    assert export_site(tmp_path, out, CONFIG)["oportunidades"] == 1
    pub = json.loads((out / "opportunities.json").read_text())["items"][0]
    assert pub["vence_em"] == "2099-12-31" and "propostas" in pub["vence_motivo"]
    # prazo encerrado: sai do site, mas continua na base histórica
    s = Store(tmp_path).load()
    s.items["00394460000141-1-000123/2026"]["data_encerramento_proposta"] = "2020-01-01T10:00"
    s.save("t")
    n = export_site(tmp_path, out, CONFIG)
    assert n["oportunidades"] == 0
    assert "00394460000141-1-000123/2026" in Store(tmp_path).load().items
    assert json.loads((out / "meta.json").read_text())["publicado"]["vencidos_fora_do_site"] == 1


def test_troca_de_classificador_redecide_publicacao_uma_vez(tmp_path):
    """Migração para a base de ofertas JSON: o que foi publicado pela taxonomia antiga e não casa
    nenhuma oferta sai; o que casa fica. Depois disso volta a valer "só sai quando vencer"."""
    s = Store(tmp_path)
    base = {"tipo": "contratacao", "estagio": "propostas_abertas", "orgao": {}, "unidade": {}, "links": {},
            "publicado_em": "2026-11-01T00:00:00", "data_encerramento_proposta": "2099-01-01T00:00"}
    s.upsert(s.items, {**base, "id": "casa", "objeto": "Suporte técnico Cisco Catalyst"}, "t")
    s.upsert(s.items, {**base, "id": "nao-casa", "objeto": "Aquisição de cadeiras", "classificacao": {"score": 90}}, "t")
    s.save("t")
    r = make_runner(tmp_path, FakeClient())
    r.reclassify_all()
    assert r.store.items["casa"]["publicado_em"] and not r.store.items["nao-casa"]["publicado_em"]
    assert r.store.state["migracao_ofertas"]["retirados"] == 1
    # 2ª vez não mexe mais (idempotente; sticky volta a valer)
    r.store.items["casa"]["objeto"] = "Aquisição de cadeiras"
    r.reclassify_all()
    assert r.store.items["casa"]["publicado_em"]


def test_sem_base_de_ofertas_a_coleta_para_com_mensagem_clara(tmp_path, monkeypatch):
    from radar.ofertas import OfertasError
    monkeypatch.setenv("RADAR_OFERTAS_FILE", "")
    monkeypatch.setattr("radar.ofertas.LOCAL_FILE", tmp_path / "nao-existe.json")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(OfertasError, match="não configurada"):
        Runner(tmp_path, CONFIG, budget_min=1, backfill=False)


def test_cargas_longas_dividem_o_tempo_restante(tmp_path):
    """Regressão: a varredura de atas rodava primeiro e usava todo o tempo; as cargas
    históricas ficavam em 0% para sempre. O tempo restante agora é repartido."""
    r = make_runner(tmp_path, FakeClient())
    f = r.fatias_cargas_longas(3000)
    assert set(f) == {"atas_varredura", "backfill_contratacoes", "backfill_contratos"}
    assert abs(sum(f.values()) - 3000) < 1e-6
    assert f["backfill_contratacoes"] > 0 and f["backfill_contratos"] > 0
    assert r.fatias_cargas_longas(-5)["atas_varredura"] == 0
