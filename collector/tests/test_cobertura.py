"""Cobertura: edital genérico de TI de valor alto, retomada do snapshot de propostas e
varredura por órgão (caso real: Pregão 131/2026 da Embrapa, switches só nos itens)."""
import time

from radar.pipeline import Runner, carregar_orgaos, export_site
from test_store_pipeline import CONFIG, TI_COMPRA, FakeClient

EMBRAPA = dict(TI_COMPRA,
               numeroControlePNCP="00348003000110-1-001574/2026", sequencialCompra=1574,
               orgaoEntidade={"cnpj": "00348003000110", "razaoSocial": "EMPRESA BRASILEIRA DE PESQUISA AGROPECUARIA",
                              "esferaId": "F"},
               objetoCompra="Contratação de empresa, mediante Ata de Registro de Preço, para o fornecimento de "
                            "equipamentos de informatica, todos com garantia de funcionamento on-site por 60 meses",
               informacaoComplementar=None, valorTotalEstimado=91_327_199.99)


class ClienteEmbrapa(FakeClient):
    def compra_itens(self, *a, **k):
        return [{"numeroItem": 5, "descricao": "Switch 24 portas Catalyst C1200 com suporte técnico 24x7 e garantia on-site",
                 "quantidade": 40, "valorTotal": 1_165_856.92, "orcamentoSigiloso": False}]


def runner(tmp_path, client, budget=5):
    r = Runner(tmp_path, CONFIG, budget_min=budget, backfill=False)
    r.client = client
    return r


def test_objeto_generico_de_valor_alto_entra_pelos_itens(tmp_path):
    r = runner(tmp_path, ClienteEmbrapa(compras=[EMBRAPA]))
    r.orgaos_relevantes = []                     # só o caminho "valor alto"
    r.run()
    it = r.store.items["00348003000110-1-001574/2026"]
    assert it["candidato_itens"] == "valor alto"
    assert it["itens"] and it["classificacao"]["tls"] and it["publicado_em"]
    n = export_site(tmp_path, tmp_path / "site", CONFIG, ofertas=r.ofertas)
    assert n["oportunidades"] == 1


def test_objeto_generico_de_valor_baixo_fica_fora_salvo_orgao_relevante(tmp_path):
    barato = dict(EMBRAPA, valorTotalEstimado=300_000.0)
    r = runner(tmp_path, ClienteEmbrapa(compras=[barato]))
    r.orgaos_relevantes = []
    r.run()
    assert not r.store.items                     # R$ 300 mil, objeto genérico, órgão fora da lista
    r2 = runner(tmp_path / "b", ClienteEmbrapa(compras=[barato]))
    r2.orgaos_relevantes = [{"cnpj": "00348003000110", "nome": "Embrapa"}]
    r2.run()
    it = r2.store.items["00348003000110-1-001574/2026"]
    assert it["candidato_itens"] == "órgão relevante" and it["classificacao"]["tls"]


def test_objeto_sem_ti_nao_vira_candidato(tmp_path):
    obra = dict(EMBRAPA, objetoCompra="Reforma predial do edifício sede", valorTotalEstimado=50_000_000.0)
    r = runner(tmp_path, ClienteEmbrapa(compras=[obra]))
    r.orgaos_relevantes = [{"cnpj": "00348003000110", "nome": "Embrapa"}]
    r.run()
    assert not r.store.items


def test_enriquecimento_prioriza_propostas_abertas_de_maior_valor(tmp_path):
    ordem = []

    class C(ClienteEmbrapa):
        def compra_itens(self, cnpj, ano, seq, **k):
            ordem.append(seq)
            return super().compra_itens()
    compras = [dict(EMBRAPA, numeroControlePNCP=f"00348003000110-1-00{n}/2026", sequencialCompra=n,
                    valorTotalEstimado=v) for n, v in ((1001, 2_000_000.0), (1002, 90_000_000.0), (1003, 5_000_000.0))]
    r = runner(tmp_path, C(compras=compras))
    r.orgaos_relevantes = []
    r.run()
    assert ordem[:3] == [1002, 1003, 1001]


class ClientePaginado(FakeClient):
    """Snapshot de propostas com N páginas; registra as páginas pedidas."""

    def __init__(self, paginas, **kw):
        super().__init__(**kw)
        self.paginas, self.pedidas = paginas, []

    def contratacoes_proposta(self, d, start_page=1, **kw):
        if kw.get("cnpj"):
            return iter(())
        def gen():
            for p in range(start_page, self.paginas + 1):
                self.pedidas.append(p)
                yield []
        return gen()


def test_snapshot_de_propostas_continua_de_onde_parou(tmp_path):
    c = ClientePaginado(30)
    r = runner(tmp_path, c)
    r._feed_deadline = lambda name: time.monotonic() + 3600
    # 1ª execução: o tempo acaba depois de 12 páginas
    r.time_left_for_bulk = lambda: 10_000 if len(c.pedidas) < 12 else 0
    r.feed_propostas_abertas()
    st = r.store.state["propostas_abertas"]
    assert st["pagina"] == 13 and "ultimo_snapshot" not in st
    assert r.sources["propostas_abertas"]["status"] == "parcial"
    assert "continua" in r.sources["propostas_abertas"]["erro"]

    # 2ª execução: recomeça 3 páginas antes (sobreposição) e termina
    r2 = runner(tmp_path, c)
    r2.store.state = r.store.state
    c.pedidas.clear()
    r2.feed_propostas_abertas()
    assert c.pedidas[0] == 10 and c.pedidas[-1] == 30
    st = r2.store.state["propostas_abertas"]
    assert "pagina" not in st and st["ultimo_snapshot"]
    assert r2.sources["propostas_abertas"]["status"] == "ok"


