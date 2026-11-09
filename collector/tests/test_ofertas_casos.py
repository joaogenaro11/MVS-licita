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


@pytest.mark.parametrize("texto,portfolio,ofertas", CASOS, ids=[c[0][:50] for c in CASOS])
def test_caso_de_aceite(texto, portfolio, ofertas):
    r = BASE.classificar([texto])
    casadas = {o["id"] for o in r["ofertas_casadas"]}
    if not ofertas:
        assert not r["tls"] and not casadas, f"não deveria casar: {casadas}"
        return
    assert r["portfolio"] == portfolio
    assert ofertas <= casadas, f"faltando {ofertas - casadas}; casou {casadas}"
