"""Orquestração da coleta: incremental + carga histórica retomável + enriquecimento.

Garantias:
- Cada fonte roda isolada: a falha de uma não interrompe as demais e é registrada em meta.json.
- Cursores só avançam após uma janela (dia) ser processada COMPLETAMENTE.
- A base nunca encolhe; escrita atômica; ausência de resposta != ausência de licitações.
- Orçamento de tempo: o que não couber continua na próxima execução.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import yaml

from . import __version__
from .ofertas import BaseOfertas, OfertasError, norm as norm_ofertas
from .normalize import (STAGE_LABELS, adesao_assessment, compra_ids, normalize_ata, normalize_contratacao,
                        normalize_contrato, normalize_pca_items, portal_name, refresh_ata_vigencia,
                        restage, safe_url, vencimento)
from .pncp import CONSULTA_BASE, PNCPClient, SourceError
from .store import Store, write_json_atomic

log = logging.getLogger("radar")
TZ = ZoneInfo("America/Sao_Paulo")

LIMITACOES = [
    "Cobertura limitada ao que os órgãos publicam no PNCP. Órgãos que não publicam (ou publicam com atraso) não aparecem.",
    "ETPs e pesquisas de preço não são publicados de forma estruturada no PNCP; o estágio 'Preparação' só aparece para "
    "manifestações de interesse e pré-qualificações.",
    "PDTI/PDTIC não possuem API pública: devem ser consultados nos sites dos órgãos (módulo futuro 'Análise de Compras').",
    "A classificação usa a base de ofertas TLS (privada) sobre o objeto, a informação complementar e, quando "
    "coletados, os itens da contratação. PDFs de editais/TRs NÃO são lidos pelo sistema.",
    "Possibilidade de adesão a atas é indicativa: não há análise jurídica nem verificação de saldo.",
    "A busca opera sobre a base coletada pelo Radar (não é uma consulta em tempo real a toda a base nacional).",
]


def d2s(d: date) -> str:
    return d.strftime("%Y%m%d")


def days_between(a: date, b: date) -> Iterable[date]:
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


class Runner:
    def __init__(self, data_dir: Path, config_dir: Path, budget_min: float | None = None, backfill: bool = True,
                 ofertas: BaseOfertas | None = None):
        self.config_dir = Path(config_dir)
        self.cfg = yaml.safe_load(open(self.config_dir / "fontes.yml", encoding="utf-8"))
        self.ofertas = ofertas or carregar_ofertas()
        pc = self.cfg["pncp"]
        self.client = PNCPClient(timeout=pc.get("timeout_s", 60), max_attempts=pc.get("max_attempts", 6),
                                 min_interval=pc.get("min_interval_s", 0.3))
        self.store = Store(data_dir).load()
        self.budget_s = 60 * float(budget_min if budget_min is not None else self.cfg.get("budget_minutes", 50))
        self.t0 = time.monotonic()
        self.backfill = backfill
        self.now = datetime.now(TZ).replace(tzinfo=None)
        self.today = self.now.date()
        self.now_iso = datetime.now(TZ).isoformat(timespec="seconds")
        st = self.cfg.get("storage", {})
        self.sources: dict[str, dict[str, Any]] = dict(self.store.meta.get("fontes") or {})
        self.page_size = pc.get("page_size", 50)
        self.modalidades = pc.get("modalidades", [6])
        self._prefilter = self._build_prefilter()
        self.counters = {"vistos": 0, "novos": 0, "atualizados": 0}

    # ----------------------------------------------------------- utilidades
    def time_left(self) -> float:
        return self.budget_s - (time.monotonic() - self.t0)

    def time_left_for_bulk(self) -> float:
        """Tempo para cargas longas (histórico, varredura), reservando parte do orçamento
        para o enriquecimento (itens e documentos) e a gravação final."""
        reserve = min(15 * 60, 0.15 * self.budget_s)
        return self.time_left() - reserve

    def _build_prefilter(self) -> re.Pattern:
        """Regex única com todos os termos exatos e marcas da base de ofertas: descarta
        rapidamente os registros sem nenhuma relação (a grande maioria)."""
        return self.ofertas.prefiltro()

    def relevant_text(self, *texts: str | None) -> bool:
        return bool(self._prefilter.search(norm_ofertas(" ".join(t for t in texts if t))))

    @contextmanager
    def feed(self, name: str):
        rec = self.sources.setdefault(name, {})
        rec.update({"ultima_execucao": self.now_iso, "status": "executando", "erro": None})
        before = dict(self.counters)
        try:
            yield rec
            if rec.get("status") == "executando":
                rec["status"] = "ok"
            rec["ultimo_sucesso"] = self.now_iso if rec["status"] in ("ok", "parcial") else rec.get("ultimo_sucesso")
        except SourceError as exc:
            log.error("fonte %s falhou: %s", name, exc)
            rec["status"] = "falha"
            rec["erro"] = f"{exc} (HTTP {exc.status})" if exc.status else str(exc)
        except Exception as exc:  # noqa: BLE001 — uma fonte não derruba as demais
            log.exception("erro inesperado na fonte %s", name)
            rec["status"] = "falha"
            rec["erro"] = f"{type(exc).__name__}: {exc}"
        finally:
            rec["registros_vistos"] = self.counters["vistos"] - before["vistos"]
            rec["novos"] = self.counters["novos"] - before["novos"]
            rec["atualizados"] = self.counters["atualizados"] - before["atualizados"]
            self.store.save_state()

    def _count(self, res: str) -> None:
        if res == "new":
            self.counters["novos"] += 1
        elif res == "updated":
            self.counters["atualizados"] += 1

    # ------------------------------------------------------------ ingestão
    def ingest_contratacao(self, raw: dict, feed: str) -> None:
        self.counters["vistos"] += 1
        if raw.get("modalidadeId") not in self.modalidades:
            return
        ctrl = raw.get("numeroControlePNCP")
        known = ctrl in self.store.items
        if not known and not self.relevant_text(raw.get("objetoCompra"), raw.get("informacaoComplementar")):
            return
        item = normalize_contratacao(raw, self.now, feed)
        if not item:
            return
        if not known:
            if not self.classify_item(item)["tls"]:
                return
        self._count(self.store.upsert(self.store.items, item, self.now_iso))

    def ingest_ata(self, raw: dict) -> None:
        self.counters["vistos"] += 1
        ctrl = raw.get("numeroControlePNCPAta")
        known = ctrl in self.store.atas
        if not known and not self.relevant_text(raw.get("objetoContratacao")):
            return
        ata = normalize_ata(raw, self.today, self.cfg["pncp"].get("atas_vencimento_alerta_dias", 90))
        if not ata:
            return
        if not known:
            if not self.classify_item(ata)["tls"]:
                return
        self._count(self.store.upsert(self.store.atas, ata, self.now_iso))
        self._apply_pending_links(ata["id"])

    def ingest_contrato(self, raw: dict) -> None:
        self.counters["vistos"] += 1
        ctrl = raw.get("numeroControlePNCP")
        known = ctrl in self.store.items
        ata_id = raw.get("numeroControlePncpAta")
        rel = known or self.relevant_text(raw.get("objetoContrato"), raw.get("informacaoComplementar"))
        if not rel and not (ata_id and ata_id in self.store.atas):
            return
        ct = normalize_contrato(raw)
        if not ct:
            return
        if ata_id:
            self._link_contract_to_ata(ata_id, ct)
        if not known:
            if not self.classify_item(ct)["tls"]:
                return
        self._count(self.store.upsert(self.store.items, ct, self.now_iso))

    def _link_contract_to_ata(self, ata_id: str, ct: dict) -> None:
        link = {"contrato": ct["id"], "fornecedor": ct["fornecedor"], "fruto_adesao": ct["fruto_adesao"],
                "orgao": (ct.get("orgao") or {}).get("nome"), "valor": ct.get("valor_global"),
                "data_assinatura": ct.get("data_assinatura")}
        if ata_id in self.store.atas:
            self._attach_link(self.store.atas[ata_id], link)
        else:
            pend = self.store.state.setdefault("ata_links_pendentes", {})
            if ata_id not in pend and len(pend) >= 20000:
                pend.pop(next(iter(pend)))  # limita o tamanho do state.json (descarta o mais antigo)
            lst = pend.setdefault(ata_id, [])
            if not any(x["contrato"] == link["contrato"] for x in lst) and len(lst) < 50:
                lst.append(link)

    def _apply_pending_links(self, ata_id: str) -> None:
        pend = self.store.state.get("ata_links_pendentes") or {}
        for link in pend.pop(ata_id, []):
            self._attach_link(self.store.atas[ata_id], link)

    @staticmethod
    def _attach_link(ata: dict, link: dict) -> None:
        contratos = ata.setdefault("contratos", [])
        if any(c["contrato"] == link["contrato"] for c in contratos):
            return
        contratos.append(link)
        f = link.get("fornecedor") or {}
        if f.get("nome") and not any(x.get("ni") == f.get("ni") for x in ata.setdefault("fornecedores", [])):
            ata["fornecedores"].append({"ni": f.get("ni"), "nome": f.get("nome"), "fonte": "contrato PNCP"})
        ata["contratos_adesao"] = sum(1 for c in contratos if c.get("fruto_adesao"))

    # -------------------------------------------------------- classificação
    def classify_item(self, item: dict) -> dict:
        item["classificacao"] = c = classificar_registro(self.ofertas, item)
        return c

    def _mark_published(self, rec: dict) -> None:
        """Uma vez publicado no site (casou alguma oferta TLS), o registro só sai quando
        VENCER — nunca por reclassificação (regra de negócio pedida pelos usuários)."""
        if not rec.get("publicado_em") and (rec.get("classificacao") or {}).get("tls"):
            rec["publicado_em"] = self.now_iso

    def migrar_base_ofertas(self) -> dict[str, int]:
        """Troca de classificador (taxonomia antiga -> base de ofertas JSON): a publicação é
        redecidida UMA vez com a regra nova. Depois disso vale de novo "só sai quando vencer"."""
        st = self.store.state
        if st.get("classificador") == "ofertas_json":
            return {}
        resumo = {"mantidos": 0, "retirados": 0}
        for rec in list(self.store.items.values()) + list(self.store.atas.values()):
            if not rec.get("publicado_em"):
                continue
            if classificar_registro(self.ofertas, rec)["tls"]:
                resumo["mantidos"] += 1
            else:
                rec["publicado_em"] = None
                resumo["retirados"] += 1
        st["classificador"] = "ofertas_json"
        st["migracao_ofertas"] = {"em": self.now_iso, **resumo}
        log.info("migração para a base de ofertas JSON: %s", resumo)
        return resumo

    def reclassify_all(self) -> None:
        self.migrar_base_ofertas()
        soon = self.cfg["pncp"].get("atas_vencimento_alerta_dias", 90)
        for it in self.store.items.values():
            it["estagio"] = restage(it, self.now)
            self.classify_item(it)
            self._mark_published(it)
        for a in self.store.atas.values():
            refresh_ata_vigencia(a, self.today, soon)
            self.classify_item(a)
            self._mark_published(a)
            texts = [a.get("objeto"), (a.get("compra") or {}).get("info_complementar"),
                     (a.get("compra") or {}).get("objeto")]
            a["adesao_status"], a["adesao_motivos"] = adesao_assessment(a, texts, a.get("contratos_adesao", 0))
            esfera = (a.get("orgao") or {}).get("esfera")
            a["alerta_esfera_federal"] = esfera in ("E", "M", "D")

    # ---------------------------------------------------------------- feeds
    def _feed_deadline(self, name: str) -> float:
        """Fatia máxima do orçamento por fonte, para que uma fonte volumosa não deixe as
        demais sem tempo (o que não couber continua na próxima execução)."""
        share = float((self.cfg.get("time_shares") or {}).get(name, 1.0))
        limite = time.monotonic() + max(300.0, share * self.budget_s)
        fatia = getattr(self, "_fatia_carga", {}).get(name)
        return min(limite, fatia) if fatia else limite

    BULK_FEEDS = ("atas_varredura", "backfill_contratacoes", "backfill_contratos")

    def fatias_cargas_longas(self, restante_s: float) -> dict[str, float]:
        """Divide o tempo que sobra para as cargas longas entre elas, na proporção de
        time_shares. Antes, cada uma podia usar até sua fatia do orçamento TOTAL; como a
        varredura de atas roda primeiro, as cargas históricas nunca recebiam tempo (0%)."""
        shares = self.cfg.get("time_shares") or {}
        pesos = {n: float(shares.get(n, 0.1)) for n in self.BULK_FEEDS}
        total = sum(pesos.values()) or 1.0
        return {n: max(0.0, restante_s) * w / total for n, w in pesos.items()}

    def _daily_cursor_feed(self, name: str, fetch, ingest, lookback_default: int = 1, max_lookback: int = 30) -> None:
        """Janelas diárias de atualização a partir do cursor (com 1 dia de sobreposição)."""
        deadline = self._feed_deadline(name)
        with self.feed(name) as rec:
            st = self.store.state.setdefault(name, {})
            cur = date.fromisoformat(st["ate"]) if st.get("ate") else None
            start = max(cur - timedelta(days=1), self.today - timedelta(days=max_lookback)) if cur \
                else self.today - timedelta(days=lookback_default)
            for d in days_between(start, self.today):
                if self.time_left_for_bulk() < 60 or time.monotonic() > deadline:
                    rec["status"] = "parcial"
                    rec["erro"] = "fatia de tempo da fonte esgotada; continua na próxima execução"
                    return
                for rows in fetch(d):
                    for r in rows:
                        ingest(r)
                    if time.monotonic() > deadline + 120:
                        # dia muito volumoso: interrompe sem avançar o cursor (dia refeito depois)
                        rec["status"] = "parcial"
                        rec["erro"] = "fatia de tempo da fonte esgotada no meio do dia; será refeito"
                        return
                st["ate"] = d.isoformat()
                self.store.save_state()

    def feed_contratacoes_atualizacao(self) -> None:
        def fetch(d):
            for mod in self.modalidades:
                yield from self.client.contratacoes_atualizacao(d2s(d), d2s(d), mod)
        self._daily_cursor_feed("contratacoes_atualizacao", fetch, lambda r: self.ingest_contratacao(r, "atualizacao"))

    def feed_atas_atualizacao(self) -> None:
        self._daily_cursor_feed("atas_atualizacao", lambda d: self.client.atas_atualizacao(d2s(d), d2s(d)), self.ingest_ata)

    def feed_contratos_atualizacao(self) -> None:
        self._daily_cursor_feed("contratos_atualizacao", lambda d: self.client.contratos_atualizacao(d2s(d), d2s(d)),
                                self.ingest_contrato)

    def feed_propostas_abertas(self) -> None:
        st = self.store.state.setdefault("propostas_abertas", {})
        every = int(self.cfg["pncp"].get("propostas_snapshot_intervalo_dias", 7))
        if st.get("ultimo_snapshot") and (self.today - date.fromisoformat(st["ultimo_snapshot"][:10])).days < every:
            return  # entre snapshots, as atualizações diárias mantêm a base em dia
        deadline = self._feed_deadline("propostas_abertas")
        with self.feed("propostas_abertas") as rec:
            horizon = self.today + timedelta(days=self.cfg["pncp"].get("propostas_horizonte_dias", 365))
            n = 0
            for rows in self.client.contratacoes_proposta(d2s(horizon)):
                for r in rows:
                    self.ingest_contratacao(r, "propostas")
                n += 1
                if self.time_left_for_bulk() < 60 or time.monotonic() > deadline:
                    rec["status"] = "parcial"
                    rec["erro"] = "orçamento de tempo esgotado durante o snapshot de propostas"
                    break
            rec["paginas"] = n
            if rec.get("status") != "parcial":
                st["ultimo_snapshot"] = self.today.isoformat()

    def feed_pca(self) -> None:
        """PCA: consulta /v1/pca/ apenas nas classes CATMAT/CATSER de TIC configuradas
        (snapshot semanal). /v1/pca/atualizacao é opcional: o volume é muito alto
        (~170 mil itens/dia observados) para o limite de requisições do PNCP."""
        pca = self.cfg["pncp"].get("pca") or {}
        if not pca.get("enabled"):
            return
        anos = set(pca.get("anos") or [])
        codes = [str(c) for c in pca.get("classificacoes") or []]
        st = self.store.state.setdefault("pca", {})
        every = int(pca.get("snapshot_intervalo_dias", 7))
        due = not st.get("ultimo_snapshot") or (self.today - date.fromisoformat(st["ultimo_snapshot"][:10])).days >= every
        if not codes and not pca.get("usar_atualizacao"):
            with self.feed("pca") as rec:
                rec["status"] = "falha"
                rec["erro"] = ("nenhum código de classificação configurado (config/fontes.yml > pca.classificacoes); "
                               "rode 'python -m radar probe --pca' para descobrir as classes de TIC")
            return
        if not due and not pca.get("usar_atualizacao"):
            return
        deadline = self._feed_deadline("pca")
        with self.feed("pca") as rec:
            errors: list[str] = []
            feitos = st.setdefault("feitos", [])
            for code in codes if due else []:
                for ano in sorted(anos):
                    key = f"{code}/{ano}"
                    if key in feitos:
                        continue
                    if self.time_left_for_bulk() < 120 or time.monotonic() > deadline:
                        rec["status"] = "parcial"
                        break
                    try:
                        for rows in self.client.pca_por_classificacao(ano, code):
                            for r in rows:
                                self.ingest_pca(r, anos)
                        feitos.append(key)
                        self.store.save_state()
                    except SourceError as exc:
                        errors.append(f"classificação {key}: {exc}")
            if due and all(f"{c}/{a}" in feitos for c in codes for a in anos):
                st["ultimo_snapshot"] = self.today.isoformat()
                st["feitos"] = []
            if pca.get("usar_atualizacao"):
                stu = self.store.state.setdefault("pca_atualizacao", {})
                try:
                    cur = date.fromisoformat(stu["ate"]) if stu.get("ate") else self.today - timedelta(days=1)
                    for d in days_between(cur - timedelta(days=1), self.today):
                        if self.time_left() < 120:
                            break
                        # dataInicio == dataFim retorna 204 na API do PNCP: janela [d, d+1]
                        for rows in self.client.pca_atualizacao(d2s(d), d2s(d + timedelta(days=1))):
                            for r in rows:
                                self.ingest_pca(r, anos)
                        stu["ate"] = d.isoformat()
                        self.store.save_state()
                except SourceError as exc:
                    errors.append(f"/v1/pca/atualizacao: {exc}")
            if errors:
                rec["status"] = "parcial" if len(errors) < len(codes) * len(anos) else "falha"
                rec["erro"] = "; ".join(errors)[:600]

    def ingest_pca(self, raw: dict, anos: set[int]) -> None:
        for item in normalize_pca_items(raw, anos):
            self.counters["vistos"] += 1
            known = item["id"] in self.store.items
            if not known:
                if not self.relevant_text(item["objeto"], item.get("info_complementar")):
                    continue
                if not self.classify_item(item)["tls"]:
                    continue
            self._count(self.store.upsert(self.store.items, item, self.now_iso))

    def feed_backfill_contratacoes(self) -> None:
        days = self.cfg["pncp"].get("backfill_days", {}).get("contratacoes", 365)
        mods = self.cfg["pncp"].get("backfill_modalidades") or self.modalidades
        self._backfill("backfill_contratacoes", days, lambda d: (
            rows for mod in mods for rows in self.client.contratacoes_publicacao(d2s(d), d2s(d), mod)),
            lambda r: self.ingest_contratacao(r, "publicacao"))

    def feed_backfill_contratos(self) -> None:
        days = self.cfg["pncp"].get("backfill_days", {}).get("contratos", 90)
        self._backfill("backfill_contratos", days, lambda d: self.client.contratos(d2s(d), d2s(d)), self.ingest_contrato)

    def _backfill(self, name: str, days: int, fetch, ingest) -> None:
        deadline = self._feed_deadline(name)
        with self.feed(name) as rec:
            st = self.store.state.setdefault(name, {})
            limite = self.today - timedelta(days=days)
            st["limite"] = limite.isoformat()
            prox = date.fromisoformat(st["proximo"]) if st.get("proximo") else self.today - timedelta(days=1)
            while prox >= limite:
                if self.time_left_for_bulk() < 120 or time.monotonic() > deadline:
                    rec["status"] = "parcial"
                    rec["erro"] = None
                    break
                for rows in fetch(prox):
                    for r in rows:
                        ingest(r)
                prox -= timedelta(days=1)
                st["proximo"] = prox.isoformat()
                self.store.save_state()
            total = max(1, days)
            feitos = (self.today - timedelta(days=1) - prox).days
            st["progresso"] = round(min(100.0, 100.0 * feitos / total), 1)
            st["concluido"] = prox < limite
            rec["progresso"] = st["progresso"]

    def feed_atas_varredura(self) -> None:
        pc = self.cfg["pncp"]
        st = self.store.state.setdefault("atas_varredura", {})
        if st.get("concluida_em"):
            last = date.fromisoformat(st["concluida_em"][:10])
            if (self.today - last).days < pc.get("atas_varredura_intervalo_dias", 30):
                return
            st.clear()
        deadline = self._feed_deadline("atas_varredura")
        with self.feed("atas_varredura") as rec:
            if not st.get("data_ref"):
                st.update({"data_ref": self.today.isoformat(), "pagina": 1, "iniciada_em": self.now_iso})
            ref = d2s(date.fromisoformat(st["data_ref"]))
            page = max(1, int(st.get("pagina", 1)) - pc.get("atas_varredura_sobreposicao_paginas", 10))
            while True:
                if self.time_left_for_bulk() < 120 or time.monotonic() > deadline:
                    rec["status"] = "parcial"
                    break
                payload = self.client.get_json(f"{CONSULTA_BASE}/v1/atas", {
                    "dataInicial": ref, "dataFinal": ref, "pagina": page, "tamanhoPagina": self.page_size})
                if not payload:
                    st["concluida_em"] = self.now_iso
                    break
                for r in payload.get("data") or []:
                    self.ingest_ata(r)
                st["pagina"] = page + 1
                st["total_paginas"] = payload.get("totalPaginas")
                st["total_registros"] = payload.get("totalRegistros")
                if (payload.get("paginasRestantes") or 0) <= 0:
                    st["concluida_em"] = self.now_iso
                    break
                page += 1
                if page % 20 == 0:
                    self.store.save_state()
            tp = st.get("total_paginas") or 0
            st["progresso"] = 100.0 if st.get("concluida_em") else round(100.0 * (st.get("pagina", 1) - 1) / tp, 1) if tp else 0.0
            rec["progresso"] = st["progresso"]

    # --------------------------------------------------------- enriquecimento
    def enrich(self) -> None:
        en = self.cfg.get("enrichment", {})
        budget = int(en.get("max_requests_per_run", 1500))
        start_req = self.client.stats.requests

        def candidato(x: dict) -> bool:
            c = x.get("classificacao") or {}
            return bool(c.get("tls") or c.get("sinais"))  # casou oferta, ou ao menos cita uma marca

        def prioridade(x: dict) -> tuple:
            c = x.get("classificacao") or {}
            return (not c.get("tls"), -(c.get("pontuacao") or 0))

        with self.feed("enriquecimento") as rec:
            cands = [i for i in self.store.items.values()
                     if i["tipo"] == "contratacao" and not i.get("enriquecido_em") and candidato(i)]
            atas = [a for a in self.store.atas.values() if not a.get("enriquecido_em")
                    and a.get("vigencia_status") not in ("encerrada", "cancelada") and candidato(a)]
            # mais promissores primeiro
            cands.sort(key=prioridade)
            atas.sort(key=prioridade)
            done = 0
            for item in cands + atas:
                if self.client.stats.requests - start_req >= budget or self.time_left() < 90:
                    rec["status"] = "parcial"
                    break
                try:
                    if item["tipo"] == "contratacao":
                        self._enrich_compra(item)
                    else:
                        self._enrich_ata(item)
                    item["enriquecido_em"] = self.now_iso
                    done += 1
                except SourceError as exc:
                    item["enriquecimento_erro"] = str(exc)[:200]
            rec["enriquecidos"] = done
            rec["pendentes"] = len(cands) + len(atas) - done

    def _docs(self, rows: list[dict]) -> list[dict]:
        out = []
        for d in rows:
            if d.get("statusAtivo") is False:
                continue
            url = safe_url(d.get("url") or d.get("uri"))
            if url:
                out.append({"titulo": d.get("titulo") or d.get("tipoDocumentoNome") or "Documento",
                            "tipo": d.get("tipoDocumentoNome") or d.get("tipoDocumentoDescricao"),
                            "url": url, "data": (d.get("dataPublicacaoPncp") or "")[:10] or None})
        return out[:30]

    def _enrich_compra(self, item: dict) -> None:
        cnpj, ano, seq = item["orgao"]["cnpj"], item["ano"], item["sequencial"]
        itens = self.client.compra_itens(cnpj, ano, seq, max_pages=2)
        item["itens"] = [{"numero": i.get("numeroItem"), "descricao": (i.get("descricao") or "")[:300],
                          "quantidade": i.get("quantidade"), "unidade": i.get("unidadeMedida"),
                          "valor_total": i.get("valorTotal"), "sigiloso": bool(i.get("orcamentoSigiloso")),
                          "tipo": i.get("materialOuServicoNome"), "situacao": i.get("situacaoCompraItemNome")}
                         for i in itens[: self.cfg.get("enrichment", {}).get("max_itens_por_compra", 100)]]
        item["itens_total"] = len(itens)
        item["itens_texto"] = " | ".join(i["descricao"] for i in item["itens"])[:4000] or None
        item["orcamento_sigiloso"] = any(i["sigiloso"] for i in item["itens"]) or None
        item["documentos"] = self._docs(self.client.compra_arquivos(cnpj, ano, seq))

    def _enrich_ata(self, ata: dict) -> None:
        ids = compra_ids(ata.get("compra_id") or "")
        m = re.fullmatch(r"\d{14}-1-\d+/\d{4}-(\d+)", ata["id"])
        if ids:
            cnpj, ano, seq = ids
            det = self.client.compra_detalhe(cnpj, ano, seq) or {}
            if det:
                un = det.get("unidadeOrgao") or {}
                org = det.get("orgaoEntidade") or {}
                origem = safe_url(det.get("linkSistemaOrigem"))
                ata["orgao"]["esfera"] = org.get("esferaId")
                ata["unidade"].update({"uf": un.get("ufSigla"), "municipio": un.get("municipioNome")})
                ata["compra"] = {
                    "objeto": det.get("objetoCompra"), "info_complementar": det.get("informacaoComplementar"),
                    "modalidade": det.get("modalidadeNome"), "srp": det.get("srp"),
                    "valor": (det.get("valorTotalHomologado") or det.get("valorTotalEstimado")) or None,
                    "valor_tipo": "homologado" if det.get("valorTotalHomologado") else "estimado",
                    "numero": det.get("numeroCompra"), "processo": det.get("processo"),
                }
                ata["links"]["origem"] = origem
                ata["links"]["origem_portal"] = portal_name(origem)
            ata["documentos_compra"] = self._docs(self.client.compra_arquivos(cnpj, ano, seq))
            if m:
                ata["documentos"] = self._docs(self.client.ata_arquivos(cnpj, ano, seq, int(m.group(1))))

    # ---------------------------------------------------------------- saída
    def build_meta(self, status: str) -> None:
        items = self.store.items.values()
        atas = list(self.store.atas.values())
        st = self.store.state
        failed = [k for k, v in self.sources.items() if v.get("status") == "falha"]
        self.store.meta = {
            "app": "Radar TLS", "versao": __version__,
            "gerado_em": self.now_iso,
            "status": status if not failed else ("parcial" if status == "ok" else status),
            "fontes_com_falha": failed,
            "fontes": self.sources,
            "carga_historica": {
                "contratacoes": {k: st.get("backfill_contratacoes", {}).get(k) for k in ("proximo", "limite", "progresso", "concluido")},
                "contratos": {k: st.get("backfill_contratos", {}).get(k) for k in ("proximo", "limite", "progresso", "concluido")},
                "atas_vigentes": {k: st.get("atas_varredura", {}).get(k) for k in ("pagina", "total_paginas", "total_registros", "progresso", "concluida_em", "iniciada_em")},
            },
            "totais_base": {
                "itens": len(self.store.items),
                "contratacoes": sum(1 for i in items if i["tipo"] == "contratacao"),
                "pca": sum(1 for i in self.store.items.values() if i["tipo"] == "pca"),
                "contratos": sum(1 for i in self.store.items.values() if i["tipo"] == "contrato"),
                "atas": len(atas),
            },
            "cliente_http": self.client.stats.as_dict(),
            "duracao_s": round(time.monotonic() - self.t0, 1),
            "classificador": {"base_ofertas": "privada", "versao_ofertas": self.ofertas.versao,
                              "ofertas": len(self.ofertas.ofertas)},
            "limitacoes": LIMITACOES,
        }

    def run(self) -> int:
        status = "ok"
        # incrementais primeiro (baratos e essenciais); snapshot semanal de propostas e PCA depois
        steps = [self.feed_contratacoes_atualizacao, self.feed_atas_atualizacao, self.feed_contratos_atualizacao,
                 self.feed_propostas_abertas, self.feed_pca]
        for step in steps:
            if self.time_left() < 120:
                log.warning("orçamento de tempo esgotado antes de %s", step.__name__)
                status = "parcial"
                break
            step()
        if self.backfill and self.time_left() >= 120:
            # cargas longas: o tempo que sobra é repartido entre elas (todas avançam)
            fatias = self.fatias_cargas_longas(self.time_left_for_bulk())
            inicio = time.monotonic()
            acumulado = 0.0
            self._fatia_carga = {}
            for nome, step in (("atas_varredura", self.feed_atas_varredura),
                               ("backfill_contratacoes", self.feed_backfill_contratacoes),
                               ("backfill_contratos", self.feed_backfill_contratos)):
                acumulado += fatias[nome]
                self._fatia_carga[nome] = inicio + acumulado   # sobra de uma passa para a próxima
                step()
            self._fatia_carga = {}
        self.reclassify_all()
        self.enrich()
        self.reclassify_all()
        self.build_meta(status)
        self.store.save(self.now_iso)
        log.info("concluído: %s", json.dumps(self.store.meta["totais_base"]))
        return 0


# ---------------------------------------------------------------------- export
FIELDS_DROP = {"itens_texto", "feeds", "enriquecimento_erro"}


def _compact(item: dict) -> dict:
    out = {k: v for k, v in item.items() if k not in FIELDS_DROP}
    c = dict(out.get("classificacao") or {})
    c.pop("sinais", None)
    out["classificacao"] = c
    if out.get("itens"):
        out["itens"] = out["itens"][:40]
    return out


def classificar_registro(base: BaseOfertas, item: dict) -> dict:
    """Textos analisados: objeto/descrição, informação complementar, cada item (isolado),
    descrição do item de PCA e, para atas, o objeto/informação da contratação de origem."""
    compra = item.get("compra") or {}
    textos = [item.get("objeto"), item.get("info_complementar")]
    if item.get("tipo") == "ata":
        textos += [compra.get("objeto"), compra.get("info_complementar")]
    itens = item.get("itens") or []
    if itens:
        textos += [i.get("descricao") for i in itens]
    elif item.get("itens_texto"):
        textos += item["itens_texto"].split(" | ")
    return base.classificar(textos)


def carregar_ofertas() -> BaseOfertas:
    try:
        base = BaseOfertas.load()
    except Exception as exc:  # noqa: BLE001
        raise OfertasError(f"falha ao carregar a base de ofertas: {exc}") from exc
    if base is None:
        raise OfertasError(
            "Base de ofertas TLS não configurada. Defina RADAR_OFERTAS_FILE/RADAR_OFERTAS_JSON, coloque o arquivo em "
            "config/ofertas_tls_radar.json (não versionado) ou configure SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.")
    return base


def export_site(data_dir: Path, out_dir: Path, config_dir: Path, ofertas: BaseOfertas | None = None) -> dict[str, int]:
    """Gera os arquivos lidos pela interface. Contém a classificação TLS (derivada da base
    privada): em produção vai para o Supabase (acesso só com login), nunca para o GitHub Pages."""
    cfg = yaml.safe_load(open(Path(config_dir) / "fontes.yml", encoding="utf-8"))
    base = ofertas or carregar_ofertas()
    venc_cfg = cfg.get("vencimento", {})
    store = Store(data_dir).load()
    now = datetime.now(TZ).replace(tzinfo=None)
    removidos = {"vencidos": 0}
    for r in list(store.items.values()) + list(store.atas.values()):
        r["classificacao"] = classificar_registro(base, r)

    def keep(r: dict) -> bool:
        """Fica no site enquanto não vencer. Entra quando casa alguma oferta TLS e, depois
        disso, só sai ao vencer (a base histórica mantém tudo, inclusive os vencidos)."""
        publicado = r.get("publicado_em") or (r.get("classificacao") or {}).get("tls")
        if not publicado:
            return False
        vence_em, vencido, motivo = vencimento(r, now, venc_cfg)
        r["vence_em"], r["vence_motivo"] = vence_em, motivo
        if vencido:
            removidos["vencidos"] += 1
            return False
        return True

    items = [_compact(i) for i in store.items.values() if keep(i)]
    atas = [_compact(a) for a in store.atas.values() if keep(a)]
    out = Path(out_dir)
    lookups = {"estagios": STAGE_LABELS, **base.resumo_publico()}
    write_json_atomic(out / "opportunities.json", {"gerado_em": store.meta.get("gerado_em"), "items": items}, compact=True)
    write_json_atomic(out / "atas.json", {"gerado_em": store.meta.get("gerado_em"), "items": atas}, compact=True)
    meta = dict(store.meta)
    meta["publicado"] = {"oportunidades": len(items), "atas": len(atas), "criterio": "casou ao menos uma oferta TLS",
                         "vencidos_fora_do_site": removidos["vencidos"]}
    meta["lookups"] = lookups
    write_json_atomic(out / "meta.json", meta)
    return {"oportunidades": len(items), "atas": len(atas)}


# ------------------------------------------------------------------ comandos
def run_update(data_dir: Path, config_dir: Path, budget_min: float | None = None, backfill: bool = True) -> int:
    return Runner(data_dir, config_dir, budget_min, backfill).run()


def run_reprocess(data_dir: Path, config_dir: Path, exemplos: int = 10, seed: int = 7,
                  ofertas: BaseOfertas | None = None, salvar: bool = True) -> dict[str, Any]:
    """Reprocessa a base inteira com a base de ofertas atual (idempotente) e imprime o relatório:
    total publicado antes/depois, distribuição por portfólio e exemplos aleatórios."""
    import random
    r = Runner(data_dir, config_dir, budget_min=1, backfill=False, ofertas=ofertas)
    venc_cfg = r.cfg.get("vencimento", {})
    todos = list(r.store.items.values()) + list(r.store.atas.values())

    def no_site(rec: dict, antigo: bool) -> bool:
        if vencimento(rec, r.now, venc_cfg)[1]:
            return False
        if antigo:  # regra anterior: publicado (sticky) ou score >= 35 da taxonomia antiga
            return bool(rec.get("publicado_em") or (rec.get("classificacao") or {}).get("score", 0) >= 35)
        return bool(rec.get("publicado_em"))

    antes = sum(1 for x in todos if no_site(x, True))
    r.reclassify_all()
    depois = [x for x in todos if no_site(x, False)]
    grupos: dict[str, list[dict]] = {"logo": [], "mvs": [], "ambos": [], "transversal": []}
    for x in depois:
        pf = set((x.get("classificacao") or {}).get("portfolio") or [])
        g = "ambos" if {"logo", "mvs"} <= pf else "logo" if "logo" in pf else "mvs" if "mvs" in pf else "transversal"
        grupos[g].append(x)
    rnd = random.Random(seed)
    rel = {
        "base_total": len(todos),
        "no_site_antes": antes,
        "no_site_depois": len(depois),
        "casaram_oferta": sum(1 for x in todos if (x.get("classificacao") or {}).get("tls")),
        "por_portfolio": {k: len(v) for k, v in grupos.items()},
        "migracao": r.store.state.get("migracao_ofertas"),
        "exemplos": {k: [{"id": x["id"], "tipo": x["tipo"], "objeto": (x.get("objeto") or "")[:220],
                          "ofertas": [o["id"] for o in x["classificacao"]["ofertas_casadas"]],
                          "termos": x["classificacao"]["termos"][:8], "pontuacao": x["classificacao"]["pontuacao"],
                          "selos": [s["tipo"] for s in x["classificacao"]["selos"]]}
                         for x in rnd.sample(v, min(exemplos, len(v)))] for k, v in grupos.items()},
    }
    if salvar:
        r.store.meta["reprocessado_em"] = r.now_iso
        r.store.save(r.store.meta.get("gerado_em") or r.now_iso)
    return rel


def run_reclassify(data_dir: Path, config_dir: Path) -> int:
    r = Runner(data_dir, config_dir, budget_min=1, backfill=False)
    r.reclassify_all()
    r.store.meta["reclassificado_em"] = r.now_iso
    r.store.save(r.store.meta.get("gerado_em") or r.now_iso)
    return 0


def run_sample(config_dir: Path, days: int = 3, max_pages: int = 20, top: int = 40, out: Path | None = None) -> int:
    """Coleta real limitada (não grava a base) e imprime o ranking — usado no CI para
    validar o classificador com licitações reais."""
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="radar-sample-"))
    r = Runner(tmp, config_dir, budget_min=25, backfill=False)
    found: list[dict] = []
    for mod in (6, 4, 8, 9):
        for d in days_between(r.today - timedelta(days=days), r.today):
            try:
                for i, rows in enumerate(r.client.contratacoes_publicacao(d2s(d), d2s(d), mod)):
                    for row in rows:
                        r.ingest_contratacao(row, "publicacao")
                    if i + 1 >= max_pages:
                        break
            except SourceError as exc:
                print(f"falha modalidade {mod} {d}: {exc}")
    try:
        for i, rows in enumerate(r.client.atas_atualizacao(d2s(r.today - timedelta(days=days)), d2s(r.today))):
            for row in rows:
                r.ingest_ata(row)
            if i + 1 >= max_pages * 2:
                break
    except SourceError as exc:
        print(f"falha atas: {exc}")
    r.reclassify_all()
    found = sorted(list(r.store.items.values()) + list(r.store.atas.values()),
                   key=lambda x: -x["classificacao"]["pontuacao"])
    print(f"\nregistros vistos: {r.counters['vistos']} | casaram oferta TLS: {len(found)}")
    for x in found[:top]:
        c = x["classificacao"]
        print(f"\n[{c['pontuacao']:5.1f} {'+'.join(c['portfolio'])}] {x['tipo']} {x['id']} | {x['orgao'].get('nome')} | {x.get('estagio')}")
        print(f"   objeto: {x.get('objeto', '')[:260]}")
        print(f"   ofertas: {', '.join(o['id'] for o in c['ofertas_casadas'])} | termos: {', '.join(c['termos'])[:200]}")
        print(f"   links: {x['links']}")
    if out:
        write_json_atomic(out, {"items": found})
    print("\ncliente:", r.client.stats.as_dict())
    return 0