def test_varredura_por_orgao_retoma_do_proximo_orgao(tmp_path):
    pedidos = []

    class C(FakeClient):
        def contratacoes_proposta(self, d, start_page=1, **kw):
            pedidos.append(kw.get("cnpj"))
            return iter(())
    r = runner(tmp_path, C())
    r.cfg["pncp"]["orgaos_paralelo"] = 1          # sequencial: ordem dos pedidos determinística
    r.orgaos_relevantes = [{"cnpj": f"{i:014d}", "nome": str(i)} for i in range(1, 6)]
    r.time_left_for_bulk = lambda: 10_000 if len(pedidos) < 3 else 0
    r.feed_orgaos_relevantes()
    assert pedidos == ["00000000000001", "00000000000002", "00000000000003"]
    assert r.store.state["orgaos_relevantes"]["proximo"] == 3
    pedidos.clear()
    r.time_left_for_bulk = lambda: 10_000
    r.feed_orgaos_relevantes()
    assert pedidos == ["00000000000004", "00000000000005", "00000000000001", "00000000000002", "00000000000003"]
    assert r.store.state["orgaos_relevantes"]["proximo"] == 0


def test_lista_de_orgaos_relevantes_valida_e_sem_repetidos():
    orgaos = carregar_orgaos(CONFIG, "orgaos_relevantes.yml")
    cnpjs = [o["cnpj"] for o in orgaos]
    assert len(orgaos) >= 100 and len(cnpjs) == len(set(cnpjs))
    assert all(len(c) == 14 and c.isdigit() for c in cnpjs)
    assert "00348003000110" in cnpjs            # Embrapa


def _compra_do_orgao(cnpj, seq):
    return dict(EMBRAPA, numeroControlePNCP=f"{cnpj}-1-{seq:06d}/2026", sequencialCompra=seq,
                orgaoEntidade=dict(EMBRAPA["orgaoEntidade"], cnpj=cnpj))


def test_varredura_por_orgao_em_paralelo_grava_na_ordem_e_segue_apos_erro(tmp_path):
    from radar.pncp import SourceError

    class C(ClienteEmbrapa):
        def contratacoes_proposta(self, d, start_page=1, **kw):
            cnpj = kw["cnpj"]
            time.sleep(0.2)                       # PNCP lento: o paralelismo é que dá o ritmo
            if cnpj.endswith("3"):
                raise SourceError("HTTP 500", status=500)
            return iter([[_compra_do_orgao(cnpj, int(cnpj[-1]))]])
    r = runner(tmp_path, C(compras=[]))
    r.cfg["pncp"]["orgaos_paralelo"] = 4
    r.orgaos_relevantes = [{"cnpj": f"{i:014d}", "nome": str(i)} for i in range(1, 9)]
    ordem = []
    original = r.ingest_contratacao
    r.ingest_contratacao = lambda rec, *a, **k: (ordem.append(rec["orgaoEntidade"]["cnpj"]), original(rec, *a, **k))[1]
    t0 = time.monotonic()
    r.feed_orgaos_relevantes()
    assert time.monotonic() - t0 < 8 * 0.2 * 0.6          # bem mais rápido que um por um
    assert ordem == [f"{i:014d}" for i in (1, 2, 4, 5, 6, 7, 8)]   # ordem da lista; o 3 falhou
    rec = r.sources["orgaos_relevantes"]
    assert rec["orgaos"] == 8 and rec["status"] == "parcial" and "1 com erro" in rec["erro"]
    assert r.store.state["orgaos_relevantes"]["proximo_cnpj"] == "00000000000001"


def test_cursor_da_varredura_segue_o_cnpj_mesmo_se_a_lista_mudar(tmp_path):
    pedidos = []

    class C(FakeClient):
        def contratacoes_proposta(self, d, start_page=1, **kw):
            pedidos.append(kw["cnpj"])
            return iter(())
    r = runner(tmp_path, C())
    r.cfg["pncp"]["orgaos_paralelo"] = 1
    r.orgaos_relevantes = [{"cnpj": f"{i:014d}", "nome": str(i)} for i in range(1, 6)]
    r.store.state["orgaos_relevantes"] = {"proximo": 1, "proximo_cnpj": "00000000000004"}
    r.orgaos_relevantes.insert(0, {"cnpj": "00000000000009", "nome": "novo"})   # lista cresceu
    r.time_left_for_bulk = lambda: 10_000 if len(pedidos) < 1 else 0
    r.feed_orgaos_relevantes()
    assert pedidos == ["00000000000004"]


def test_orgaos_da_carteira_que_ja_compram_vem_primeiro(tmp_path, monkeypatch):
    import json
    from radar.store import Store
    st = Store(tmp_path).load()
    st.items["x"] = {"id": "x", "orgao": {"cnpj": "22222222000122"}}
    st.save("2026-11-26T00:00:00-03:00")
    monkeypatch.setenv("RADAR_TERRITORIOS_JSON", json.dumps({"versao": "t", "contas": [
        {"nomes": ["ORGAO A"], "cnpjs": ["11111111000111"], "bsb": "V"},
        {"nomes": ["ORGAO B"], "cnpjs": ["22222222000122"], "bsb": "V"}]}))
    r = Runner(tmp_path, CONFIG, budget_min=5, backfill=False)
    carteira = [o["cnpj"] for o in r.orgaos_relevantes if o.get("grupo") == "Carteira (territórios)"]
    assert carteira == ["22222222000122", "11111111000111"]
