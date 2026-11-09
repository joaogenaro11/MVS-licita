"""Regras de casamento da base de ofertas (regras_de_match), sobre a base SINTÉTICA."""
import json

import pytest

from conftest import FIXTURE_OFERTAS
from radar.ofertas import SELO_FALSO_POSITIVO, BaseOfertas, OfertasError, norm, portfolio_label


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


def test_termo_exato_forca_1_e_fator_de_prioridade(base):
    r = base.classificar(["Pontos de acesso para o prédio"])
    assert ids(r) == ["sint_rede_sem_fio"] and r["via"] == "oferta"
    assert r["componentes"]["portfolio"] == 31.5                               # 35 x 1,0 x 0,9 (média)
    r = base.classificar(["Contratação de suporte Cisco"])
    assert ids(r) == ["sint_suporte_cisco"] and r["componentes"]["portfolio"] == 35   # alta: x 1,0
    assert r["ofertas_casadas"][0]["via"] == "termo_exato"


def test_marca_mais_servico_no_mesmo_texto_vale_2(base):
    r = base.classificar(["Manutenção de switches Catalyst"])
    assert ids(r) == ["sint_suporte_cisco"] and r["componentes"]["portfolio"] == 31.5   # 35 x 0,9 x 1,0
    assert r["ofertas_casadas"][0]["via"] == "marca_servico"
    # marca e serviço em textos diferentes (objeto x item) não casam
    assert not base.classificar(["Licenças Catalyst", "Serviço de manutenção predial"])["tls"]


def test_so_marca_nao_classifica_mas_fica_como_sinal(base):
    r = base.classificar(["Equipamentos Cisco para o auditório"])
    assert not r["tls"] and r["score"] is None and r["faixa"] is None and "Cisco" in r["sinais"]


def test_oferta_sem_termos_servico_so_casa_por_termo_exato(base):
    assert not base.classificar(["Suporte técnico e manutenção Meraki"])["tls"]   # sint_rede_sem_fio não tem serviços


def test_excluir_da_oferta_impede_o_casamento(base):
    assert not base.classificar(["Curso de suporte técnico em Cisco"])["tls"]


def test_varias_ofertas_casadas_e_familia_principal(base):
    r = base.classificar(["Manutenção de mainframe e suporte Cisco"])
    assert set(ids(r)) == {"sint_mainframe", "sint_suporte_cisco"}
    assert r["familias"] == ["networking", "ibm_logo"]          # mesma força -> menor 'ordem'


def test_exclusao_global_limita_a_nota_e_gera_selo(base):
    r = base.classificar(["Aquisição de notebooks e suporte técnico Cisco 24x7"], estagio="propostas_abertas", valor=9e6)
    assert r["tls"] and r["score"] == 45                         # teto exclusao_global
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


def test_oferta_indisponivel_no_brasil_nao_gera_selo(base):
    # disponivel_brasil = "nao" fica no JSON só como informação
    r = base.classificar(["Serviço de sanitização de dados de discos"])
    assert r["tls"] and r["portfolio"] == ["transversal"] and r["selos"] == []


def test_nenhuma_oferta_nao_e_oportunidade(base):
    r = base.classificar(["Aquisição de mobiliário de escritório"])
    assert r == {**r, "tls": False, "ofertas_casadas": [], "portfolio": [], "score": None}


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
    assert r["componentes"]["portfolio"] == 21 and r["score"] <= 69   # 35 x 0,6 (família alta); teto só família
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
    assert r["componentes"]["portfolio"] == 18.9                              # 35 x 0,6 x 0,9 (média)


def test_duas_familias_pelo_caminho_c_somam_e_ganham_bonus(base):
    r = base.classificar(["Aquisição de firewall e de switches"])
    assert r["familias"] == ["networking", "seguranca"]                      # mesma força -> ordem


def test_marca_no_texto_acrescenta_portfolio_no_caminho_de_familia(base):
    r = base.classificar(["Aquisição de switches para o ambiente mainframe"])
    assert r["via"] == "familia" and r["portfolio"] == ["logo", "mvs"]


def test_faixas_da_nota(base):
    f = base.pontuacao.faixa
    assert [f(n) for n in (100, 80, 79, 60, 59, 40, 39, 0)] == [
        "alta", "alta", "analisar", "analisar", "indireto", "indireto", "baixa", "baixa"]


# ------------------------------------------------------------- nota (modelo da versão anterior)
def test_nota_completa_suporte_cisco_propostas_abertas(base):
    r = base.classificar(["Contratação de serviços de suporte técnico e manutenção corretiva on-site de switches Cisco"],
                         estagio="propostas_abertas")
    c = r["componentes"]
    # portfólio 35 x 0,9 (marca + serviço, alta) · suporte 25 (saturou) · fabricante 15 (aliança) · valor 10 x 0,3
    # (sem valor) · estágio 10 · evidências 5 x 3/5 (oferta forte, suporte, marca) = 87,5
    assert (c["portfolio"], c["suporte"], c["fabricante"], c["valor"], c["estagio"], c["evidencias"]) == (31.5, 25, 15, 3, 10, 3)
    assert r["score"] == 88 and r["faixa"] == "alta" and r["relacao"] == "direta" and not r["via_parceiro"]
    assert r["score_tecnico"] == 93 and r["score_comercial"] == 65


