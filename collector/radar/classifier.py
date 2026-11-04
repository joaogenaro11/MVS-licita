"""Motor de classificação TLS (regras + sinônimos + pesos, 100% configurável).

Etapas:
 1. Busca ampla  — termos de oferta, serviço, fabricantes e sinônimos (config/portfolio_tls.yml).
 2. Contexto     — neutraliza falsos positivos clássicos ("servidores públicos",
                   "rede municipal de ensino", "segurança patrimonial"...), separa
                   suporte/manutenção x aquisição x serviço de TI genérico.
 3. Score 0–100  — aderência técnica (portfólio, suporte, fabricante, evidências)
                   + urgência comercial (valor, estágio) multiplicada pelo fator técnico.
 4. Justificativa — gerada SOMENTE a partir dos termos encontrados no texto público.

Somente texto do objeto/informação complementar/itens é analisado. O nome do órgão
NÃO entra (evita "Secretaria de Segurança" virar oportunidade de Security).
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

LEVEL_WEIGHT = {"strong": 1.0, "medium": 0.5, "weak": 0.2}
STOPWORDS = {"de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "para", "com", "sem", "em", "no", "na", "por", "ao", "x"}
COVERAGE_FACTOR = {"confirmada": 1.0, "validar": 0.6, "fora_tls": 0.0}
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


# --------------------------------------------------------------------------- texto
def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Minúsculas, sem acento, só [a-z0-9-/.] e espaços simples.
    Retorna também o mapa índice_normalizado -> índice_original (para citar trechos)."""
    chars: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text or ""):
        for c in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(c):
                continue
            c = c.lower()
            if not (c.isalnum() or c in "-/."):
                c = " "
            if c == " " and (not chars or chars[-1] == " "):
                continue
            chars.append(c)
            idx.append(i)
    return "".join(chars), idx


def normalize(text: str) -> str:
    return normalize_with_map(text)[0].strip()


def _word_pattern(word: str) -> str:
    if word in STOPWORDS or len(word) < 3 or not word[-1].isalpha():
        return re.escape(word).replace(r"\-", "[- ]?")
    w = re.escape(word).replace(r"\-", "[- ]?")
    if word.endswith("cao"):
        return w[:-3] + "c(?:ao|oes)"
    if word.endswith("al"):
        return w[:-1] + "(?:l|is)"
    if word.endswith("m"):
        return w[:-1] + "(?:m|ns)"
    if word.endswith(("r", "z", "h")):
        return w + "(?:es)?"
    if word.endswith(("s", "x")):
        return w
    return w + "s?"


def term_regex(term: str) -> re.Pattern:
    words = normalize(term).split(" ")
    body = " ".join(_word_pattern(w) for w in words if w)
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")


@dataclass
class Term:
    text: str
    category: str      # offer key | "support" | "vendor:<nome>" | "penalty" | "acquisition"
    weight: float
    regex: re.Pattern
    level: str = ""


@dataclass
class Match:
    term: Term
    start: int
    end: int


