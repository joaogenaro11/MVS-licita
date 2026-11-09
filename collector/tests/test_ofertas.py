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
    assert r["aderencia"] == 50 and r["faixa"] == "media" and r["via"] == "oferta"
    r = base.classificar(["Contratação de suporte Cisco"])
    assert ids(r) == ["sint_suporte_cisco"] and r["pontuacao"] == 4.5         # alta: 3 x 1,5
    assert r["ofertas_casadas"][0]["via"] == "termo_exato"


def test_marca_mais_servico_no_mesmo_texto_vale_2(base):
    r = base.classificar(["Manutenção de switches Catalyst"])
    assert ids(r) == ["sint_suporte_cisco"] and r["pontuacao"] == 3           # 2 x 1,5
    assert r["ofertas_casadas"][0]["via"] == "marca_servico"
    # marca e serviço em textos diferentes (objeto x item) não casam
    assert not base.classificar(["Licenças Catalyst", "Serviço de manutenção predial"])["tls"]


def test_so_marca_nao_classifica_mas_fica_como_sinal(base):
    r = base.classificar(["Equipamentos Cisco para o auditório"])
    assert not r["tls"] and r["pontuacao"] == 0 and "Cisco" in r["sinais"]


def test_oferta_sem_termos_servico_so_casa_por_termo_exato(base):
    assert not base.classificar(["Suporte técnico e manutenção Meraki"])["tls"]   # sint_rede_sem_fio não tem serviços


def test_excluir_da_oferta_impede_o_casamento(base):
    assert not base.classificar(["Curso de suporte técnico em Cisco"])["tls"]


def test_soma_das_ofertas_casadas_com_bonus_de_duas_familias(base):
    r = base.classificar(["Manutenção de mainframe e suporte Cisco"])
    assert set(ids(r)) == {"sint_mainframe", "sint_suporte_cisco"}
    # (3 + 3) x 1,5 (oferta principal de prioridade alta) + 1 (duas famílias) = 10 -> aderência 100
    assert r["pontuacao"] == 10 and r["aderencia"] == 100 and r["faixa"] == "alta"
    assert r["familias"] == ["networking", "ibm_logo"]          # empate de peso -> menor 'ordem'


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


# ------------------------------------------------------------- rev. c: famílias e aderência
def test_caminho_familia_quando_nenhuma_oferta_casa(base):
    r = base.classificar(["Manutenção preventiva de equipamentos de rede (switches e roteadores)"])
    assert r["tls"] and r["via"] == "familia" and ids(r) == []
    assert r["familias"] == ["networking"] and r["familia_principal"] == "networking"
    assert r["pontuacao"] == 3 and r["aderencia"] == 50 and r["faixa"] == "media"   # 2 x 1,5 (família alta)
    assert r["portfolio"] == ["mvs"]
    assert {"switches", "manutenção"} <= set(r["termos"])


def test_caminho_familia_so_se_nenhuma_oferta_casou(base):
    r = base.classificar(["Suporte Cisco e manutenção de switches"])
    assert r["via"] == "oferta" and r["familias_casadas"] == []


def test_caminho_familia_exige_categoria_e_servico_no_mesmo_texto_e_respeita_excluir(base):
    assert base.classificar(["Aquisição de switches"])["tls"]                  # categoria + serviço: casa
    assert not base.classificar(["Switches de rede", "manutenção predial"])["tls"]
    assert not base.classificar(["Manutenção da rede elétrica e switches"])["tls"]
    assert not base.classificar(["Capacitação de servidores públicos em switches e manutenção"])["tls"]


def test_familia_ibm_vai_para_logo_e_media_prioridade_nao_multiplica(base):
    r = base.classificar(["Suporte técnico da plataforma alta (computador de grande porte)"])
    assert r["familias"] == ["ibm_logo"] and r["portfolio"] == ["logo"]
    assert r["pontuacao"] == 2 and r["aderencia"] == 33 and r["faixa"] == "baixa"


def test_duas_familias_pelo_caminho_c_somam_e_ganham_bonus(base):
    r = base.classificar(["Aquisição de firewall e de switches"])
    assert r["familias"] == ["networking", "seguranca"]                      # mesmo peso -> ordem
    assert r["pontuacao"] == (2 + 2) * 1.5 + 1 and r["aderencia"] == 100


def test_marca_no_texto_acrescenta_portfolio_no_caminho_de_familia(base):
    r = base.classificar(["Aquisição de switches para o ambiente mainframe"])
    assert r["via"] == "familia" and r["portfolio"] == ["logo", "mvs"]


def test_faixas_de_aderencia():
    from radar.ofertas import aderencia_de
    assert aderencia_de(6) == (100, "alta") and aderencia_de(4.2) == (70, "alta")
    assert aderencia_de(4.1) == (68, "media") and aderencia_de(2.4) == (40, "media")
    assert aderencia_de(2.3) == (38, "baixa") and aderencia_de(20) == (100, "alta")


def test_resumo_publico_traz_familias_em_ordem(base):
    r = base.resumo_publico()
    assert [f["id"] for f in r["familias"]][:3] == ["networking", "seguranca", "servidores_storage"]
    assert r["ofertas"]["sint_mainframe"]["familia"] == "ibm_logo"


def test_oferta_com_familia_inexistente_falha(tmp_path):
    d = json.loads(FIXTURE_OFERTAS.read_text())
    d["ofertas"][0]["familia"] = "nao_existe"
    with pytest.raises(OfertasError, match="família inexistente"):
        BaseOfertas.from_dict(d)
