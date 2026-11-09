"""Casos de aceite da base de ofertas REAL (ofertas_tls_radar.json, privada).

A base real não fica no repositório público. Este teste a procura em:
  RADAR_OFERTAS_REAL_FILE (caminho) · config/ofertas_tls_radar.json (cópia local, não versionada) ·
  Supabase (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY: no CI, com o secret configurado).
Sem nenhuma delas, o teste é PULADO e o motivo aparece na saída do pytest.
"""
import json
import os
from pathlib import Path

import pytest

from radar.ofertas import LOCAL_FILE, BaseOfertas


def _base_real():
    fp = os.environ.get("RADAR_OFERTAS_REAL_FILE")
    if fp:
        return BaseOfertas.load(fp)
    if LOCAL_FILE.exists():
        return BaseOfertas.load(LOCAL_FILE)
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        from radar.supa import fetch_ofertas
        d = fetch_ofertas()
        return BaseOfertas.from_dict(d, "supabase") if d else None
    return None


BASE = _base_real()
pytestmark = pytest.mark.skipif(BASE is None, reason="base de ofertas real (privada) indisponível neste ambiente")

# (texto, portfólio esperado, ofertas que devem estar entre as casadas)
CASOS = [
    ("Contratação de serviços de suporte técnico e manutenção da rede SDN Cisco ACI, 24x7, tempo máximo de solução de 4 horas",
     ["mvs"], {"mms_cisco", "cisco_sdn_impl"}),
    ("Aquisição de pontos de acesso Wi-Fi 6E e controladora wireless", ["mvs"], {"cisco_resell"}),
    ("Manutenção de firewall Fortinet FortiGate com suporte 24x7", ["mvs"], {"mms_fortinet"}),
    ("Aquisição de notebooks Lenovo para servidores do órgão", [], set()),
    ("Serviços de limpeza no prédio da rua São Francisco", [], set()),
    ("Licença Power BI Pro", [], set()),
    ("Assessoria de Controle Interno (ACI) – capacitação", [], set()),
    ("Renovação de garantia e suporte do mainframe IBM z16 e storage DS8000", ["logo"], {"hwma"}),
    ("Extensão de suporte para switches SAN Brocade do ambiente de mainframe", ["logo", "mvs"], {"hwse", "mms_san_brocade"}),
    ("Contratação de suporte técnico para ambiente VMware vSphere com licenças perpétuas", ["mvs"], {"support_vmware"}),
    ("Serviço de suporte técnico especializado Microsoft Unified", ["mvs"], {"support_microsoft"}),
    ("Contratação de serviços de sanitização de dados e descarte seguro de discos", ["transversal"], {"data_erasure"}),
]

# rev. c: famílias (texto, família principal esperada, portfólio esperado ou None, faixa esperada ou None)
CASOS_FAMILIA = [
    ("Contratação de serviços de manutenção preventiva e corretiva de equipamentos de rede (switches e roteadores) com "
     "reposição de peças", "networking", None, None),
    ("Aquisição de solução de firewall com garantia de 60 meses", "seguranca", None, "media"),
    ("Renovação de garantia dos servidores de rede do datacenter", "servidores_storage", None, "media"),
    ("Aquisição de servidores rack e storage para modernização do data center", "refresh", None, None),
    ("Contratação de suporte técnico para a plataforma alta (computador de grande porte)", "ibm_logo", ["logo"], None),
]
NADA = [
    "Capacitação de servidores públicos em gestão de redes",
    "Serviço de manutenção da rede elétrica e lógica",
    "Aquisição de notebooks com Wi-Fi",
    "Contratação de fábrica de software",
]


@pytest.mark.parametrize("texto,portfolio,ofertas", CASOS, ids=[c[0][:50] for c in CASOS])
def test_caso_de_aceite(texto, portfolio, ofertas):
    r = BASE.classificar([texto])
    casadas = {o["id"] for o in r["ofertas_casadas"]}
    if not ofertas:
        assert not r["tls"] and not casadas, f"não deveria casar: {casadas}"
        return
    assert r["portfolio"] == portfolio
    assert ofertas <= casadas, f"faltando {ofertas - casadas}; casou {casadas}"


@pytest.mark.skipif(BASE is None or not getattr(BASE, "familias", None), reason="base real sem famílias (rev. c)")
@pytest.mark.parametrize("texto,familia,portfolio,faixa", CASOS_FAMILIA, ids=[c[0][:50] for c in CASOS_FAMILIA])
def test_caso_familia(texto, familia, portfolio, faixa):
    r = BASE.classificar([texto])
    assert r["tls"] and r["familia_principal"] == familia, (r["familias"], [o["id"] for o in r["ofertas_casadas"]])
    if portfolio:
        assert r["portfolio"] == portfolio
    if faixa:
        assert r["faixa"] == faixa, r["aderencia"]


@pytest.mark.parametrize("texto", NADA)
def test_caso_nada(texto):
    r = BASE.classificar([texto])
    assert not r["tls"], (r["familias"], [o["id"] for o in r["ofertas_casadas"]])



# rev. d: excluir avaliado no registro inteiro do PCA (ficha técnica + classe/descrição)
from radar.pipeline import classificar_registro  # noqa: E402

CASOS_REGISTRO = [
    ({"tipo": "pca", "objeto": "QUANTIDADE PORTAS: 8, TIPO: NÃO GERENCIÁVEL",
      "info_complementar": "SWITCH | Material | EQUIPAMENTOS DE REDE DE TIC - LOCAL E REMOTA | Aquisição de switch"}, None),
    ({"tipo": "pca", "objeto": "TIPO: SERVER SWITCH, 2 CONSOLES",
      "info_complementar": "CHAVEADORA | Material | EQUIPAMENTOS DE REDE DE TIC | Aquisição de Switch chaveador KVM"}, None),
    ({"tipo": "pca", "objeto": "QUANTIDADE PORTAS: 48, TIPO PORTAS: 1000 BASE T, SLOTS SFP+",
      "info_complementar": "SWITCH | Material | EQUIPAMENTOS DE REDE DE TIC | Aquisição de switches de rede"}, "networking"),
    ({"tipo": "contratacao", "objeto": "Aquisição de equipamentos de informática",
      "itens": [{"descricao": "Notebook"}, {"descricao": "Switch gerenciável 48 portas com garantia"}]}, "networking"),
]


@pytest.mark.parametrize("rec,familia", CASOS_REGISTRO, ids=["pca_nao_gerenciavel", "pca_kvm", "pca_switch_48", "contratacao_lotes_mistos"])
def test_caso_registro(rec, familia):
    r = classificar_registro(BASE, rec)
    if familia is None:
        assert not r["tls"], (r["familias"], [o["id"] for o in r["ofertas_casadas"]])
    else:
        assert r["tls"] and r["familia_principal"] == familia, (r["familias"], [o["id"] for o in r["ofertas_casadas"]])
