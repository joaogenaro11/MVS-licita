"""Casos REAIS do PNCP (amostra coletada pelo CI em 04/11/2026, job `source-probe`).

Os textos são trechos do objeto EXATAMENTE como publicados (truncados no log em ~110–260
caracteres) — nada foi acrescentado. Variações sintéticas ficam em test_classifier.py. Servem de regressão do classificador: verdadeiros positivos devem continuar
altos e falsos positivos já observados devem continuar baixos.

ATENÇÃO: são exemplos históricos. Não representam licitações abertas nem atas vigentes
no momento em que você ler este arquivo.
"""
from pathlib import Path

import pytest

from radar.classifier import Portfolio, classify

CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture(scope="module")
def pf():
    return Portfolio.load(CONFIG, private="")


POSITIVOS = [
    ("46377222000129-1-000354/2026",
     "Contratação de serviços de suporte para infraestrutura de rede sem fio no ambiente SEFAZ", "Networking", 60, "direta"),
    ("23274194000119-1-000105/2026",
     "Serviços de suporte gerenciado à infraestrutura de TIC", "Data Center", 55, "direta"),
    ("00531640000128-1-000134/2026",
     "Contratação de subscrição de licenças da suíte de software de nuvem privada VMware Cloud Foundation, com direito "
     "ao suporte técnico oficial do fabricante, atualização de versões, correçõe", "Data Center", 75, "direta"),
    # (id PNCP, objeto, oferta esperada, score mínimo, relação esperada)
    ("83539643000135-1-000060/2026",
     "Contratação de empresa especializada para o fornecimento de renovação de subscrição e licenças da solução de "
     "Segurança de Rede Perimetral do tipo Next-Generation Firewall (NGFW) de dois equipamentos 100F com FortiGate, "
     "em regime de alta di", "Security", 75, "direta"),   # Fortinet = "validar" na config pública
    ("15126437000305-1-004505/2026",
     "CONTRATAÇÃO DE SERVIÇO CONTÍNUO ESPECIALIZADO DE SUSTENTAÇÃO, GERENCIAMENTO, SUPORTE TÉCNICO, MANUTENÇÃO "
     "PREVENTIVA E CORRETIVA E LOCAÇÃO, PARA O PARQUE DE SWITCHES", "Networking", 70, "direta"),
    ("06170517000105-1-000148/2026",
     "Prestação do serviço continuado de assistência técnica, abrangendo manutenção preventiva programada, manutenção "
     "corretiva, suporte técnico e monitoramento remoto proativo online, para o ambiente data center do TRE-RJ",
     "Data Center", 60, "direta"),
    ("08241747000305-1-000015/2026",
     "[Portal de Compras Públicas] - Contratação da renovação da garantia estendida mediante contratação de cobertura "
     "oficial de suporte de hardware Dell Post Standard Support — PSS para 02 (dois) servidores Dell PowerEdge R740xd, "
     "identificados p", "MVS — Multivendor", 60, "direta"),
    ("25053190000136-1-000360/2026",
     "Contratação de serviços de suporte técnico e atualizações de software para o sistema gerenciador de banco de dados "
     "Oracle Standard Edition 2, pelo período de 12 (doze) meses, para atender as demandas do Poder Judiciário do Estado "
     "do Tocantin", "Suporte de software de terceiros", 60, "direta"),
    ("10662072000158-1-000078/2026",
     "Aquisição de solução de armazenamento corporativo (storage) para o ambiente do Datacenter da Reitoria do IFFar, "
     "incluindo equipamentos, licenças, instalação, configuração e garantia/suporte técnico por 60 meses.",
     "Data Center", 60, "indireta"),
    ("01409580000138-1-001292/2026-000001",
     "Registro de Preços para para futura e eventual contratação de solução de infraestrutura de rede local cabeada de "
     "missão crítica, contemplando a prestação de serviços continuados de suporte técnico especializado e garantia, "
     "renovação tec", "Networking", 60, None),
    ("00394502000144-1-011868/2026-000001",
     "Aquisição de appliances de firewall de próxima geração (NGFW), solução de gerenciamento centralizado, appliance de "
     "segurança industrial, licenças de funcionalidades de segurança para firewall, licenças de suporte e garantia do "
     "fabricante ", "Security", 60, "indireta"),
    ("89814693000160-1-000288/2026",
     "[Portal de Compras Públicas] - Aquisição de switches Ethernet gerenciáveis para modernização, expansão e "
     "padronização da infraestrutura de rede lógica da Administração Pública Municipal", "Networking", 45, "indireta"),
]

