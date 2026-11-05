from datetime import date, datetime

from radar.normalize import (adesao_assessment, ata_ids, compra_ids, contratacao_stage, normalize_ata,
                             normalize_contratacao, portal_name, safe_url, vigencia_status)

NOW = datetime(2026, 11, 4, 10, 0)
TODAY = NOW.date()

# Registro real retornado por /v1/contratacoes/publicacao (probe do CI, 04/11/2026)
REAL_COMPRA = {
    "valorTotalHomologado": None,
    "orgaoEntidade": {"cnpj": "87613071000148", "razaoSocial": "MUNICIPIO DE SANTO ANGELO", "poderId": "N", "esferaId": "M"},
    "numeroControlePNCP": "87613071000148-1-000435/2026", "srp": False, "anoCompra": 2026, "sequencialCompra": 435,
    "numeroCompra": "0081", "processo": "359/2026",
    "objetoCompra": "AQUISIÇÃO DE EQUIPAMENTOS ESPORTIVOS PARA USO EM ESPAÇOS PÚBLICOS COM RECURSO DE TRANSFERÊNCIA ESPECIAL DE EMENDA PARLAMENTAR Nº 20269048000",
    "informacaoComplementar": "", "dataAberturaProposta": "2026-11-03T08:00:00",
    "dataEncerramentoProposta": "2026-11-13T08:00:00", "dataPublicacaoPncp": "2026-11-02T09:00:40",
    "dataAtualizacaoGlobal": "2026-11-03T09:01:03",
    "unidadeOrgao": {"ufNome": "Rio Grande do Sul", "ufSigla": "RS", "municipioNome": "Santo Ângelo", "codigoIbge": "4317509",
                     "codigoUnidade": "109819", "nomeUnidade": "PREFEITURA MUNICIPAL DE SANTO ÂNGELO"},
    "amparoLegal": {"nome": "Lei 14.133/2021, Art. 28, I", "codigo": 1},
    "linkSistemaOrigem": "https://pregaobanrisul.com.br/editais/0081_2026/358860", "linkProcessoEletronico": None,
    "tipoInstrumentoConvocatorioNome": "Edital", "valorTotalEstimado": 115571.37, "modalidadeId": 6,
    "modalidadeNome": "Pregão - Eletrônico", "situacaoCompraId": 1, "situacaoCompraNome": "Divulgada no PNCP",
}

# Registro real de /v1/atas (probe do CI): vigenciaFim inconsistente publicada na fonte
REAL_ATA_INCONSISTENTE = {
    "numeroControlePNCPAta": "45780103000150-1-000001/2023-000001", "numeroAtaRegistroPreco": "PMJ-586", "anoAta": 2023,
    "numeroControlePNCPCompra": "45780103000150-1-000001/2023", "cancelado": False, "dataCancelamento": None,
    "dataAssinatura": "2023-06-28", "vigenciaInicio": "2023-06-28", "vigenciaFim": "7203-07-27",
    "dataPublicacaoPncp": "2023-08-07", "objetoContratacao": "MEDICAMENTOS (POMADA ...) - RP   ",
    "cnpjOrgao": "45780103000150", "nomeOrgao": "MUNICIPIO DE JUNDIAI", "codigoUnidadeOrgao": "14",
    "nomeUnidadeOrgao": "SMPS - Secretaria Municipal de Promoção da Saúde", "possibilidadeAdesao": None,
}


def test_ids_oficiais():
    assert compra_ids("87613071000148-1-000435/2026") == ("87613071000148", 2026, 435)
    assert ata_ids("45780103000150-1-000001/2023-000001") == ("45780103000150", 2023, 1, 1)
    assert compra_ids("lixo") is None


def test_normaliza_compra_real_e_links():
    it = normalize_contratacao(REAL_COMPRA, NOW, "publicacao")
    assert it["id"] == "87613071000148-1-000435/2026"
    assert it["links"]["pncp"] == "https://pncp.gov.br/app/editais/87613071000148/2026/435"
    assert it["links"]["origem"] == "https://pregaobanrisul.com.br/editais/0081_2026/358860"
    assert it["links"]["origem_portal"] == "Pregão Banrisul"
    assert it["estagio"] == "propostas_abertas"
    assert it["valor_estimado"] == 115571.37 and it["valor_homologado"] is None
    assert it["unidade"]["uf"] == "RS"


def test_estagios():
    base = dict(situacaoCompraId=1, modalidadeId=6)
    assert contratacao_stage(dict(base, dataAberturaProposta="2026-11-10T08:00:00",
                                  dataEncerramentoProposta="2026-11-20T08:00:00"), NOW) == "publicada"
    assert contratacao_stage(dict(base, dataAberturaProposta="2026-11-01T08:00:00",
                                  dataEncerramentoProposta="2026-11-20T08:00:00"), NOW) == "propostas_abertas"
    assert contratacao_stage(dict(base, dataEncerramentoProposta="2026-10-01T08:00:00"), NOW) == "julgamento"
    assert contratacao_stage(dict(base, situacaoCompraId=2), NOW) == "encerrada"
    assert contratacao_stage(dict(base, modalidadeId=10), NOW) == "preparacao"


def test_reestagio_usa_datas_armazenadas():
    """Regressão: datas gravadas como 'YYYY-MM-DDTHH:MM' devem ser relidas no reestágio diário."""
    from radar.normalize import restage
    it = normalize_contratacao(dict(REAL_COMPRA, dataAberturaProposta="2026-11-01T08:00:00"), NOW, "x")
    assert it["data_abertura_proposta"] == "2026-11-01T08:00"
    assert restage(it, NOW) == "propostas_abertas"
    assert restage(it, datetime(2026, 11, 14)) == "julgamento"


