"""Cliente HTTP para as APIs públicas do PNCP.

- API de Consulta:   https://pncp.gov.br/api/consulta   (swagger: /swagger-ui/index.html)
- API PNCP (leitura pública usada pelo próprio portal): https://pncp.gov.br/api/pncp

Responsabilidades:
- Retry com backoff exponencial (429, 5xx, timeouts, erros de conexão).
- Paginação completa (totalPaginas / paginasRestantes).
- HTTP 204 = página sem conteúdo (resposta válida, NÃO é erro).
- Falha definitiva levanta SourceError: o chamador NUNCA deve tratar falha como
  "não há licitações".
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests

log = logging.getLogger(__name__)

CONSULTA_BASE = "https://pncp.gov.br/api/consulta"
PNCP_BASE = "https://pncp.gov.br/api/pncp"

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class SourceError(RuntimeError):
    """Falha definitiva ao consultar a fonte (após todas as tentativas)."""

    def __init__(self, message: str, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url


@dataclass
class ClientStats:
    requests: int = 0
    retries: int = 0
    failures: int = 0
    no_content: int = 0
    throttled: int = 0
    by_status: dict[int, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "retries": self.retries,
            "failures": self.failures,
            "no_content": self.no_content,
            "limitadas_429": self.throttled,
            "by_status": {str(k): v for k, v in sorted(self.by_status.items())},
        }


class PNCPClient:
    def __init__(
        self,
        timeout: float = 60.0,
        max_attempts: int = 6,
        backoff_base: float = 2.0,
        backoff_max: float = 90.0,
        min_interval: float = 0.25,
        user_agent: str = "RadarTLS/1.0 (+https://github.com; coleta de dados abertos)",
        session: requests.Session | None = None,
        sleep=time.sleep,
    ):
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.min_interval = min_interval
        self.base_interval = min_interval
        self.max_interval = 8.0
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        self.stats = ClientStats()
        self._sleep = sleep
        self._last_request = 0.0

    # ------------------------------------------------------------------ core
    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            self._sleep(wait)
        self._last_request = time.monotonic()

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any | None:
        """GET com retry. Retorna JSON, ou None para HTTP 204 (sem conteúdo)."""
        last_exc: Exception | None = None
        status: int | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._throttle()
            self.stats.requests += 1
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                status = resp.status_code
                self.stats.by_status[status] = self.stats.by_status.get(status, 0) + 1
                if status == 204:
                    self.stats.no_content += 1
                    return None
                if status == 200:
                    # recupera a velocidade aos poucos após limitação (429)
                    self.min_interval = max(self.base_interval, self.min_interval * 0.97)
                    if not resp.content:
                        self.stats.no_content += 1
                        return None
                    return resp.json()
                if status == 429:
                    # limite de requisições do PNCP: desacelera de forma adaptativa
                    self.min_interval = min(self.max_interval, max(self.min_interval * 1.6, self.base_interval * 2, 1.0))
                    self.stats.throttled += 1
                if status in RETRY_STATUS:
                    last_exc = SourceError(f"HTTP {status}", status=status, url=resp.url)
                    retry_after = resp.headers.get("Retry-After")
                    delay = self._delay(attempt, retry_after)
                else:
                    # 4xx não-transitório: erro de parâmetro/contrato. Não insistir.
                    body = resp.text[:300].replace("\n", " ")
                    self.stats.failures += 1
                    raise SourceError(f"HTTP {status}: {body}", status=status, url=resp.url)
            except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
                # ValueError: JSON inválido (resposta truncada / página de erro HTML)
                last_exc = exc
                delay = self._delay(attempt, None)
            if attempt < self.max_attempts:
                self.stats.retries += 1
                log.warning("tentativa %d/%d falhou (%s) %s params=%s; aguardando %.1fs",
                            attempt, self.max_attempts, last_exc, url, params, delay)
                self._sleep(delay)
        self.stats.failures += 1
        raise SourceError(f"falha após {self.max_attempts} tentativas: {last_exc}", status=status, url=url)

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.backoff_max)
            except ValueError:
                pass
        base = min(self.backoff_base ** attempt, self.backoff_max)
        return base * (0.75 + random.random() * 0.5)

    # ------------------------------------------------------------ pagination
    def paginate(self, path: str, params: dict[str, Any], page_size: int = 50,
                 base: str = CONSULTA_BASE, max_pages: int | None = None) -> Iterator[list[dict]]:
        """Itera página a página. Levanta SourceError se qualquer página falhar,
        para que o chamador não avance o checkpoint com dados incompletos."""
        page = 1
        total_pages = None
        while True:
            q = dict(params, pagina=page, tamanhoPagina=page_size)
            payload = self.get_json(f"{base}{path}", q)
            if payload is None:
                return
            data, total_pages = _extract_page(payload, total_pages)
            if data:
                yield data
            if max_pages and page >= max_pages:
                return
            remaining = payload.get("paginasRestantes") if isinstance(payload, dict) else None
            if remaining is not None:
                if remaining <= 0:
                    return
            elif total_pages is None or page >= total_pages or not data:
                return
            page += 1

    # ------------------------------------------------------------ endpoints
    def contratacoes_publicacao(self, data_ini: str, data_fim: str, modalidade: int, **kw):
        p = {"dataInicial": data_ini, "dataFinal": data_fim, "codigoModalidadeContratacao": modalidade}
        return self.paginate("/v1/contratacoes/publicacao", _merge(p, kw))

    def contratacoes_atualizacao(self, data_ini: str, data_fim: str, modalidade: int, **kw):
        p = {"dataInicial": data_ini, "dataFinal": data_fim, "codigoModalidadeContratacao": modalidade}
        return self.paginate("/v1/contratacoes/atualizacao", _merge(p, kw))

    def contratacoes_proposta(self, data_fim: str, modalidade: int | None = None, **kw):
        p: dict[str, Any] = {"dataFinal": data_fim}
        if modalidade is not None:
            p["codigoModalidadeContratacao"] = modalidade
        return self.paginate("/v1/contratacoes/proposta", _merge(p, kw))

    def atas(self, data_ini: str, data_fim: str, **kw):
        return self.paginate("/v1/atas", _merge({"dataInicial": data_ini, "dataFinal": data_fim}, kw))

    def atas_atualizacao(self, data_ini: str, data_fim: str, **kw):
        return self.paginate("/v1/atas/atualizacao", _merge({"dataInicial": data_ini, "dataFinal": data_fim}, kw))

    def contratos(self, data_ini: str, data_fim: str, **kw):
        return self.paginate("/v1/contratos", _merge({"dataInicial": data_ini, "dataFinal": data_fim}, kw))

    def contratos_atualizacao(self, data_ini: str, data_fim: str, **kw):
        return self.paginate("/v1/contratos/atualizacao", _merge({"dataInicial": data_ini, "dataFinal": data_fim}, kw))

    def pca_atualizacao(self, data_ini: str, data_fim: str, **kw):
        return self.paginate("/v1/pca/atualizacao", _merge({"dataInicio": data_ini, "dataFim": data_fim}, kw))

    def pca_por_classificacao(self, ano: int, codigo_classificacao_superior: str, **kw):
        p = {"anoPca": ano, "codigoClassificacaoSuperior": codigo_classificacao_superior}
        return self.paginate("/v1/pca/", _merge(p, kw))

    # Detalhes (API PNCP de leitura pública)
    def compra_detalhe(self, cnpj: str, ano: int, seq: int) -> dict | None:
        return self.get_json(f"{CONSULTA_BASE}/v1/orgaos/{cnpj}/compras/{ano}/{seq}")

    def compra_itens(self, cnpj: str, ano: int, seq: int, page_size: int = 50, max_pages: int = 4) -> list[dict]:
        out: list[dict] = []
        for page in range(1, max_pages + 1):
            data = self.get_json(f"{PNCP_BASE}/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens",
                                 {"pagina": page, "tamanhoPagina": page_size})
            if not data:
                break
            rows = data if isinstance(data, list) else data.get("data") or []
            out.extend(rows)
            if len(rows) < page_size:
                break
        return out

    def compra_item_resultados(self, cnpj: str, ano: int, seq: int, numero_item: int) -> list[dict]:
        data = self.get_json(f"{PNCP_BASE}/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens/{numero_item}/resultados")
        return data if isinstance(data, list) else (data or {}).get("data", []) if data else []

    def compra_arquivos(self, cnpj: str, ano: int, seq: int) -> list[dict]:
        data = self.get_json(f"{PNCP_BASE}/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos")
        return data if isinstance(data, list) else []

    def ata_arquivos(self, cnpj: str, ano: int, seq: int, seq_ata: int) -> list[dict]:
        data = self.get_json(f"{PNCP_BASE}/v1/orgaos/{cnpj}/compras/{ano}/{seq}/atas/{seq_ata}/arquivos")
        return data if isinstance(data, list) else []


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _extract_page(payload: Any, total_pages: int | None) -> tuple[list[dict], int | None]:
    if isinstance(payload, list):
        return payload, 1
    if not isinstance(payload, dict):
        raise SourceError(f"formato inesperado: {type(payload).__name__}")
    data = payload.get("data")
    if data is None:
        data = payload.get("content") or []
    tp = payload.get("totalPaginas", total_pages)
    return data, tp
