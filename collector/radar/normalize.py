"""Normalização dos registros do PNCP para o modelo do Radar.

Regras de honestidade:
- Nenhum campo é inventado: ausências ficam None e são exibidas como "não informado".
- Links do PNCP seguem a estrutura pública do portal (validada no CI pelo probe);
  o link do portal de origem é SEMPRE o `linkSistemaOrigem` informado pelo órgão.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

STAGE_LABELS = {
    "planejamento": "Planejamento (PCA)",
    "preparacao": "Preparação (ETP/pesquisa de preços)",
    "publicada": "Edital/aviso publicado",
    "propostas_abertas": "Propostas abertas",
    "julgamento": "Julgamento/homologação",
    "ata_vigente": "Ata vigente",
    "concluida": "Contratação concluída",
    "encerrada": "Encerrada/cancelada",
}


def normalize_text(text: str | None) -> str:
    """Minúsculas, sem acento, só [a-z0-9-/.] e espaços simples (regex de adesão e afins)."""
    out: list[str] = []
    for ch in unicodedata.normalize("NFKD", text or ""):
        if unicodedata.combining(ch):
            continue
        ch = ch.lower()
        if not (ch.isalnum() or ch in "-/."):
            ch = " "
        if ch == " " and (not out or out[-1] == " "):
            continue
        out.append(ch)
    return "".join(out).strip()

PNCP_APP = "https://pncp.gov.br/app"

STAGE_ORDER = ["planejamento", "preparacao", "publicada", "propostas_abertas", "julgamento",
               "ata_vigente", "concluida", "encerrada"]

# Domínio -> nome amigável do portal de origem (apenas rótulo; o link vem da fonte).
PORTAL_NAMES = {
    "cnetmobile.estaleiro.serpro.gov.br": "Compras.gov.br",
    "www.gov.br": "Compras.gov.br",
    "comprasnet.gov.br": "Compras.gov.br",
    "www.comprasnet.gov.br": "Compras.gov.br",
    "pregaobanrisul.com.br": "Pregão Banrisul",
    "licitanet.com.br": "Licitanet",
    "www.licitanet.com.br": "Licitanet",
    "app2.licitardigital.com.br": "Licitar Digital",
    "www.portaldecompraspublicas.com.br": "Portal de Compras Públicas",
    "portaldecompraspublicas.com.br": "Portal de Compras Públicas",
    "bllcompras.com": "BLL Compras",
    "www.bllcompras.com": "BLL Compras",
    "bnccompras.com": "BNC Compras",
    "www.licitacoes-e.com.br": "Licitações-e (Banco do Brasil)",
    "licitacoes-e2.bb.com.br": "Licitações-e (Banco do Brasil)",
    "www.bec.sp.gov.br": "BEC/SP",
    "www.compras.mg.gov.br": "Portal de Compras MG",
    "www.compras.rj.gov.br": "SIGA/RJ",
    "www.centraldecompras.pb.gov.br": "Central de Compras PB",
    "compras.df.gov.br": "Compras DF",
    "www.compras.df.gov.br": "Compras DF",
    "ecompras.caixa.gov.br": "Licitações CAIXA",
    "www.licitacoes.caixa.gov.br": "Licitações CAIXA",
}

MODALIDADES = {
    1: "Leilão - Eletrônico", 2: "Diálogo Competitivo", 3: "Concurso", 4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial", 6: "Pregão - Eletrônico", 7: "Pregão - Presencial",
    8: "Dispensa", 9: "Inexigibilidade", 10: "Manifestação de Interesse", 11: "Pré-qualificação",
    12: "Credenciamento", 13: "Leilão - Presencial",
}


# --------------------------------------------------------------------- helpers
def parse_dt(v: Any) -> datetime | None:
    if not v or not isinstance(v, str):
        return None
    s = v.strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    return None


def iso(v: Any) -> str | None:
    d = parse_dt(v)
    if not d:
        return None
    return d.date().isoformat() if (d.hour, d.minute, d.second) == (0, 0, 0) and len(str(v)) <= 10 else d.isoformat(timespec="minutes")


def num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def safe_url(u: Any) -> str | None:
    """Aceita apenas http(s) com host válido; descarta javascript:, mailto:, espaços etc."""
    if not u or not isinstance(u, str):
        return None
    u = u.strip()
    if len(u) > 2000 or any(c in u for c in ' \n\r\t"<>'):
        return None
    if u.lower().startswith("www."):
        u = "https://" + u
    try:
        p = urlparse(u)
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.netloc or "." not in p.netloc:
        return None
    host = p.hostname or ""
    if host in ("localhost",) or re.fullmatch(r"[\d.]+", host) and host.startswith(("10.", "127.", "192.168.")):
        return None
    return u


def portal_name(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    if host in PORTAL_NAMES:
        return PORTAL_NAMES[host]
    for dom, name in PORTAL_NAMES.items():
        if host.endswith("." + dom.removeprefix("www.")):
            return name
    return host.removeprefix("www.") or None


def pncp_doc_url(u: str | None) -> str | None:
    """A API devolve URLs de arquivos em /pncp-api/...; ambas as formas são oficiais."""
    return safe_url(u)


# ---------------------------------------------------------------- contratação
def compra_ids(numero_controle: str) -> tuple[str, int, int] | None:
    """'87613071000148-1-000435/2026' -> ('87613071000148', 2026, 435)"""
    m = re.fullmatch(r"(\d{14})-1-(\d+)/(\d{4})", numero_controle or "")
    if not m:
        return None
    return m.group(1), int(m.group(3)), int(m.group(2))


def ata_ids(numero_controle_ata: str) -> tuple[str, int, int, int] | None:
    """'45780103000150-1-000001/2023-000001' -> (cnpj, ano, seqCompra, seqAta)"""
    m = re.fullmatch(r"(\d{14})-1-(\d+)/(\d{4})-(\d+)", numero_controle_ata or "")
    if not m:
        return None
    return m.group(1), int(m.group(3)), int(m.group(2)), int(m.group(4))


def contratacao_stage(r: dict, now: datetime) -> str:
    sit = r.get("situacaoCompraId")
    if sit in (2, 3):  # revogada / anulada
        return "encerrada"
    mod = r.get("modalidadeId")
    if mod in (10, 11):
        return "preparacao"
    ab = parse_dt(r.get("dataAberturaProposta"))
    en = parse_dt(r.get("dataEncerramentoProposta"))
    if num(r.get("valorTotalHomologado")):
        return "julgamento" if not (en and en > now) else "propostas_abertas"
    if en and en >= now:
        if ab and ab > now:
            return "publicada"
        return "propostas_abertas"
    if en and en < now:
        return "julgamento"
    return "publicada"


def normalize_contratacao(r: dict, now: datetime, fonte: str) -> dict[str, Any] | None:
    ctrl = r.get("numeroControlePNCP")
    ids = compra_ids(ctrl)
    if not ids:
        return None
    cnpj, ano, seq = ids
    org = r.get("orgaoEntidade") or {}
    un = r.get("unidadeOrgao") or {}
    origem = safe_url(r.get("linkSistemaOrigem"))
    stage = contratacao_stage(r, now)
    mod_id = r.get("modalidadeId")
    return {
        "id": ctrl,
        "tipo": "contratacao",
        "fonte": "PNCP",
        "feeds": [fonte],
        "numero": r.get("numeroCompra"),
        "processo": r.get("processo"),
        "ano": ano,
        "sequencial": seq,
        "orgao": {"cnpj": cnpj, "nome": org.get("razaoSocial"), "esfera": org.get("esferaId"),
                  "poder": org.get("poderId")},
        "unidade": {"codigo": un.get("codigoUnidade"), "nome": un.get("nomeUnidade"), "uf": un.get("ufSigla"),
                    "municipio": un.get("municipioNome"), "ibge": un.get("codigoIbge")},
        "objeto": (r.get("objetoCompra") or "").strip(),
        "info_complementar": (r.get("informacaoComplementar") or "").strip() or None,
        "modalidade": {"id": mod_id, "nome": r.get("modalidadeNome") or MODALIDADES.get(mod_id)},
        "modo_disputa": r.get("modoDisputaNome"),
        "instrumento": r.get("tipoInstrumentoConvocatorioNome"),
        "amparo_legal": (r.get("amparoLegal") or {}).get("nome"),
        "srp": bool(r.get("srp")),
        "situacao": r.get("situacaoCompraNome"),
        "situacao_id": r.get("situacaoCompraId"),
        "valor_estimado": num(r.get("valorTotalEstimado")),
        "valor_homologado": num(r.get("valorTotalHomologado")),
        "data_publicacao": iso(r.get("dataPublicacaoPncp")),
        "data_abertura_proposta": iso(r.get("dataAberturaProposta")),
        "data_encerramento_proposta": iso(r.get("dataEncerramentoProposta")),
        "data_atualizacao_fonte": iso(r.get("dataAtualizacaoGlobal") or r.get("dataAtualizacao")),
        "estagio": stage,
        "links": {
            "pncp": f"{PNCP_APP}/editais/{cnpj}/{ano}/{seq}",
            "origem": origem,
            "origem_portal": portal_name(origem),
            "processo_eletronico": safe_url(r.get("linkProcessoEletronico")),
        },
    }


def restage(item: dict, now: datetime) -> str:
    """Recalcula o estágio a cada execução (datas avançam; não depende de nova coleta)."""
    t = item.get("tipo")
    if t == "contratacao":
        raw = {"situacaoCompraId": item.get("situacao_id"), "modalidadeId": (item.get("modalidade") or {}).get("id"),
               "dataAberturaProposta": item.get("data_abertura_proposta"),
               "dataEncerramentoProposta": item.get("data_encerramento_proposta"),
               "valorTotalHomologado": item.get("valor_homologado")}
        return contratacao_stage(raw, now)
    if t == "ata":
        return "ata_vigente" if item.get("vigencia_status") in ("vigente", "vence_em_breve") else "encerrada"
    if t == "contrato":
        return "concluida"
    if t == "pca":
        return "planejamento"
    return item.get("estagio") or "publicada"


# ------------------------------------------------------------------------ atas
ADESAO_NEG = [
    r"vedad[ao]s? (?:a )?ades(?:ao|oes)", r"nao (?:sera|serao) (?:admitid|permitid|aceit)[ao]s? (?:a )?ades",
    r"sem (?:possibilidade|previsao) de adesao", r"nao (?:e|sera) permitid[ao] (?:a )?adesao",
    r"nao (?:se )?admite adesao", r"nao cabe adesao", r"proibid[ao] (?:a )?adesao",
]
ADESAO_POS = [
    r"permitid[ao] (?:a )?adesao", r"admitid[ao] (?:a )?adesao", r"admite(?:-se)? (?:a )?adesao",
    r"possibilidade de adesao", r"orgaos? (?:e entidades )?nao participantes", r"adesao (?:por|de) (?:outros )?orgaos",
    r"carona",
]


def vigencia_status(inicio: str | None, fim: str | None, cancelado: bool, today: date,
                    soon_days: int = 90, max_years: int = 6) -> tuple[str, int | None]:
    if cancelado:
        return "cancelada", None
    f = parse_dt(fim)
    if not f:
        return "sem_data", None
    fd = f.date()
    if fd > today + timedelta(days=365 * max_years):
        return "inconsistente", None   # ex.: vigenciaFim "7203-07-27" publicado na fonte
    days = (fd - today).days
    if days < 0:
        return "encerrada", days
    i = parse_dt(inicio)
    if i and i.date() > today:
        return "vigente", days
    return ("vence_em_breve" if days <= soon_days else "vigente"), days


def adesao_assessment(ata: dict, texts: list[str], contratos_adesao: int = 0) -> tuple[str, list[str]]:
    """Avalia a POSSIBILIDADE de adesão apenas com evidência pública disponível.
    Nunca afirma elegibilidade jurídica nem saldo."""
    motivos: list[str] = []
    if ata.get("vigencia_status") in ("encerrada", "cancelada"):
        return "encerrada", ["Ata encerrada, vencida ou cancelada segundo o PNCP."]
    text = normalize_text(" ".join(t for t in texts if t))
    neg = any(re.search(p, text) for p in ADESAO_NEG)
    pos = any(re.search(p, text) for p in ADESAO_POS)
    flag = ata.get("possibilidade_adesao_pncp")
    if flag is False:
        motivos.append("PNCP informa que a ata NÃO admite adesão (campo possibilidadeAdesao).")
    if neg:
        motivos.append("Texto público menciona vedação/restrição de adesão.")
    if flag is False or neg:
        return "restricao_identificada", motivos
    if flag is True:
        motivos.append("PNCP informa possibilidade de adesão (campo possibilidadeAdesao).")
    if pos:
        motivos.append("Texto público menciona adesão/órgãos não participantes.")
    if contratos_adesao:
        motivos.append(f"{contratos_adesao} contrato(s) publicados no PNCP como fruto de adesão a esta ata.")
    if ata.get("vigencia_status") == "inconsistente":
        motivos.append("Data de fim de vigência publicada parece inconsistente — conferir documento.")
    if flag is True or pos or contratos_adesao:
        return "potencial_verificar", motivos
    motivos.append("Sem evidência pública sobre adesão; consultar edital e órgão gerenciador.")
    return "nao_determinada", motivos


def normalize_ata(r: dict, today: date, soon_days: int = 90) -> dict[str, Any] | None:
    ctrl = r.get("numeroControlePNCPAta")
    ids = ata_ids(ctrl)
    if not ids:
        return None
    cnpj, ano, seq_c, seq_a = ids
    vs, days = vigencia_status(r.get("vigenciaInicio"), r.get("vigenciaFim"), bool(r.get("cancelado")), today, soon_days)
    pa = r.get("possibilidadeAdesao")
    return {
        "id": ctrl,
        "tipo": "ata",
        "fonte": "PNCP",
        "numero": (r.get("numeroAtaRegistroPreco") or "").strip() or None,
        "ano": r.get("anoAta"),
        "compra_id": r.get("numeroControlePNCPCompra"),
        "orgao": {"cnpj": r.get("cnpjOrgao"), "nome": r.get("nomeOrgao"), "esfera": None},
        "unidade": {"codigo": r.get("codigoUnidadeOrgao"), "nome": r.get("nomeUnidadeOrgao"), "uf": None, "municipio": None},
        "orgao_subrogado": r.get("nomeOrgaoSubrogado"),
        "objeto": re.sub(r"\s+", " ", (r.get("objetoContratacao") or "")).strip(),
        "data_assinatura": iso(r.get("dataAssinatura")),
        "vigencia_inicio": iso(r.get("vigenciaInicio")),
        "vigencia_fim": iso(r.get("vigenciaFim")) if vs != "inconsistente" else None,
        "vigencia_fim_publicada": r.get("vigenciaFim"),
        "vigencia_status": vs,
        "dias_para_vencer": days,
        "cancelado": bool(r.get("cancelado")),
        "data_cancelamento": iso(r.get("dataCancelamento")),
        "possibilidade_adesao_pncp": pa if isinstance(pa, bool) else None,
        "data_publicacao": iso(r.get("dataPublicacaoPncp")),
        "data_atualizacao_fonte": iso(r.get("dataAtualizacaoGlobal") or r.get("dataAtualizacao")),
        "sistema_publicador": r.get("usuario"),
        "estagio": "ata_vigente" if vs in ("vigente", "vence_em_breve", "inconsistente", "sem_data") else "encerrada",
        "links": {
            "pncp": f"{PNCP_APP}/atas/{cnpj}/{ano}/{seq_c}/{seq_a}",
            "pncp_compra": f"{PNCP_APP}/editais/{cnpj}/{ano}/{seq_c}",
            "origem": None, "origem_portal": None,
        },
        "fornecedores": [],
        "contratos_adesao": 0,
    }


def refresh_ata_vigencia(ata: dict, today: date, soon_days: int = 90) -> None:
    raw_fim = ata.get("vigencia_fim_publicada") or ata.get("vigencia_fim")
    vs, days = vigencia_status(ata.get("vigencia_inicio"), raw_fim, ata.get("cancelado", False), today, soon_days)
    ata["vigencia_status"], ata["dias_para_vencer"] = vs, days
    ata["estagio"] = "ata_vigente" if vs in ("vigente", "vence_em_breve", "inconsistente", "sem_data") else "encerrada"


# -------------------------------------------------------------------- contrato
def normalize_contrato(r: dict) -> dict[str, Any] | None:
    ctrl = r.get("numeroControlePNCP")
    m = re.fullmatch(r"(\d{14})-2-(\d+)/(\d{4})", ctrl or "")
    if not m:
        return None
    cnpj, seq, ano = m.group(1), int(m.group(2)), int(m.group(3))
    org = r.get("orgaoEntidade") or {}
    un = r.get("unidadeOrgao") or {}
    return {
        "id": ctrl,
        "tipo": "contrato",
        "fonte": "PNCP",
        "numero": r.get("numeroContratoEmpenho"),
        "processo": r.get("processo"),
        "ano": ano,
        "orgao": {"cnpj": cnpj, "nome": org.get("razaoSocial"), "esfera": org.get("esferaId"), "poder": org.get("poderId")},
        "unidade": {"codigo": un.get("codigoUnidade"), "nome": un.get("nomeUnidade"), "uf": un.get("ufSigla"),
                    "municipio": un.get("municipioNome")},
        "objeto": (r.get("objetoContrato") or "").strip(),
        "info_complementar": (r.get("informacaoComplementar") or "").strip() or None,
        "tipo_contrato": (r.get("tipoContrato") or {}).get("nome"),
        "fornecedor": {"ni": r.get("niFornecedor"), "nome": r.get("nomeRazaoSocialFornecedor")},
        "valor_global": num(r.get("valorGlobal")),
        "valor_estimado": num(r.get("valorGlobal")),
        "data_assinatura": iso(r.get("dataAssinatura")),
        "vigencia_inicio": iso(r.get("dataVigenciaInicio")),
        "vigencia_fim": iso(r.get("dataVigenciaFim")),
        "data_publicacao": iso(r.get("dataPublicacaoPncp")),
        "data_atualizacao_fonte": iso(r.get("dataAtualizacaoGlobal") or r.get("dataAtualizacao")),
        "fruto_adesao": bool(r.get("frutoAdesao")),
        "compra_id": r.get("numeroControlePncpCompra"),
        "ata_id": r.get("numeroControlePncpAta"),
        "estagio": "concluida",
        "links": {"pncp": f"{PNCP_APP}/contratos/{cnpj}/{ano}/{seq}", "origem": None, "origem_portal": None},
    }


# ------------------------------------------------------------------------- PCA
def normalize_pca_items(r: dict, ano_filter: set[int] | None = None) -> list[dict[str, Any]]:
    """Um PCA (com lista `itens`) ou um item isolado -> itens normalizados."""
    out: list[dict[str, Any]] = []
    ano = r.get("anoPca") or r.get("ano")
    if ano_filter and ano and int(ano) not in ano_filter:
        return out
    cnpj = r.get("orgaoEntidadeCnpj") or r.get("cnpj") or (r.get("orgaoEntidade") or {}).get("cnpj")
    org_nome = r.get("orgaoEntidadeRazaoSocial") or r.get("razaoSocial") or (r.get("orgaoEntidade") or {}).get("razaoSocial")
    un_cod = r.get("codigoUnidade")
    un_nome = r.get("nomeUnidade")
    pca_id = r.get("idPcaPncp") or r.get("numeroControlePNCP")
    itens = r.get("itens")
    if itens is None:
        itens = [r]
    for it in itens:
        n = it.get("numeroItem")
        desc = (it.get("descricaoItem") or it.get("descricao") or "").strip()
        if not desc and not it.get("pdmDescricao"):
            continue
        iid = f"pca:{pca_id or cnpj}:{ano}:{un_cod}:{n}"
        out.append({
            "id": iid,
            "tipo": "pca",
            "fonte": "PNCP",
            "ano": ano,
            "pca_id": pca_id,
            "numero": n,
            "orgao": {"cnpj": cnpj, "nome": org_nome, "esfera": None},
            "unidade": {"codigo": un_cod, "nome": un_nome, "uf": None, "municipio": None},
            "objeto": desc,
            "info_complementar": " | ".join(x for x in [it.get("pdmDescricao"), it.get("nomeClassificacaoCatalogo"),
                                                        it.get("classificacaoSuperiorNome"), it.get("grupoContratacaoNome")] if x) or None,
            "categoria": it.get("categoriaItemPcaNome"),
            "classificacao_superior": {"codigo": it.get("classificacaoSuperiorCodigo"), "nome": it.get("classificacaoSuperiorNome")},
            "quantidade": it.get("quantidadeEstimada"),
            "valor_estimado": num(it.get("valorTotal")),
            "valor_orcamento_exercicio": num(it.get("valorOrcamentoExercicio")),
            "data_desejada": iso(it.get("dataDesejada")),
            "unidade_requisitante": it.get("unidadeRequisitante"),
            "data_publicacao": iso(r.get("dataPublicacaoPNCP") or r.get("dataPublicacaoPncp")),
            "data_atualizacao_fonte": iso(it.get("dataAtualizacao") or r.get("dataAtualizacaoGlobalPCA")),
            "estagio": "planejamento",
            "links": {"pncp": f"{PNCP_APP}/pca/{cnpj}/{ano}" if cnpj and ano else None,
                      "origem": None, "origem_portal": None},
        })
    return out


# ----------------------------------------------------------------- vencimento
def vencimento(item: dict, now: datetime, cfg: dict | None = None) -> tuple[str | None, bool, str]:
    """Data em que o registro deixa de estar ativo e sai do site (continua na base histórica).

    Retorna (vence_em ISO ou None, já_venceu, motivo). Regras (configuráveis em fontes.yml > vencimento):
      contratação  -> encerramento do prazo de propostas (+ dias de tolerância);
                      revogada/anulada encerra na hora; sem prazo informado -> publicação + N dias
      item de PCA  -> fim do ano do plano (31/12 do anoPca)
      ata          -> fim da vigência publicada; cancelada encerra na hora;
                      vigência ausente/inconsistente -> nunca vence automaticamente (conferir)
      contrato     -> fim da vigência; sem vigência -> publicação + N dias
    """
    cfg = cfg or {}
    today = now.date()
    t = item.get("tipo")
    if t == "contratacao":
        if item.get("situacao_id") in (2, 3):
            return today.isoformat(), True, f"contratação {str(item.get('situacao') or 'revogada/anulada').lower()}"
        enc = parse_dt(item.get("data_encerramento_proposta"))
        if enc:
            fim = enc + timedelta(days=int(cfg.get("contratacoes_dias_apos_encerramento", 0)))
            return fim.date().isoformat(), fim < now, "encerramento do prazo de propostas"
        pub = parse_dt(item.get("data_publicacao"))
        if pub:
            fim = pub + timedelta(days=int(cfg.get("contratacoes_sem_prazo_dias", 120)))
            return fim.date().isoformat(), fim < now, "sem prazo de propostas informado (publicação + prazo padrão)"
        return None, False, "sem datas informadas"
    if t == "pca":
        try:
            fim = date(int(item.get("ano")), 12, 31)
        except (TypeError, ValueError):
            return None, False, "ano do PCA não informado"
        return fim.isoformat(), fim < today, "fim do ano do plano de contratações"
    if t == "ata":
        if item.get("vigencia_status") == "cancelada" or item.get("cancelado"):
            return (item.get("data_cancelamento") or today.isoformat())[:10], True, "ata cancelada"
        fim = parse_dt(item.get("vigencia_fim"))
        if fim:
            return fim.date().isoformat(), fim.date() < today, "fim da vigência da ata"
        return None, False, "vigência não informada ou inconsistente — conferir na ata"
    if t == "contrato":
        fim = parse_dt(item.get("vigencia_fim"))
        if fim:
            return fim.date().isoformat(), fim.date() < today, "fim da vigência do contrato"
        pub = parse_dt(item.get("data_publicacao"))
        if pub:
            f = pub + timedelta(days=int(cfg.get("contratos_sem_vigencia_dias", 365)))
            return f.date().isoformat(), f < now, "sem vigência informada (publicação + prazo padrão)"
        return None, False, "sem datas informadas"
    return None, False, ""