def test_url_segura():
    assert safe_url("https://x.gov.br/a?b=1") == "https://x.gov.br/a?b=1"
    assert safe_url("www.compras.df.gov.br/x") == "https://www.compras.df.gov.br/x"
    for bad in ("javascript:alert(1)", "ftp://x.com", "http://localhost/x", "", None, "https://semponto", "https://a .com"):
        assert safe_url(bad) is None


def test_link_vazio_nao_e_inventado():
    it = normalize_contratacao(dict(REAL_COMPRA, linkSistemaOrigem=""), NOW, "publicacao")
    assert it["links"]["origem"] is None
    assert it["links"]["pncp"]  # PNCP continua disponível


def test_portal_name():
    assert portal_name("https://cnetmobile.estaleiro.serpro.gov.br/comprasnet-web/x") == "Compras.gov.br"
    assert portal_name("https://desconhecido.exemplo.com.br/a") == "desconhecido.exemplo.com.br"


def test_vigencia():
    assert vigencia_status("2026-01-01", "2027-06-01", False, TODAY)[0] == "vigente"
    assert vigencia_status("2026-01-01", "2026-12-01", False, TODAY)[0] == "vence_em_breve"
    assert vigencia_status("2025-01-01", "2026-01-01", False, TODAY)[0] == "encerrada"
    assert vigencia_status("2026-01-01", "2027-01-01", True, TODAY)[0] == "cancelada"
    assert vigencia_status(None, None, False, TODAY)[0] == "sem_data"


def test_ata_real_com_vigencia_inconsistente():
    a = normalize_ata(REAL_ATA_INCONSISTENTE, TODAY)
    assert a["vigencia_status"] == "inconsistente"
    assert a["vigencia_fim"] is None                       # não exibe data impossível como fato
    assert a["vigencia_fim_publicada"] == "7203-07-27"     # mas preserva o dado publicado
    assert a["links"]["pncp"] == "https://pncp.gov.br/app/atas/45780103000150/2023/1/1"
    assert a["objeto"].endswith("- RP")


def _ata(**kw):
    a = {"vigencia_status": "vigente", "possibilidade_adesao_pncp": None}
    a.update(kw)
    return a


def test_adesao_nao_assume_por_vigencia():
    st, motivos = adesao_assessment(_ata(), ["Registro de preços para switches"])
    assert st == "nao_determinada"
    assert motivos


def test_adesao_campo_oficial():
    assert adesao_assessment(_ata(possibilidade_adesao_pncp=True), [""])[0] == "potencial_verificar"
    assert adesao_assessment(_ata(possibilidade_adesao_pncp=False), [""])[0] == "restricao_identificada"


def test_adesao_texto():
    assert adesao_assessment(_ata(), ["Não será admitida a adesão de órgãos não participantes"])[0] == "restricao_identificada"
    assert adesao_assessment(_ata(), ["Será permitida a adesão por órgãos não participantes"])[0] == "potencial_verificar"
    assert adesao_assessment(_ata(), [""], contratos_adesao=2)[0] == "potencial_verificar"


def test_adesao_ata_encerrada():
    assert adesao_assessment(_ata(vigencia_status="encerrada", possibilidade_adesao_pncp=True), [""])[0] == "encerrada"



def test_regras_de_vencimento():
    from radar.normalize import vencimento
    base = {"tipo": "contratacao", "situacao_id": 1}
    # contratação: vence no encerramento do prazo de propostas
    assert vencimento(dict(base, data_encerramento_proposta="2026-11-20T10:00"), NOW)[:2] == ("2026-11-20", False)
    assert vencimento(dict(base, data_encerramento_proposta="2026-11-01T10:00"), NOW)[1] is True
    # tolerância configurável após o encerramento
    assert vencimento(dict(base, data_encerramento_proposta="2026-11-01T10:00"), NOW,
                      {"contratacoes_dias_apos_encerramento": 10})[1] is False
    # revogada/anulada sai na hora
    assert vencimento(dict(base, situacao_id=2, data_encerramento_proposta="2026-12-01T10:00"), NOW)[1] is True
    # sem prazo informado: publicação + prazo padrão
    assert vencimento(dict(base, data_publicacao="2026-10-01T10:00"), NOW)[:2] == ("2027-01-29", False)
    # PCA: fim do ano do plano
    assert vencimento({"tipo": "pca", "ano": 2026}, NOW)[:2] == ("2026-12-31", False)
    assert vencimento({"tipo": "pca", "ano": 2025}, NOW)[1] is True
    # ata: fim da vigência; cancelada sai; vigência inconsistente fica (conferir)
    assert vencimento({"tipo": "ata", "vigencia_fim": "2027-03-01"}, NOW)[:2] == ("2027-03-01", False)
    assert vencimento({"tipo": "ata", "vigencia_fim": "2026-11-03"}, NOW)[1] is True
    assert vencimento({"tipo": "ata", "vigencia_status": "cancelada", "vigencia_fim": "2027-01-01"}, NOW)[1] is True
    assert vencimento({"tipo": "ata", "vigencia_fim": None, "vigencia_status": "inconsistente"}, NOW)[:2] == (None, False)
    # contrato: fim da vigência
    assert vencimento({"tipo": "contrato", "vigencia_fim": "2026-12-31"}, NOW)[1] is False
    assert vencimento({"tipo": "contrato", "vigencia_fim": "2026-10-31"}, NOW)[1] is True