# ----------------------------------------------------------------------- portfolio
@dataclass
class Portfolio:
    raw: dict[str, Any]
    offer_terms: list[Term] = field(default_factory=list)
    support_terms: list[Term] = field(default_factory=list)
    vendor_terms: list[Term] = field(default_factory=list)
    penalty_terms: list[Term] = field(default_factory=list)
    acquisition_terms: list[Term] = field(default_factory=list)
    neutralize: list[re.Pattern] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | str, private: str | None = None) -> "Portfolio":
        """Carrega a configuração pública e aplica, se houver, a sobreposição privada
        (variável RADAR_PRIVATE_CONFIG ou config/portfolio_private.yml — fora do git)."""
        p = Path(path)
        if p.is_dir():
            p = p / "portfolio_tls.yml"
        with open(p, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        if private is None:
            private = os.environ.get("RADAR_PRIVATE_CONFIG")
            priv_file = p.parent / "portfolio_private.yml"
            if not private and priv_file.exists():
                private = priv_file.read_text(encoding="utf-8")
        if private:
            raw = apply_private_overlay(raw, yaml.safe_load(private) or {})
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Portfolio":
        pf = cls(raw=raw)
        for key, offer in raw["offers"].items():
            for level in ("strong", "medium", "weak"):
                for t in offer.get(level) or []:
                    pf.offer_terms.append(Term(t, key, LEVEL_WEIGHT[level], term_regex(t), level))
        for level in ("strong", "medium", "weak"):
            for t in (raw.get("support_terms") or {}).get(level) or []:
                pf.support_terms.append(Term(t, "support", LEVEL_WEIGHT[level], term_regex(t), level))
        for name, v in (raw.get("vendors") or {}).items():
            for a in v.get("aliases") or []:
                pf.vendor_terms.append(Term(a, f"vendor:{name}", 1.0, term_regex(a)))
        pen = raw.get("penalties") or {}
        for t in pen.get("terms") or []:
            pf.penalty_terms.append(Term(t, "penalty", float(pen.get("penalty", 0.5)), term_regex(t)))
        for t in raw.get("acquisition_terms") or []:
            pf.acquisition_terms.append(Term(t, "acquisition", 1.0, term_regex(t)))
        pf.neutralize = [term_regex(t) for t in raw.get("neutralize") or []]
        # termos mais longos primeiro: "switch san" consome o trecho antes de "switch"
        for lst in (pf.offer_terms, pf.support_terms, pf.vendor_terms, pf.penalty_terms):
            lst.sort(key=lambda t: len(t.text), reverse=True)
        return pf

    # atalhos de configuração
    @property
    def weights(self) -> dict[str, float]:
        return self.raw["weights"]

    @property
    def thresholds(self) -> dict[str, float]:
        return self.raw["thresholds"]

    def offer_label(self, key: str) -> str:
        return self.raw["offers"].get(key, {}).get("label", key)

    def faixa(self, score: float) -> str:
        th = self.thresholds
        if score >= th["alta"]:
            return "alta"
        if score >= th["analisar"]:
            return "analisar"
        if score >= th["indireto"]:
            return "indireto"
        return "baixa"


def apply_private_overlay(raw: dict[str, Any], priv: dict[str, Any]) -> dict[str, Any]:
    """Aplica SOMENTE parâmetros numéricos/enumerados da configuração privada.
    Notas, listas de órgãos e parceiros são ignoradas aqui de propósito: o resultado
    da coleta é publicado, e esse conteúdo só deve aparecer na interface autenticada."""
    import copy
    out = copy.deepcopy(raw)
    for key, ov in (priv.get("offers") or {}).items():
        if key in out["offers"] and isinstance(ov, dict) and "fit_factor" in ov:
            out["offers"][key]["fit_factor"] = float(ov["fit_factor"])
    for name, ov in (priv.get("vendors") or {}).items():
        cov = (ov or {}).get("tls_coverage") if isinstance(ov, dict) else None
        if name in out.get("vendors", {}) and cov in COVERAGE_FACTOR:
            out["vendors"][name]["tls_coverage"] = cov
    for sect in ("weights", "thresholds"):
        for k, v in (priv.get(sect) or {}).items():
            if k in out.get(sect, {}) and isinstance(v, (int, float)):
                out[sect][k] = v
    return out


FAIXA_LABEL = {"alta": "Alta prioridade", "analisar": "Analisar", "indireto": "Potencial indireto", "baixa": "Baixa aderência"}


def _find(terms: list[Term], text: str, consume: bool = True) -> list[Match]:
    """Encontra termos; com consume=True, um trecho já casado por termo mais longo
    não é contado de novo por um termo mais curto contido nele."""
    taken = bytearray(len(text))
    out: list[Match] = []
    for t in terms:
        for m in t.regex.finditer(text):
            s, e = m.span()
            if consume and any(taken[s:e]):
                continue
            out.append(Match(t, s, e))
            if consume:
                taken[s:e] = b"\x01" * (e - s)
    return out


def _snippet(original: str, idx: list[int], s: int, e: int, pad: int = 45) -> str:
    if not idx:
        return ""
    os_, oe = idx[s], idx[min(e, len(idx)) - 1] + 1
    a, b = max(0, os_ - pad), min(len(original), oe + pad)
    pre = "…" if a > 0 else ""
    post = "…" if b < len(original) else ""
    return (pre + original[a:b] + post).replace("\n", " ").strip()


def _original(original: str, idx: list[int], s: int, e: int) -> str:
    return original[idx[s]: idx[min(e, len(idx)) - 1] + 1]


# ----------------------------------------------------------------------- classify
def classify(pf: Portfolio, texts: list[str], stage: str | None = None,
             value: float | None = None, has_items: bool = False) -> dict[str, Any]:
    raw = pf.raw
    W = pf.weights
    sat = raw.get("saturation", {})
    original = " | ".join(t.strip() for t in texts if t and t.strip())
    norm, idx = normalize_with_map(original)

    # Etapa 2a — neutraliza falsos positivos (mantendo comprimento/índices)
    work = list(norm)
    for rx in pf.neutralize:
        for m in rx.finditer(norm):
            for i in range(*m.span()):
                work[i] = " "
    text = "".join(work)

    offer_matches = _find(pf.offer_terms, text)
    support_matches = _find(pf.support_terms, text)
    vendor_matches = _find(pf.vendor_terms, text)
    penalty_matches = _find(pf.penalty_terms, text)
    acq = bool(_find(pf.acquisition_terms, text, consume=False))

    # força por oferta (termos distintos)
    strength: dict[str, float] = {}
    best_level: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for m in offer_matches:
        k = (m.term.category, m.term.text)
        if k in seen:
            continue
        seen.add(k)
        strength[m.term.category] = strength.get(m.term.category, 0.0) + m.term.weight
        if m.term.level in ("strong", "medium"):
            best_level[m.term.category] = "strong" if "strong" in (best_level.get(m.term.category), m.term.level) else "medium"

    # fabricantes
    vendors_cfg = raw.get("vendors") or {}
    vendors: dict[str, dict[str, Any]] = {}
    for m in vendor_matches:
        name = m.term.category.split(":", 1)[1]
        if name not in vendors:
            v = vendors_cfg[name]
            vendors[name] = {"nome": name, "cobertura": v.get("tls_coverage", "validar"),
                             "nota": v.get("note"), "termo": _original(original, idx, m.start, m.end),
                             "offers": v.get("offers") or []}
    for v in vendors.values():
        if v["cobertura"] == "fora_tls":
            continue
        targets = [o for o in v["offers"] if o in strength] or v["offers"][:1]
        for o in targets:
            strength[o] = strength.get(o, 0.0) + 0.6
            best_level.setdefault(o, "medium")

    # requisitos de contexto por oferta (ex.: "modernização" só conta se houver
    # infraestrutura de TIC; suporte de software só conta forte com fabricante no escopo)
    offers_cfg_all = raw["offers"]
    infra_vendor_offers = {o for v in vendors.values() if v["cobertura"] != "fora_tls" for o in v["offers"]}
    for k in list(strength):
        cfg = offers_cfg_all.get(k, {})
        ctx_keys = cfg.get("requires_context") or []
        if ctx_keys and max((strength.get(o, 0.0) for o in ctx_keys), default=0.0) < 0.5:
            strength[k] *= float(cfg.get("context_missing_factor", 0.3))
            best_level.pop(k, None)
        if cfg.get("requires_vendor") and k not in infra_vendor_offers:
            strength[k] *= float(cfg.get("vendor_missing_factor", 0.5))

    # penalidades (contexto genérico/fora do escopo)
    pen_terms = sorted({m.term.text for m in penalty_matches})
    first_offer = min((m.start for m in offer_matches if m.term.level in ("strong", "medium")), default=None)
    first_pen = min((m.start for m in penalty_matches), default=None)
    primary_out_of_scope = first_pen is not None and (first_offer is None or first_pen < first_offer)
    pen_total = min(1.0, sum(float((raw.get("penalties") or {}).get("penalty", 0.5)) for _ in pen_terms))

    # oferta principal
    offers_cfg = raw["offers"]

    def eff(k: str) -> float:
        return max(0.0, strength[k] - pen_total) * float(offers_cfg[k].get("fit_factor", 1.0))

    ranked = sorted(strength, key=eff, reverse=True)
    best = ranked[0] if ranked else None
    best_strength = max(0.0, strength[best] - pen_total) if best else 0.0
    fit = float(offers_cfg[best].get("fit_factor", 1.0)) if best else 0.0

    # Etapa 3 — componentes
    c_portfolio = W["portfolio"] * min(1.0, best_strength / sat.get("portfolio", 1.6)) * fit
    s_strength = 0.0
    seen_s: set[str] = set()
    for m in support_matches:
        if m.term.text not in seen_s:
            seen_s.add(m.term.text)
            s_strength += m.term.weight
    tech_context = min(1.0, best_strength / 0.5)
    c_support = W["support"] * min(1.0, s_strength / sat.get("support", 1.5)) * tech_context
    vend_factor = max((COVERAGE_FACTOR.get(v["cobertura"], 0.6) for v in vendors.values()), default=0.0)
    c_vendor = W["vendor"] * vend_factor * min(1.0, tech_context + 0.5)

    tech_max = W["portfolio"] + W["support"] + W["vendor"]
    tech_ratio = (c_portfolio + c_support + c_vendor) / tech_max
    tech_factor = min(1.0, tech_ratio / float(raw.get("technical_factor_full_at", 0.55)))

    if value and value > 0:
        vf = next((b["factor"] for b in raw.get("value_bands", []) if value >= b["min"]), 0.0)
    else:
        vf = float(raw.get("value_unknown_factor", 0.3))
    tf = float((raw.get("timing_by_stage") or {}).get(stage or "", 0.5))
    c_value = W["value"] * vf * tech_factor
    c_timing = W["timing"] * tf * tech_factor

    has_strong = any(lvl in ("strong", "medium") for lvl in best_level.values())
    evid_n = sum([has_strong, s_strength > 0, bool(vendors), has_items, bool(value and value > 0)])
    c_evidence = W["evidence"] * evid_n / 5 * min(1.0, tech_context)

    total = c_portfolio + c_support + c_vendor + c_value + c_timing + c_evidence
    alertas: list[str] = []
    if not has_strong:
        total = min(total, float(raw.get("cap_without_strong_evidence", 35)))
    if primary_out_of_scope:
        # o objeto principal (primeiro item citado) está fora do escopo TLS
        total = min(total, float(raw.get("cap_primary_out_of_scope", 45)))
        alertas.append("Objeto principal fora do escopo TLS; termos de infraestrutura aparecem como acessórios.")

    # tipo de serviço e relação com o TLS
    if best is None or best_strength < 0.5:
        tipo = "servico_ti_generico" if pen_terms else "sem_aderencia"
    elif best == "software_terceiros" and s_strength >= 0.5:
        tipo = "software_suporte"
    elif acq and s_strength >= 0.5:
        tipo = "aquisicao_com_garantia"
    elif acq:
        tipo = "aquisicao_hardware"
    elif s_strength >= 0.5:
        tipo = "suporte_manutencao"
    else:
        tipo = "infraestrutura_geral"
    relacao = {"suporte_manutencao": "direta", "software_suporte": "direta",
               "aquisicao_com_garantia": "indireta", "aquisicao_hardware": "indireta",
               "infraestrutura_geral": "a_validar"}.get(tipo, "sem")
    via_parceiro = tipo in ("aquisicao_com_garantia", "aquisicao_hardware")

    # ofertas sugeridas
    comb = raw.get("combination") or {}
    sugeridas: list[str] = []
    if best and best_strength >= 0.5:
        sugeridas.append(best)
        for k in ranked[1:]:
            if eff(k) >= 0.5 and k not in sugeridas:
                sugeridas.append(k)
        if tipo == "suporte_manutencao" and best in comb.get("support_implies_mvs_for", []) and "mvs" not in sugeridas:
            sugeridas.append("mvs")
        if via_parceiro and best in comb.get("acquisition_implies_refresh_for", []) and "hardware_refresh" not in sugeridas:
            sugeridas.append("hardware_refresh")
    sugeridas = sugeridas[:4]

    for v in vendors.values():
        if v["nota"]:
            alertas.append(f"{v['nome']}: {v['nota']}")
        if v["cobertura"] == "validar":
            alertas.append(f"{v['nome']}: cobertura TLS não confirmada — validar com a área de ofertas.")
    if pen_terms and best_strength >= 0.5:
        alertas.append("Objeto também cita itens fora do escopo TLS: " + ", ".join(pen_terms[:5]) + ".")

    # evidências (somente termos realmente encontrados)
    evid: list[dict[str, str]] = []
    used: set[str] = set()
    for m in sorted(offer_matches, key=lambda x: -x.term.weight) + support_matches:
        key = m.term.text
        if key in used:
            continue
        used.add(key)
        evid.append({"termo": _original(original, idx, m.start, m.end),
                     "categoria": "servico" if m.term.category == "support" else m.term.category,
                     "forca": m.term.level or "strong",
                     "trecho": _snippet(original, idx, m.start, m.end)})
    for v in vendors.values():
        evid.append({"termo": v["termo"], "categoria": "fabricante", "forca": v["cobertura"], "trecho": ""})

    score = int(round(max(0.0, min(100.0, total))))
    faixa = pf.faixa(score)
    just = _justificativa(pf, sugeridas, tipo, evid, vendors, score)
    return {
        "score": score,
        "faixa": faixa,
        "score_tecnico": int(round(100 * (c_portfolio + c_support + c_vendor + c_evidence) / (tech_max + W["evidence"]))),
        "score_comercial": int(round(100 * (c_value + c_timing) / (W["value"] + W["timing"]))),
        "componentes": {k: round(v, 1) for k, v in {
            "portfolio": c_portfolio, "suporte": c_support, "fabricante": c_vendor,
            "valor": c_value, "estagio": c_timing, "evidencias": c_evidence}.items()},
        "oferta_principal": pf.offer_label(sugeridas[0]) if sugeridas else None,
        "ofertas": [pf.offer_label(k) for k in sugeridas],
        "ofertas_chave": sugeridas,
        "fabricantes": [{k: v[k] for k in ("nome", "cobertura", "nota")} for v in vendors.values()],
        "tipo_servico": tipo,
        "tipo_servico_label": (raw.get("service_types") or {}).get(tipo, tipo),
        "relacao": relacao,
        "via_parceiro": via_parceiro,
        "evidencias": evid[:12],
        "justificativa": just,
        "alertas": alertas,
        "validacao_comercial": True,
    }


def _justificativa(pf: Portfolio, offers: list[str], tipo: str, evid: list[dict], vendors: dict, score: int) -> str:
    if not offers:
        if tipo == "servico_ti_generico":
            return "Serviço de TI genérico, sem evidência concreta de aderência ao portfólio TLS."
        return "Sem evidência suficiente de aderência ao portfólio TLS."
    names = "/".join(pf.offer_label(o).split(" — ")[0] for o in offers[:3])
    termos = [e["termo"].strip() for e in evid if e["categoria"] != "fabricante"][:6]
    parts = [f"Possível aderência a {names}: objeto menciona " + ", ".join(f"“{t}”" for t in termos)]
    if vendors:
        parts[0] += "; fabricante(s): " + ", ".join(vendors)
    parts[0] += "."
    label = (pf.raw.get("service_types") or {}).get(tipo)
    if label:
        parts.append(label + ".")
    if tipo in ("aquisicao_com_garantia", "aquisicao_hardware"):
        parts.append("Oportunidade indireta — possível atuação via parceiro licitante.")
    return " ".join(parts)
