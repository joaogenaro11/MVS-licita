"""Testes do motor de classificação TLS.

Os textos de verdadeiro/falso positivo reproduzem padrões de objetos publicados no
PNCP. Casos reais (com identificador PNCP) ficam em test_casos_reais.py.
"""
from pathlib import Path

import pytest

from radar.classifier import Portfolio, classify, normalize, term_regex

CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture(scope="module")
def pf():
    return Portfolio.load(CONFIG, private="")


def c(pf, text, stage="publicada", value=None, **kw):
    return classify(pf, [text], stage=stage, value=value, **kw)


# ---------------------------------------------------------------- texto
def test_normalize_remove_acentos_e_pontuacao():
    assert normalize("Manutenção  Preventiva; Switches!") == "manutencao preventiva switches"


def test_plural_automatico():
    rx = term_regex("roteador")
    assert rx.search("roteadores de borda")
    rx = term_regex("ponto de acesso sem fio")
    assert rx.search("pontos de acesso sem fio")
    assert term_regex("solucao de armazenamento").search("solucoes de armazenamento")
    assert not term_regex("san").search("sanitizacao")


# ------------------------------------------------------- verdadeiros positivos
@pytest.mark.parametrize("texto,oferta", [
    ("Contratação de serviços de suporte técnico e manutenção preventiva e corretiva de switches e roteadores "
     "Cisco, com atendimento 24x7 e reposição de peças", "Networking"),
    ("Renovação de garantia e suporte do fabricante para appliances de firewall Fortinet (FortiGate)", "Security"),
    ("Prestação de serviços de manutenção de hardware de equipamentos de TIC de múltiplos fabricantes "
     "(servidores, storage e switches) fora de garantia", "MVS — Multivendor"),
    ("Contratação de suporte técnico especializado para solução de armazenamento de dados (storage) NetApp", "Data Center"),
])
def test_alta_aderencia(pf, texto, oferta):
    r = c(pf, texto, stage="propostas_abertas", value=2_000_000)
    assert r["score"] >= 80, r
    assert r["faixa"] == "alta"
    assert oferta in r["ofertas"]
    assert r["relacao"] == "direta"


def test_aquisicao_e_indireta(pf):
    r = c(pf, "Registro de preços para aquisição de switches gerenciáveis e access points com garantia de 60 meses",
          value=800_000)
    assert r["tipo_servico"] == "aquisicao_com_garantia"
    assert r["relacao"] == "indireta"
    assert r["via_parceiro"] is True
    assert "Hardware Refresh" in r["ofertas"]
    assert 40 <= r["score"] < 80


# --------------------------------------------------------- falsos positivos
@pytest.mark.parametrize("texto", [
    "Contratação de empresa para capacitação de servidores públicos da rede municipal de ensino",
    "Prestação de serviços de segurança patrimonial armada e desarmada",
    "Aquisição de suporte para soro e suporte para TV para unidades de saúde",
    "Serviços de manutenção predial preventiva e corretiva",
    "Contratação de serviços de vigilância e rede de proteção para quadras",
    "Ampliação da rede de esgoto e rede de água do município",
    "Aquisição de equipamentos esportivos para uso em espaços públicos",
    "Serviço de manutenção preventiva e corretiva de equipamentos médico-hospitalares",
])
def test_falsos_positivos_ficam_baixos(pf, texto):
    r = c(pf, texto, stage="propostas_abertas", value=50_000_000)
    assert r["score"] < 40, (texto, r)
    assert r["faixa"] == "baixa"


def test_palavras_isoladas_nao_pontuam_alto(pf):
    r = c(pf, "Contratação de suporte para a rede", value=10_000_000)
    assert r["score"] <= 35


def test_valor_alto_nao_compensa_falta_de_aderencia(pf):
    pequeno = c(pf, "Aquisição de microcomputadores e notebooks", value=1_000)
    grande = c(pf, "Aquisição de microcomputadores e notebooks", value=900_000_000)
    assert grande["score"] < 40
    assert grande["score"] - pequeno["score"] <= 3


def test_valor_e_estagio_so_somam_com_aderencia(pf):
    base = "Manutenção corretiva de switches e roteadores com suporte técnico 24x7"
    a = c(pf, base, stage="julgamento", value=10_000_000)
    b = c(pf, base, stage="propostas_abertas", value=10_000_000)
    assert b["score"] > a["score"]
    assert b["score_tecnico"] == a["score_tecnico"]      # estágio é urgência, não aderência
    assert b["score_comercial"] > a["score_comercial"]


def test_servico_generico_de_ti(pf):
    r = c(pf, "Contratação de fábrica de software e service desk")
    assert r["tipo_servico"] in ("servico_ti_generico", "sem_aderencia")
    assert r["score"] < 40


# ------------------------------------------------------------ justificativa
def test_justificativa_cita_apenas_termos_encontrados(pf):
    r = c(pf, "Suporte técnico para switches Cisco")
    j = r["justificativa"]
    assert "switches" in j and "Cisco" in j
    assert "firewall" not in j.lower()
    for ev in r["evidencias"]:
        if ev["categoria"] != "fabricante":
            assert ev["termo"].lower() in "suporte técnico para switches cisco"


def test_sem_evidencia_sem_justificativa_inventada(pf):
    r = c(pf, "Aquisição de gêneros alimentícios")
    assert r["justificativa"].startswith("Sem evidência")
    assert r["ofertas"] == []
    assert r["evidencias"] == []


def test_orgao_nao_entra_na_classificacao(pf):
    # o classificador recebe apenas textos do objeto; nome de órgão "Segurança" não deve contar
    r = c(pf, "Aquisição de material de expediente")
    assert r["score"] < 20


def test_fabricante_com_cobertura_a_validar_gera_alerta(pf):
    r = c(pf, "Suporte e manutenção de switches Huawei")
    assert any("validar" in a for a in r["alertas"])


# ------------------------------------------------------- configuração privada
def test_sobreposicao_privada_aplica_somente_numeros(pf):
    priv = """
vendors:
  Huawei: {tls_coverage: confirmada, note: "texto interno"}
offers:
  networking: {fit_factor: 0.5}
vendor_notes: {Huawei: "segredo"}
priority_orgs: [ORGAO X]
"""
    pf2 = Portfolio.load(CONFIG, private=priv)
    r = classify(pf2, ["Suporte e manutenção de switches Huawei"], stage="publicada")
    assert r["fabricantes"][0]["cobertura"] == "confirmada"
    assert r["fabricantes"][0]["nota"] is None          # nota interna NÃO vaza para os dados
    dump = str(r)
    assert "segredo" not in dump and "texto interno" not in dump and "ORGAO X" not in dump
    assert pf2.raw["offers"]["networking"]["fit_factor"] == 0.5


def test_limiares_configuraveis(pf):
    assert pf.faixa(80) == "alta" and pf.faixa(79) == "analisar"
    assert pf.faixa(59) == "indireto" and pf.faixa(39) == "baixa"
