from __future__ import annotations

import math

import pytest

from pet_hospital_mcp.errors import AdapterError
from pet_hospital_mcp.tools.list_pets import parse_list_pets_input


def test_accepts_valid_filters() -> None:
    model = parse_list_pets_input(
        {
            "q": "肠胃炎",
            "name": "旺财",
            "ownerName": "张三",
            "ownerPhone": "13800001111",
            "species": "犬",
            "doctor": "李医生",
            "disease": "肠胃炎",
            "status": "已康复",
            "min": 0,
            "max": 1000,
            "sortBy": "totalCost",
            "order": "desc",
            "page": 2,
            "pageSize": 50,
        }
    )
    assert model.species == "犬"
    assert model.page == 2
    assert model.pageSize == 50


def test_rejects_unknown_fields() -> None:
    with pytest.raises(AdapterError) as exc:
        parse_list_pets_input({"foo": "bar"})
    assert exc.value.code == "VALIDATION_ERROR"


def test_rejects_invalid_species_status_sort_order() -> None:
    with pytest.raises(AdapterError):
        parse_list_pets_input({"species": "dinosaur"})
    with pytest.raises(AdapterError):
        parse_list_pets_input({"status": "未知"})
    with pytest.raises(AdapterError):
        parse_list_pets_input({"sortBy": "weight"})
    with pytest.raises(AdapterError):
        parse_list_pets_input({"order": "sideways"})


def test_rejects_page_and_page_size_bounds() -> None:
    with pytest.raises(AdapterError):
        parse_list_pets_input({"page": 0})
    with pytest.raises(AdapterError):
        parse_list_pets_input({"pageSize": 0})
    with pytest.raises(AdapterError):
        parse_list_pets_input({"pageSize": 501})


def test_rejects_nan_infinity_and_min_max_rules() -> None:
    with pytest.raises(AdapterError):
        parse_list_pets_input({"min": math.nan})
    with pytest.raises(AdapterError):
        parse_list_pets_input({"max": math.inf})
    with pytest.raises(AdapterError):
        parse_list_pets_input({"min": -1})
    with pytest.raises(AdapterError):
        parse_list_pets_input({"min": 200, "max": 100})
