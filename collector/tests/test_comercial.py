"""Atestados (atende / próximo) e territórios por vendedor — com bases SINTÉTICAS.

As bases reais são privadas (Supabase, tabela radar_bases). Os testes com elas só verificam a
estrutura e casos neutros, para não expor o conteúdo no log público do CI.
"""
import os

import pytest

from radar.comercial import BaseAtestados, BaseTerritorios, chave
from radar.pipeline import aplicar_comercial

SERV = ["manutenção", "suporte técnico", "assistência técnica"]
ATESTADOS = {
    "versao": "teste",
    "atestados": [
        {"id": "otico", "titulo": "Exemplo — transporte óptico", "tipo": "Atestado", "emissor": "Cliente A", "titular": "Empresa",
         "atende": [[["DWDM", "transporte óptico"]]],
         "proximo": [[["rede óptica", "CWDM"]]]},
        {"id": "servidores", "titulo": "Exemplo — manutenção de servidores rack", "tipo": "Atestado", "emissor": "Cliente B", "titular": "Parceiro",
         "atende": [[["servidores rack", "PowerEdge"], SERV]],
         "proximo": [[["servidores", "servidor"], SERV]]},
    ],
}
TERRITORIOS = {
    "versao": "teste",
    "contas": [
        {"nomes": ["MINISTERIO DO EXEMPLO"], "uf": "DF", "bsb": "Vendedor A", "renovacao": "Renovação X", "cnpjs": ["00000000000191"]},
        {"nomes": ["SECRETARIA DE ESTADO DA SAUDE"], "uf": "ES", "bsb": "Vendedor B", "renovacao": None, "cnpjs": []},
        {"nomes": ["SECRETARIA DE ESTADO DA SAUDE"], "uf": "MG", "bsb": "Vendedor C", "renovacao": None, "cnpjs": []},
        {"nomes": ["UNIVERSIDADE FEDERAL DO EXEMPLO - CENTRO DE PROCESS"], "uf": "SP", "bsb": "Vendedor A", "renovacao": None, "cnpjs": []},
    ],
}


@pytest.fixture
def at():
    return BaseAtestados.from_dict(ATESTADOS)


@pytest.fixture
def te():
    return BaseTerritorios.from_dict(TERRITORIOS)


def test_atende_exige_todos_os_grupos_no_mesmo_texto(at):
    r = at.avaliar(["Manutenção corretiva de servidores rack do datacenter"])
    assert r["nivel"] == "atende"
    assert [a["id"] for a in r["lista"]] == ["servidores"]
    # marca num item e serviço em outro não comprova o atestado
    r = at.avaliar(["Servidores PowerEdge", "Serviço de manutenção predial"])
    assert r["nivel"] is None


def test_proximo_e_melhor_nivel(at):
    assert at.avaliar(["Expansão da rede óptica metropolitana"])["nivel"] == "proximo"
    assert at.avaliar(["Suporte técnico para servidor de arquivos"])["nivel"] == "proximo"
    r = at.avaliar(["Expansão da rede óptica", "Aquisição de solução DWDM"])
    assert r["nivel"] == "atende" and r["lista"][0]["nivel"] == "atende" and "DWDM" in r["lista"][0]["termos"]
    assert at.avaliar(["Aquisição de combustível"])["nivel"] is None
    assert at.avaliar([None, ""])["nivel"] is None


def test_aplicar_comercial_so_avalia_atestado_de_registro_tls(at, te):
    rec = {"tipo": "contratacao", "objeto": "Solução DWDM", "orgao": {"cnpj": "00000000000191", "nome": "MINISTERIO DO EXEMPLO"},
           "unidade": {"uf": "DF"}, "itens": [{"descricao": "Manutenção de servidores rack"}]}
    c = {"tls": True}
    aplicar_comercial(rec, c, at, te)
    assert c["atestados"]["nivel"] == "atende" and len(c["atestados"]["lista"]) == 2
    assert c["territorio"] == {"bsb": "Vendedor A", "renovacao": "Renovação X", "conta": "MINISTERIO DO EXEMPLO", "uf": "DF", "via": "cnpj"}
    c = {"tls": False}
    aplicar_comercial(rec, c, at, te)
    assert "atestados" not in c and c["territorio"]["bsb"] == "Vendedor A"


def test_territorio_por_nome_desempata_pela_uf(te):
    rec = lambda nome, uf, cnpj=None: {"orgao": {"nome": nome, "cnpj": cnpj}, "unidade": {"uf": uf}}
    assert te.territorio(rec("Secretaria de Estado da Saúde", "ES"))["bsb"] == "Vendedor B"
    assert te.territorio(rec("SECRETARIA DE ESTADO DA SAUDE", "MG"))["bsb"] == "Vendedor C"
    # homônimo em UF sem conta: não arrisca
    assert te.territorio(rec("SECRETARIA DE ESTADO DA SAUDE", "RJ")) is None
    # nome da planilha cortado: casa pelo começo
    t = te.territorio(rec("Universidade Federal do Exemplo - Centro de Processamento de Dados", "SP"))
    assert t["bsb"] == "Vendedor A" and t["via"] == "nome"
    # nomes genéricos não identificam conta
    assert te.territorio(rec("União Federal", "DF")) is None
    assert te.territorio({"orgao": {}, "unidade": {"nome": "MINISTERIO DO EXEMPLO", "uf": "DF"}})["bsb"] == "Vendedor A"


def test_cnpjs_da_carteira_entram_na_varredura(te):
    assert te.cnpjs() == [{"cnpj": "00000000000191", "nome": "MINISTERIO DO EXEMPLO", "grupo": "Carteira (territórios)"}]
    assert chave("Secretaria  de Estado - Saúde") == "SECRETARIADEESTADOSAUDE"


def _real(cls):
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")) and not os.environ.get("RADAR_ATESTADOS_FILE"):
        return None
    try:
        return cls.load()
    except Exception:  # noqa: BLE001
        return None


@pytest.mark.skipif(_real(BaseAtestados) is None, reason="base de atestados real (privada) indisponível neste ambiente")
def test_base_real_de_atestados_bem_formada():
    base = _real(BaseAtestados)
    assert base.versao and len(base.atestados) >= 1
    for a in base.atestados:
        assert a.id and a.titulo and (a.atende or a.proximo)
    assert base.avaliar(["Aquisição de combustível para veículos oficiais"])["nivel"] is None
