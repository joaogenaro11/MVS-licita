"""Regras de casamento da base de ofertas (regras_de_match), sobre a base SINTÉTICA."""
import json

import pytest

from conftest import FIXTURE_OFERTAS
from radar.ofertas import (SELO_FALSO_POSITIVO, SELO_INDISPONIVEL, BaseOfertas, OfertasError, norm,
                           portfolio_label)


@pytest.fixture(scope="module")
def base():
    return BaseOfertas.load(FIXTURE_OFERTAS)


def ids(r):
    return [o["id"] for o in r["ofertas_casadas"]]


def test_normalizacao_sem_acento_minusculas_e_pontuacao():
    assert norm("Manutenção  TÉCNICA/24x7") == "manutencao tecnica 24x7"
    assert norm("Wi-Fi 6E") == "wi fi 6e"


def test_palavra_inteira_nunca_pedaco(base):
    assert not base.classificar(["Serviços de limpeza na rua São Francisco com manutenção"])["tls"]   # Cisco ≠ Francisco
    assert not base.classificar(["Cluster HPC com manutenção preventiva"])["tls"]                      # HP ≠ HPC
    assert ids(base.classificar(["Manutenção de storage HP"])) == ["sint_storage_hp"]


def test_termo_exato_vale_3_e_prioridade_alta_multiplica(base):
    r = base.classificar(["Pontos de acesso para o prédio"])
    assert ids(r) == ["sint_rede_sem_fio"] and r["pontuacao"] == 3            # média: sem multiplicador
    r = base.classificar(["Contratação de suporte Cisco"])
    assert ids(r) == ["sint_suporte_cisco"] and r["pontuacao"] == 4.5         # alta: 3 x 1,5
    assert r["ofertas_casadas"][0]["via"] == "termo_exato"


def test_marca_mais_servico_no_mesmo_texto_vale_2(base):
    r = base.classificar(["Manutenção de switches Catalyst"])
    assert ids(r) == ["sint_suporte_cisco"] and r["pontuacao"] == 3           # 2 x 1,5
    assert r["ofertas_casadas"][0]["via"] == "marca_servico"
    # marca e serviço em textos diferentes (objeto x item) não casam
    assert not base.classificar(["Aquisição de switches Catalyst", "Serviço de manutenção predial"])["tls"]


def test_so_marca_nao_classifica_mas_fica_como_sinal(base):
    r = base.classificar(["Aquisição de switches Cisco"])
    assert not r["tls"] and r["pontuacao"] == 0 and "Cisco" in r["sinais"]


def test_oferta_sem_termos_servico_so_casa_por_termo_exato(base):
    assert not base.classificar(["Suporte técnico e manutenção Meraki"])["tls"]   # sint_rede_sem_fio não tem serviços


def test_excluir_da_oferta_impede_o_casamento(base):
    assert not base.classificar(["Curso de suporte técnico em Cisco"])["tls"]


def test_soma_das_ofertas_casadas(base):
    r = base.classificar(["Manutenção de mainframe e suporte Cisco"])
    assert set(ids(r)) == {"sint_mainframe", "sint_suporte_cisco"}
    assert r["pontuacao"] == 9                                                 # 4,5 + 4,5


def test_exclusao_global_reduz_pela_metade_e_gera_selo(base):
    r = base.classificar(["Aquisição de notebooks e suporte Cisco"])
    assert r["tls"] and r["pontuacao"] == 2.25
    assert r["selos"][0]["texto"] == SELO_FALSO_POSITIVO and "notebooks" in r["selos"][0]["detalhe"]


def test_portfolio_logo_mvs_ambos_e_transversal(base):
    assert base.classificar(["Manutenção de mainframe"])["portfolio"] == ["logo"]
    assert base.classificar(["Suporte Cisco"])["portfolio"] == ["mvs"]
    # casou oferta MVS e o texto cita marca Logo -> ambos
    assert base.classificar(["Suporte Cisco no ambiente de mainframe"])["portfolio"] == ["logo", "mvs"]
    # só oferta transversal, sem marca -> transversal
    assert base.classificar(["Projeto de rede do campus"])["portfolio"] == ["transversal"]
    # transversal + marca MVS no texto -> mvs
    assert base.classificar(["Projeto de rede com equipamentos Brocade"])["portfolio"] == ["mvs"]
    assert portfolio_label(["logo", "mvs"]) == "Logo IBM + MVS"


def test_oferta_indisponivel_no_brasil_gera_selo_com_alternativa(base):
    r = base.classificar(["Serviço de sanitização de dados de discos"])
    assert r["tls"] and r["portfolio"] == ["transversal"]
    selo = [s for s in r["selos"] if s["tipo"] == "indisponivel_brasil"][0]
    assert selo["texto"] == SELO_INDISPONIVEL and "alternativa sintética Y" in selo["detalhe"]


def test_nenhuma_oferta_nao_e_oportunidade(base):
    r = base.classificar(["Aquisição de mobiliário de escritório"])
    assert r == {**r, "tls": False, "ofertas_casadas": [], "portfolio": [], "pontuacao": 0}


def test_termos_que_casaram_sao_guardados(base):
    r = base.classificar(["Contratação de suporte técnico e manutenção da rede SDN Cisco ACI, 24x7"])
    assert {"Cisco ACI", "Cisco", "suporte técnico", "24x7"} <= set(r["termos"])
    assert r["ofertas"] == ["Suporte de rede Cisco (sintético)"]


def test_prefiltro_contem_termos_exatos_e_marcas(base):
    rx = base.prefiltro()
    assert rx.search(norm("Aquisição de switches Catalyst"))
    assert rx.search(norm("manutenção de mainframe"))
    assert not rx.search(norm("Rua São Francisco"))


def test_base_invalida_falha_com_mensagem_clara(tmp_path):
    d = json.loads(FIXTURE_OFERTAS.read_text())
    del d["marcas_mvs"]
    with pytest.raises(OfertasError, match="marcas_mvs"):
        BaseOfertas.from_dict(d)
    d = json.loads(FIXTURE_OFERTAS.read_text())
    d["ofertas"][1]["id"] = d["ofertas"][0]["id"]
    with pytest.raises(OfertasError, match="duplicado"):
        BaseOfertas.from_dict(d)
