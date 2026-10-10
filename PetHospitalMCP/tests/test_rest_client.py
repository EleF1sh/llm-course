from __future__ import annotations

import httpx
import pytest
import respx

from pet_hospital_mcp.errors import AdapterError, ErrorEnvelope
from pet_hospital_mcp.rest_client import PetHospitalClient
from pet_hospital_mcp.tools.list_pets import run_list_pets
from helpers import SAMPLE_PET, list_payload


@pytest.mark.asyncio
@respx.mock
async def test_forwards_all_query_params(settings) -> None:
    route = respx.get("http://pet-hospital.test/api/v1/pets").mock(
        return_value=httpx.Response(200, json=list_payload())
    )
    client = PetHospitalClient(settings)
    try:
        result = await run_list_pets(
            client,
            {
                "q": "肠胃炎",
                "name": "旺财",
                "ownerName": "张三",
                "ownerPhone": "13800001111",
                "species": "犬",
                "doctor": "李医生",
                "disease": "肠胃炎",
                "status": "已康复",
                "min": 10,
                "max": 900,
                "sortBy": "totalCost",
                "order": "desc",
                "page": 3,
                "pageSize": 15,
            },
        )
    finally:
        await client.aclose()

    assert not isinstance(result, ErrorEnvelope)
    assert result.items[0].id == SAMPLE_PET["id"]
    assert route.called
    request = route.calls.last.request
    assert str(request.url.path) == "/api/v1/pets"
    qs = dict(request.url.params)
    assert qs == {
        "q": "肠胃炎",
        "name": "旺财",
        "ownerName": "张三",
        "ownerPhone": "13800001111",
        "species": "犬",
        "doctor": "李医生",
        "disease": "肠胃炎",
        "status": "已康复",
        "min": "10.0",
        "max": "900.0",
        "sortBy": "totalCost",
        "order": "desc",
        "page": "3",
        "pageSize": "15",
    }


@pytest.mark.asyncio
@respx.mock
async def test_backend_4xx_and_5xx(settings) -> None:
    respx.get("http://pet-hospital.test/api/v1/pets").mock(
        return_value=httpx.Response(400, json={"message": "bad"})
    )
    client = PetHospitalClient(settings)
    try:
        result = await run_list_pets(client, {"page": 1})
    finally:
        await client.aclose()
    assert isinstance(result, ErrorEnvelope)
    assert result.error.code == "BACKEND_API_ERROR"

    respx.get("http://pet-hospital.test/api/v1/pets").mock(
        return_value=httpx.Response(503, text="down")
    )
    client = PetHospitalClient(settings)
    try:
        result = await run_list_pets(client, {"page": 1})
    finally:
        await client.aclose()
    assert isinstance(result, ErrorEnvelope)
    assert result.error.code == "BACKEND_API_ERROR"


@pytest.mark.asyncio
@respx.mock
async def test_timeout_and_connection_errors(settings) -> None:
    respx.get("http://pet-hospital.test/api/v1/pets").mock(
        side_effect=httpx.TimeoutException("slow")
    )
    client = PetHospitalClient(settings)
    try:
        result = await run_list_pets(client, {"page": 1})
    finally:
        await client.aclose()
    assert isinstance(result, ErrorEnvelope)
    assert result.error.code == "BACKEND_TIMEOUT"

    respx.get("http://pet-hospital.test/api/v1/pets").mock(
        side_effect=httpx.ConnectError("nope")
    )
    client = PetHospitalClient(settings)
    try:
        result = await run_list_pets(client, {"page": 1})
    finally:
        await client.aclose()
    assert isinstance(result, ErrorEnvelope)
    assert result.error.code == "BACKEND_UNAVAILABLE"


@pytest.mark.asyncio
@respx.mock
async def test_invalid_json_and_schema(settings) -> None:
    respx.get("http://pet-hospital.test/api/v1/pets").mock(
        return_value=httpx.Response(200, text="not-json")
    )
    client = PetHospitalClient(settings)
    try:
        result = await run_list_pets(client, {"page": 1})
    finally:
        await client.aclose()
    assert isinstance(result, ErrorEnvelope)
    assert result.error.code == "BACKEND_INVALID_RESPONSE"

    respx.get("http://pet-hospital.test/api/v1/pets").mock(
        return_value=httpx.Response(
            200,
            json={"code": 200, "message": "ok", "data": {"items": "nope"}},
        )
    )
    client = PetHospitalClient(settings)
    try:
        result = await run_list_pets(client, {"page": 1})
    finally:
        await client.aclose()
    assert isinstance(result, ErrorEnvelope)
    assert result.error.code == "BACKEND_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_null_records_and_charges_are_accepted(settings) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=list_payload(
                items=[
                    {
                        **SAMPLE_PET,
                        "records": None,
                        "charges": None,
                    }
                ]
            ),
        )
    )
    client = PetHospitalClient(settings, transport=transport)
    try:
        result = await run_list_pets(client, {"page": 1, "pageSize": 5})
    finally:
        await client.aclose()
    assert not isinstance(result, ErrorEnvelope)
    assert result.items[0].records is None
    assert result.items[0].charges is None


@pytest.mark.asyncio
async def test_validation_error_does_not_call_backend(settings) -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=list_payload())

    client = PetHospitalClient(settings, transport=httpx.MockTransport(handler))
    try:
        result = await run_list_pets(client, {"pageSize": 9999})
    finally:
        await client.aclose()
    assert isinstance(result, ErrorEnvelope)
    assert result.error.code == "VALIDATION_ERROR"
    assert called is False


@pytest.mark.asyncio
async def test_client_raises_adapter_error_type(settings) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(500, text="boom")
    )
    client = PetHospitalClient(settings, transport=transport)
    try:
        with pytest.raises(AdapterError) as exc:
            await client.list_pets({"page": 1})
        assert exc.value.code == "BACKEND_API_ERROR"
    finally:
        await client.aclose()