def test_suporte_termo_longo_consome_o_curto_e_satura(base):
    _, termos, _ = base.pontuacao.suporte(norm("manutenção corretiva"))
    assert termos == ["manutenção corretiva"]                  # "manutenção" não conta de novo
    forca, _, _ = base.pontuacao.suporte(norm("garantia"))
    assert forca == 0.5
    r = base.classificar(["Suporte Cisco com garantia"])
    assert r["componentes"]["suporte"] == round(25 * 1.0 / 1.5, 1)   # suporte (0,5) + garantia (0,5)


def test_so_aquisicao_vale_0_3_e_e_oportunidade_indireta(base):
    r = base.classificar(["Aquisição de switches Catalyst"])
    assert r["componentes"]["suporte"] == 7.5 and r["relacao"] == "indireta" and r["via_parceiro"]
    assert "Oportunidade indireta" in r["justificativa"]


def test_fabricante_alianca_outras_e_nenhum(base):
    assert base.classificar(["Suporte Cisco"])["componentes"]["fabricante"] == 15
    assert base.classificar(["Manutenção de storage HP"])["componentes"]["fabricante"] == 12   # outra marca: 0,8
    assert base.classificar(["Projeto de rede do campus"])["componentes"]["fabricante"] == 0


def test_valor_estagio_e_itens_tornam_a_nota_continua(base):
    t = ["Manutenção de switches Catalyst"]
    notas = {base.classificar(t, estagio=e, valor=v, tem_itens=i)["score"]
             for e in (None, "julgamento", "propostas_abertas") for v in (None, 50e3, 2e6, 9e6) for i in (False, True)}
    assert len(notas) >= 10
    assert base.classificar(t, valor=9e6)["score"] > base.classificar(t, valor=50e3)["score"]
    assert base.classificar(t, estagio="propostas_abertas")["score"] > base.classificar(t, estagio="encerrada")["score"]


def test_teto_so_familia(base):
    r = base.classificar(["Manutenção preventiva e suporte técnico 24x7 de switches Cisco Catalyst do data center, on-site",
                          "Aquisição de switches com garantia"], estagio="propostas_abertas", valor=9e6)
    assert r["via"] == "oferta"
    r = base.classificar(["Manutenção preventiva e suporte técnico 24x7 on-site de switches e roteadores"],
                         estagio="propostas_abertas", valor=9e6, tem_itens=True)
    assert r["via"] == "familia" and r["score"] == 69


def test_justificativa_so_com_termos_encontrados(base):
    r = base.classificar(["Contratação de suporte técnico Cisco 24x7"])
    j = r["justificativa"]
    assert j.startswith("Possível aderência a Suporte de rede Cisco (sintético)")
    assert "“suporte técnico”" in j and "“24x7”" in j and "fabricante(s): Cisco" in j
    assert "garantia" not in j and "Oportunidade indireta" not in j


def test_base_sem_bloco_pontuacao_falha(tmp_path):
    d = json.loads(FIXTURE_OFERTAS.read_text())
    del d["pontuacao"]
    with pytest.raises(OfertasError, match="pontuacao"):
        BaseOfertas.from_dict(d)
    d = json.loads(FIXTURE_OFERTAS.read_text())
    del d["pontuacao"]["pesos"]["suporte"]
    with pytest.raises(OfertasError, match="pesos.suporte"):
        BaseOfertas.from_dict(d)


def test_resumo_publico_traz_familias_em_ordem(base):
    r = base.resumo_publico()
    assert [f["id"] for f in r["familias"]][:3] == ["networking", "seguranca", "servidores_storage"]
    assert r["ofertas"]["sint_mainframe"]["familia"] == "ibm_logo"


def test_oferta_com_familia_inexistente_falha(tmp_path):
    d = json.loads(FIXTURE_OFERTAS.read_text())
    d["ofertas"][0]["familia"] = "nao_existe"
    with pytest.raises(OfertasError, match="família inexistente"):
        BaseOfertas.from_dict(d)



# ------------------------------------------------------- rev. d: excluir por registro no PCA
from radar.pipeline import classificar_registro  # noqa: E402


def _pca(objeto, info):
    return {"tipo": "pca", "objeto": objeto, "info_complementar": info}


def test_pca_avalia_ficha_e_classe_juntas_para_excluir(base):
    r = classificar_registro(base, _pca("QUANTIDADE PORTAS: 8, TIPO: NÃO GERENCIÁVEL",
                                        "SWITCH | Material | EQUIPAMENTOS DE REDE DE TIC - LOCAL E REMOTA | Aquisição de switch"))
    assert not r["tls"]
    r = classificar_registro(base, _pca("TIPO: SERVER SWITCH, 2 CONSOLES",
                                        "CHAVEADORA | Material | EQUIPAMENTOS DE REDE DE TIC | Aquisição de Switch chaveador KVM"))
    assert not r["tls"]


def test_pca_switch_de_rede_continua_networking(base):
    r = classificar_registro(base, _pca("QUANTIDADE PORTAS: 48, TIPO PORTAS: 1000 BASE T, SLOTS SFP+",
                                        "SWITCH | Material | EQUIPAMENTOS DE REDE DE TIC | Aquisição de switches de rede"))
    assert r["tls"] and r["familia_principal"] == "networking"


def test_contratacao_com_lotes_mistos_continua_texto_a_texto(base):
    rec = {"tipo": "contratacao", "objeto": "Aquisição de equipamentos de informática",
           "itens": [{"descricao": "Notebook"}, {"descricao": "Switch gerenciável 48 portas com garantia"}]}
    r = classificar_registro(base, rec)
    assert r["tls"] and r["familia_principal"] == "networking"