NEGATIVOS = [
    # (id PNCP, objeto, score máximo) — falsos positivos observados na 1ª calibração
    ("06622443000109-1-000022/2026",
     "Aquisição de 4 (quatro) microcomputadores novos, de primeiro uso, destinados à modernização e ao atendimento das "
     "necessidades operacionais e administrativas do Conselho Regional de Medicina Veterinária do Estado do Ceará "
     "(CRMV-CE), visando as", 45),
    ("33781055000135-1-001882/2026",
     "Serviços continuados de manutenção preditiva, preventiva e corretiva, na modalidade FPP - Full Protection Plan, com "
     "cobertura de peças, em resfriadores de líquido tipo CHILLER da marca CARRIER, sendo 3 unidades modelo 30XWV4206 e "
     "1 unidade do m", 39),
    ("00402552000126-1-000583/2026",
     "Contratação de serviço de manutenção corretiva de autoclaves, abrangendo diagnóstico técnico completo, inspeção "
     "funcional, avaliação dos sistemas eletrônicos, elétricos, mecânicos, pneumáticos, hidráulicos (quando aplicável)", 39),
    ("54689336000132-1-000099/2026",
     "Contratação de empresa especializada para a prestação de serviço continuado de solução integrada de telefonia "
     "interna, compreendendo a locação de Central Privada de Comutação Telefônica – CPCT tipo PABX analógico, com "
     "fornecimento de", 39),
    ("05789902000172-1-000028/2026",
     "Contratação de empresa especializada para a prestação de serviços continuados de engenharia, para a manutenção "
     "preventiva e corretiva, sem o fornecimento de peças e sem dedicação exclusiva de mão de obra, do Sistema de "
     "Detecção, Alarme e Combate a Incêndio (gá", 45),
    ("00394429000100-1-002889/2026",
     "MODERNIZAÇÃO DA CASA DE FORÇA DA GUARDA DA BAPV, INCLUINDO SUBSTITUIÇÃO DE EQUIPAMENTOS E FORNECIMENTO E "
     "INSTALAÇÃO DE GERADOR", 39),
    ("46187506000152-1-000060/2026",
     "Registro de Preços para aquisição de materiais e equipamentos elétricos para suprir de forma continuada as demandas "
     "de manutenção preventiva, corretiva e expansão da infraestrutura elétrica das unidades municipais", 39),
    ("37318510000111-1-000050/2026",
     "Registro de preços para futura e eventual contratação de licenças de software, na modalidade de assinatura anual, "
     "da solução Autodesk Architecture, Engineering & Construction Collection (AEC Collection), incluindo suporte "
     "técnico e atualizaç", 39),
    ("09168704000142-1-000062/2026",
     "Contratação de subscrições da plataforma Microsoft 365, Power BI e Visio, incluindo suporte técnico.", 45),
    ("04567897000190-1-000237/2026",
     "Aquisição de 1.200 (mil e duzentos) aparelhos telefônicos IP SIP, com conectividade de rede sem fio (Wi-Fi) "
     "integrada, fontes de alimentação externa e garantia de 24 (vinte e quatro) meses", 45),
    ("82577636000165-1-000224/2026",
     "contratação de empresa especializada para o fornecimento e instalação de sistema de cortinas cênicas para o "
     "anfiteatro Leda Regina, compreendendo cortina frontal motorizada com abertura central, cortinas de fundo "
     "laterais motorizadas, cortina de fundo central ", 45),
    ("88830609000139-1-000561/2026-000001",
     "Fornecimento e garantia de material de expediente (baterias, pilhas, calculadora e dispositivos de "
     "armazenamentos de dados).", 39),
    ("46634341000110-1-000225/2026-000001",
     "ATA DE REGISTRO DE PREÇO PARA AQUISIÇÃO DE CONTÊINERES E PRESTAÇÃO DE SERVIÇOS DE MANUTENÇÃO CORRETIVA DE "
     "CONTÊINERES PLÁSTICOS COM CAPACIDADE DE 1.000 LITROS DESTINADO AO ARMAZENAMENTO DE LIXO, INCLUINDO O "
     "FORNECIMENTO E SUBSTITUIÇÃO DE PEÇAS E MÃO DE OBRA.", 39),
    ("04972843000100-1-000043/2026",
     "COMPRA DE HD EXTERNO PARA MANUTENÇÃO DA INFRAESTRUTURA DE REDE DA CÂMARA MUNICIPAL DE VEREADORES.", 45),
    ("89768535000110-1-000035/2026",
     "Contratação de empresa especializada para prestação contínua de serviço de acesso dedicado à internet, com lin",
     45),
    ("00489828000155-1-000538/2026",
     "Aquisição de scanner para atender a PRFN5 e seus Escritório de Representação em Caruaru e Petrolina.", 39),
    ("02218683000183-1-000407/2026",
     "SOLICITO AQUISIÇÃO DE UM AR-CONDICIONADO DO TIPO SPLIT HI-WALL, COM TECNOLOGIA INVERTER, CAPACIDADE NOMINAL DE",
     39),
    ("31723265000141-1-000062/2026",
     "disponibilização de infraestrutura computacional em ambiente de nuvem, no modelo de Infraestrutura como Serviç",
     45),
    ("87613071000148-1-000435/2026",
     "AQUISIÇÃO DE EQUIPAMENTOS ESPORTIVOS PARA USO EM ESPAÇOS PÚBLICOS COM RECURSO DE TRANSFERÊNCIA ESPECIAL DE "
     "EMENDA PARLAMENTAR Nº 20269048000", 10),
]


@pytest.mark.parametrize("pid,objeto,oferta,minimo,relacao", POSITIVOS, ids=[p[0] for p in POSITIVOS])
def test_positivos_reais(pf, pid, objeto, oferta, minimo, relacao):
    r = classify(pf, [objeto], stage="publicada", value=None)
    assert r["score"] >= minimo, (pid, r["score"], r["justificativa"])
    assert oferta in r["ofertas"], (pid, r["ofertas"])
    if relacao:
        assert r["relacao"] == relacao, (pid, r["relacao"], r["tipo_servico"])


@pytest.mark.parametrize("pid,objeto,maximo", NEGATIVOS, ids=[n[0] for n in NEGATIVOS])
def test_negativos_reais(pf, pid, objeto, maximo):
    r = classify(pf, [objeto], stage="propostas_abertas", value=5_000_000)
    assert r["score"] <= maximo, (pid, r["score"], r["justificativa"])
