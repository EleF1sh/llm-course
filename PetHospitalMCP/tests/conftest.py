from __future__ import annotations

import pytest

from pet_hospital_mcp.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        pet_hospital_base_url="http://pet-hospital.test",
        mcp_host="127.0.0.1",
        mcp_port=8100,
        request_timeout_s=1.0,
        max_retries=1,
        retry_backoff_s=0.01,
    )
