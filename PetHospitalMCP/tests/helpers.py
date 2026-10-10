from __future__ import annotations

SAMPLE_PET = {
    "id": "PET-000001",
    "name": "旺财",
    "species": "犬",
    "breed": "金毛寻回犬",
    "gender": "公",
    "ageMonths": 36,
    "color": "金黄",
    "chipNo": "CHIP-001",
    "ownerName": "张三",
    "ownerPhone": "13800001111",
    "ownerAddr": "上海市某路 1 号",
    "doctor": "李医生",
    "disease": "急性肠胃炎",
    "status": "已康复",
    "allergy": "青霉素过敏",
    "note": "",
    "records": None,
    "charges": [],
    "totalCost": 380.0,
    "visitCount": 1,
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-02T00:00:00Z",
}


def list_payload(items=None, **overrides):
    data = {
        "items": items if items is not None else [SAMPLE_PET],
        "total": 1,
        "page": 1,
        "pageSize": 20,
        "totalPages": 1,
        "totalCost": 380.0,
    }
    data.update(overrides)
    return {"code": 200, "message": "ok", "data": data, "time": "2026-01-01T00:00:00Z"}
