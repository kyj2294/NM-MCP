"""api/client 통합 테스트 — 실제 나라장터 API 호출."""
import os
from pathlib import Path

import pytest

from narajangteo_pro.api.client import NaraAPIError, NaraClient
from narajangteo_pro.config import Settings

_API_KEY = os.getenv("NARA_API_KEY", "")
_HAS_REAL_KEY = bool(_API_KEY) and not _API_KEY.startswith("placeholder")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    if not _HAS_REAL_KEY:
        pytest.skip("실제 NARA_API_KEY 환경변수 필요")
    return Settings(
        api_key=_API_KEY,
        transport="stdio",
        http_host="0.0.0.0",
        http_port=8000,
        state_db_path=tmp_path / "state.db",
        cache_ttl=300,
        log_level="INFO",
    )


# ─────────────────────────────────────────────────────────────
# 응답 구조 검증
# ─────────────────────────────────────────────────────────────
async def test_응답이_정규화된_구조로_반환(settings):
    """실제 API 응답이 items 리스트 / total_count int 구조로 정규화된다."""
    async with NaraClient(settings) as client:
        result = await client.call(
            "bid",
            "getBidPblancListInfoServcPPSSrch",
            {"numOfRows": "5", "pageNo": "1"},
        )
    assert isinstance(result["items"], list)
    assert isinstance(result["total_count"], int)
    assert result["page_no"] == 1


# ─────────────────────────────────────────────────────────────
# 캐시
# ─────────────────────────────────────────────────────────────
async def test_같은_요청은_캐시_히트(settings):
    """동일 파라미터 재호출 시 캐시된 결과와 동일."""
    params = {"numOfRows": "3", "pageNo": "1"}
    async with NaraClient(settings) as client:
        r1 = await client.call("bid", "getBidPblancListInfoServcPPSSrch", params)
        r2 = await client.call("bid", "getBidPblancListInfoServcPPSSrch", params)
    assert r1 == r2


async def test_파라미터_다르면_다른_응답(settings):
    """pageNo가 다르면 각각 정상 응답을 반환한다."""
    async with NaraClient(settings) as client:
        r1 = await client.call(
            "bid", "getBidPblancListInfoServcPPSSrch", {"numOfRows": "3", "pageNo": "1"}
        )
        r2 = await client.call(
            "bid", "getBidPblancListInfoServcPPSSrch", {"numOfRows": "3", "pageNo": "2"}
        )
    assert isinstance(r1["items"], list)
    assert isinstance(r2["items"], list)


# ─────────────────────────────────────────────────────────────
# 에러 처리
# ─────────────────────────────────────────────────────────────
async def test_잘못된_서비스키면_NaraAPIError(tmp_path):
    """유효하지 않은 API 키로 호출하면 NaraAPIError가 발생한다."""
    bad = Settings(
        api_key="INVALID_SERVICE_KEY_00000",
        transport="stdio",
        http_host="0.0.0.0",
        http_port=8000,
        state_db_path=tmp_path / "bad.db",
        cache_ttl=300,
        log_level="INFO",
    )
    async with NaraClient(bad) as client:
        with pytest.raises(NaraAPIError):
            await client.call(
                "bid",
                "getBidPblancListInfoServcPPSSrch",
                {"numOfRows": "1", "pageNo": "1"},
            )
