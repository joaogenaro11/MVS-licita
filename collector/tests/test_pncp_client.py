import pytest
import requests

from radar.pncp import PNCPClient, SourceError


class FakeResp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.content = b"x" if payload is not None else b""
        self.text = str(payload)
        self.url = "https://pncp.gov.br/fake"

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def client(responses):
    s = FakeSession(responses)
    return PNCPClient(session=s, sleep=lambda _x: None, min_interval=0), s


def page(n, total, rows):
    return {"data": rows, "totalPaginas": total, "numeroPagina": n, "paginasRestantes": total - n,
            "totalRegistros": 999}


def test_paginacao_completa():
    c, s = client([FakeResp(200, page(1, 3, [{"a": 1}])),
                   FakeResp(200, page(2, 3, [{"a": 2}])),
                   FakeResp(200, page(3, 3, [{"a": 3}]))])
    rows = [r for p in c.paginate("/x", {"q": 1}) for r in p]
    assert [r["a"] for r in rows] == [1, 2, 3]
    assert [call[1]["pagina"] for call in s.calls] == [1, 2, 3]


def test_204_nao_e_erro():
    c, _ = client([FakeResp(204)])
    assert list(c.paginate("/x", {})) == []
    assert c.stats.no_content == 1


def test_retry_em_503_e_timeout():
    c, s = client([FakeResp(503, {}), requests.Timeout("t"), FakeResp(200, page(1, 1, [{"a": 1}]))])
    rows = [r for p in c.paginate("/x", {}) for r in p]
    assert rows == [{"a": 1}]
    assert c.stats.retries == 2


def test_falha_definitiva_levanta_erro():
    c, _ = client([FakeResp(503, {})] * 6)
    with pytest.raises(SourceError):
        list(c.paginate("/x", {}))


def test_400_nao_repete():
    c, s = client([FakeResp(400, {"erro": "parametro"})])
    with pytest.raises(SourceError) as e:
        c.get_json("https://pncp.gov.br/x")
    assert e.value.status == 400
    assert len(s.calls) == 1


def test_json_invalido_repete():
    c, _ = client([FakeResp(200, ValueError("bad json")), FakeResp(200, page(1, 1, []))])
    assert list(c.paginate("/x", {})) == []


def test_429_desacelera_e_recupera():
    c, _ = client([FakeResp(429, {}), FakeResp(200, page(1, 1, [{"a": 1}]))])
    c.base_interval = c.min_interval = 0.5
    rows = [r for p in c.paginate("/x", {}) for r in p]
    assert rows == [{"a": 1}]
    assert c.stats.throttled == 1
    assert 0.5 < c.min_interval <= 1.0        # desacelerou e começou a recuperar
