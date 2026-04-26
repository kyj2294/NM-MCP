"""Phase 2 추가 API (request, shopping) 통합 테스트."""
import os
from pathlib import Path

import pytest

_API_KEY = os.getenv("NARA_API_KEY", "")
_HAS_REAL_KEY = bool(_API_KEY) and not _API_KEY.startswith("placeholder")

pytestmark = pytest.mark.skipif(not _HAS_REAL_KEY, reason="실제 NARA_API_KEY 필요")


@pytest.mark.asyncio
async def test_search_procurement_request_도메인(tmp_path, monkeypatch):
    """조달요청 검색이 정상 응답을 반환한다."""
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "p2.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    result = await server_mod.search_procurement(
        domain="request",
        business_type="용역",
        limit=5,
    )
    assert "error" not in result
    assert "items" in result
    assert isinstance(result["items"], list)


@pytest.mark.asyncio
async def test_search_procurement_shopping_도메인(tmp_path, monkeypatch):
    """종합쇼핑몰 검색이 정상 응답을 반환한다."""
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "p2s.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    result = await server_mod.search_procurement(
        domain="shopping",
        keyword="모니터",
        limit=5,
    )
    assert "error" not in result
    assert "items" in result
    assert isinstance(result["items"], list)


@pytest.mark.asyncio
async def test_get_procurement_detail_request_도메인(tmp_path, monkeypatch):
    """조달요청 상세 조회 — 실제 요청번호를 목록에서 취득해 검증한다."""
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "p2d.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    # 목록에서 첫 번째 요청번호 취득
    list_result = await server_mod.search_procurement(domain="request", business_type="용역", limit=1)
    if not list_result.get("items"):
        pytest.skip("조달요청 데이터 없음")

    req_no = list_result["items"][0].get("prcrmntReqNo")
    if not req_no:
        pytest.skip("조달요청번호 필드 없음")

    result = await server_mod.get_procurement_detail(
        domain="request",
        notice_no=req_no,
        business_type="용역",
    )
    assert "error" not in result
    assert "items" in result
    assert len(result["items"]) >= 1


@pytest.mark.asyncio
async def test_get_procurement_detail_shopping_도메인(tmp_path, monkeypatch):
    """쇼핑몰 품목 상세 조회 — 실제 품목번호를 목록에서 취득해 검증한다."""
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "p2sd.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    list_result = await server_mod.search_procurement(domain="shopping", keyword="모니터", limit=1)
    if not list_result.get("items"):
        pytest.skip("쇼핑몰 데이터 없음")

    item_id = list_result["items"][0].get("prdctIdntNo")
    if not item_id:
        pytest.skip("품목식별번호 필드 없음")

    result = await server_mod.get_procurement_detail(domain="shopping", notice_no=item_id)
    assert "error" not in result
    assert "items" in result
    assert len(result["items"]) >= 1
