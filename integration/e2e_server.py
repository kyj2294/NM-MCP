"""통합 테스트 — MCP 서버 8개 도구 전체 흐름.

API 키가 없는 환경에서도 구조/상태 테스트는 실행된다.
실제 나라장터 API 호출이 필요한 테스트는 NARA_API_KEY가 설정된 경우에만 실행된다.
"""
import os
from pathlib import Path

import pytest

_API_KEY = os.getenv("NARA_API_KEY", "")
_HAS_REAL_KEY = bool(_API_KEY) and not _API_KEY.startswith("placeholder")


# ─────────────────────────────────────────────────────────────
# 모듈 로드 / 도구 등록 (API 키 불필요)
# ─────────────────────────────────────────────────────────────
def test_server_모듈_정상_로드():
    from narajangteo_pro import server

    assert server.mcp is not None
    assert server.mcp.name == "narajangteo-pro"


@pytest.mark.asyncio
async def test_8개_도구가_모두_등록():
    from narajangteo_pro import server

    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        "search_procurement",
        "get_procurement_detail",
        "trace_procurement_lifecycle",
        "analyze_market",
        "analyze_competitor",
        "score_bid_fit",
        "manage_watchlist",
        "manage_company_profile",
    }
    assert names == expected


@pytest.mark.asyncio
async def test_도구_스키마에_한국어_설명_포함():
    from narajangteo_pro import server

    tools = await server.mcp.list_tools()
    by_name = {t.name: t for t in tools}

    lifecycle = by_name["trace_procurement_lifecycle"]
    assert "⭐" in (lifecycle.description or "")
    assert "사전규격" in (lifecycle.description or "")

    search = by_name["search_procurement"]
    assert "자연어" in (search.description or "") or "최근" in (search.description or "")


# ─────────────────────────────────────────────────────────────
# 실제 API 호출 테스트
# ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.skipif(not _HAS_REAL_KEY, reason="실제 NARA_API_KEY 필요")
async def test_search_procurement_입찰공고_검색(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "state.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    result = await server_mod.search_procurement(
        domain="bid",
        business_type="용역",
        limit=5,
    )
    assert "error" not in result
    assert "items" in result
    assert isinstance(result["items"], list)


@pytest.mark.asyncio
@pytest.mark.skipif(not _HAS_REAL_KEY, reason="실제 NARA_API_KEY 필요")
async def test_search_procurement_자연어_업무구분_매핑(tmp_path, monkeypatch):
    """'서비스' → '용역'으로 정규화되어 API가 정상 응답한다."""
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "state.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    result = await server_mod.search_procurement(domain="bid", business_type="서비스")
    assert "error" not in result
    assert "items" in result


# ─────────────────────────────────────────────────────────────
# 상태 관리 테스트 (API 키 불필요)
# ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_manage_watchlist_라이프사이클(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "wl.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    add = await server_mod.manage_watchlist(action="add", keyword="클라우드", business_type="용역")
    assert add["watch_id"] > 0
    wid = add["watch_id"]

    lst = await server_mod.manage_watchlist(action="list")
    assert lst["count"] == 1
    assert lst["watches"][0]["keyword"] == "클라우드"

    rm = await server_mod.manage_watchlist(action="remove", watch_id=wid)
    assert rm["success"] is True

    lst2 = await server_mod.manage_watchlist(action="list")
    assert lst2["count"] == 0


@pytest.mark.asyncio
async def test_manage_company_profile_저장_로드(tmp_path, monkeypatch):
    """자연어 매출 입력 → 저장 → 로드 시 한국어 포맷."""
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "p.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    save = await server_mod.manage_company_profile(
        action="save",
        profile_id="acme",
        name="ACME",
        licenses=["소프트웨어개발업"],
        revenue="10억",
        prior_contracts=[{"name": "AI 프로젝트", "category": "AI"}],
    )
    assert save["revenue_formatted"] == "10억원"

    load = await server_mod.manage_company_profile(action="load", profile_id="acme")
    assert load["profile"]["revenue"] == 1_000_000_000
    assert load["profile"]["revenue_formatted"] == "10억원"
    assert "소프트웨어개발업" in load["profile"]["licenses"]


@pytest.mark.asyncio
async def test_score_bid_fit_프로필_없으면_안내_메시지(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "fit.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    result = await server_mod.score_bid_fit(bid_notice_no="20260415001", business_type="용역")
    assert "error" in result
    assert "프로필" in result["error"]


@pytest.mark.asyncio
@pytest.mark.skipif(not _HAS_REAL_KEY, reason="실제 NARA_API_KEY 필요")
async def test_score_bid_fit_inline_profile로_평가(tmp_path, monkeypatch):
    """inline_profile 제공 시 실제 API에서 공고 상세를 가져와 적합도를 산출한다."""
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "fit2.db"))

    import importlib
    import narajangteo_pro.server as server_mod
    importlib.reload(server_mod)

    # 실제 공고 목록에서 첫 번째 공고번호 취득
    from narajangteo_pro.api import bid as bid_api
    from narajangteo_pro.api.client import NaraClient
    from narajangteo_pro.config import Settings

    settings = Settings.load()
    async with NaraClient(settings) as client:
        list_result = await bid_api.search_bid_list(client, "용역", num_of_rows=1)

    if not list_result["items"]:
        pytest.skip("공고 데이터 없음")

    bid_no = list_result["items"][0]["bidNtceNo"]

    result = await server_mod.score_bid_fit(
        bid_notice_no=bid_no,
        business_type="용역",
        inline_profile={
            "licenses": ["소프트웨어개발업"],
            "revenue": 5_000_000_000,
            "prior_contracts": [{"name": "AI 챗봇 개발", "category": "AI"}],
        },
    )
    assert "total_score" in result
    assert "recommendation" in result
    assert 0 <= result["total_score"] <= 100
    assert result["recommendation"] in ["강력추천", "검토 권장", "신중 검토", "비추천"]
