import httpx
import pytest
from fastapi import HTTPException

from backend.clients import ds_client


@pytest.fixture(autouse=True)
def _reset_client():
    # Each test manages its own client state; ensure one test's client never leaks into the next.
    ds_client._client = None
    yield
    ds_client._client = None


def test_get_client_raises_when_uninitialized():
    with pytest.raises(RuntimeError, match="DS client not initialised"):
        ds_client.get_client()


def test_get_client_returns_the_initialized_client():
    client = httpx.AsyncClient()
    ds_client._client = client
    assert ds_client.get_client() is client


def _status_error(status_code: int, json_body=None, text_body: str = "") -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://ds/some-path")
    response = httpx.Response(status_code, json=json_body, text=text_body if json_body is None else None, request=request)
    return httpx.HTTPStatusError("error", request=request, response=response)


def test_raise_for_upstream_error_extracts_json_detail():
    exc = _status_error(400, json_body={"detail": "bad input"})
    with pytest.raises(HTTPException) as excinfo:
        ds_client._raise_for_upstream_error(exc)
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "bad input"


def test_raise_for_upstream_error_falls_back_to_raw_text_when_not_json():
    exc = _status_error(500, text_body="internal server error")
    with pytest.raises(HTTPException) as excinfo:
        ds_client._raise_for_upstream_error(exc)
    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "internal server error"


def test_raise_for_ds_request_error_read_timeout_maps_to_504():
    request = httpx.Request("POST", "http://ds/some-path")
    exc = httpx.ReadTimeout("timed out", request=request)
    with pytest.raises(HTTPException) as excinfo:
        ds_client.raise_for_ds_request_error(exc)
    assert excinfo.value.status_code == 504


def test_raise_for_ds_request_error_connect_error_maps_to_502():
    request = httpx.Request("POST", "http://ds/some-path")
    exc = httpx.ConnectError("connection refused", request=request)
    with pytest.raises(HTTPException) as excinfo:
        ds_client.raise_for_ds_request_error(exc)
    assert excinfo.value.status_code == 502
    assert "unreachable" in excinfo.value.detail


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, raise_exc=None):
        self.status_code = status_code
        self._payload = payload
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response=None, request_exc=None):
        self._response = response
        self._request_exc = request_exc
        self.calls = []

    async def post(self, path, json=None, **kwargs):
        self.calls.append((path, json))
        if self._request_exc:
            raise self._request_exc
        return self._response

    async def get(self, path, params=None, **kwargs):
        self.calls.append((path, params))
        if self._request_exc:
            raise self._request_exc
        return self._response


@pytest.mark.asyncio
async def test_ds_post_returns_json_on_success():
    ds_client._client = _FakeClient(response=_FakeResponse(200, payload={"ok": True}))
    result = await ds_client.ds_post("/generate", json={"a": 1})
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_ds_post_raises_http_exception_on_upstream_error():
    request = httpx.Request("POST", "http://ds/generate")
    response = httpx.Response(422, json={"detail": "validation failed"}, request=request)
    status_error = httpx.HTTPStatusError("error", request=request, response=response)
    ds_client._client = _FakeClient(response=_FakeResponse(422, raise_exc=status_error))
    with pytest.raises(HTTPException) as excinfo:
        await ds_client.ds_post("/generate")
    assert excinfo.value.status_code == 422
    assert excinfo.value.detail == "validation failed"


@pytest.mark.asyncio
async def test_ds_post_raises_http_exception_on_request_error():
    request = httpx.Request("POST", "http://ds/generate")
    ds_client._client = _FakeClient(request_exc=httpx.ConnectError("refused", request=request))
    with pytest.raises(HTTPException) as excinfo:
        await ds_client.ds_post("/generate")
    assert excinfo.value.status_code == 502


@pytest.mark.asyncio
async def test_ds_get_returns_json_on_success():
    ds_client._client = _FakeClient(response=_FakeResponse(200, payload={"items": []}))
    result = await ds_client.ds_get("/archetypes", params={"q": "x"})
    assert result == {"items": []}
