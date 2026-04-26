"""narajangteo-pro MCP 서버 엔트리포인트.

8개 통합 도구로 6개 나라장터 API + 분석 + 상태 관리를 제공.

도구 설계 철학: "적게, 깊게"
- domain 파라미터로 비슷한 패턴 통합 (korean-law-mcp 교훈)
- 도구 30개 → 8개로 압축 → LLM 컨텍스트 절약
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .analytics.fit_scorer import score_bid_fit as _score_bid_fit
from .analytics.market import analyze_competitor as _analyze_competitor
from .analytics.market import analyze_market as _analyze_market
from .api import bid as bid_api
from .api import lifecycle as lifecycle_api
from .api.client import NaraAPIError, NaraClient
from .config import Settings
from .storage.db import StateStore
from .utils.nl_mapping import (
    format_money,
    normalize_business_type,
    parse_money,
    parse_relative_date_range,
)

# ─────────────────────────────────────────────────────────────
# 부트스트랩
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("narajangteo_pro")

# API 키가 없으면 설정 마법사를 띄워 입력받는다.
from .setup_wizard import ensure_api_key
ensure_api_key()

# 환경설정 로드 (실패 시 명확한 에러)
try:
    SETTINGS = Settings.load()
except RuntimeError as e:
    # MCP 서버는 stderr로만 로그가 흐르므로 명확히 출력
    import sys
    print(f"[narajangteo-pro] 설정 오류: {e}", file=sys.stderr)
    raise

logging.basicConfig(level=SETTINGS.log_level)

# 상태 저장소 초기화
STORE = StateStore(SETTINGS.state_db_path)

# MCP 서버 인스턴스
mcp = FastMCP("narajangteo-pro")


# ─────────────────────────────────────────────────────────────
# 헬퍼: 클라이언트 컨텍스트 매니저
# ─────────────────────────────────────────────────────────────
async def _with_client(coro_factory):
    """API 클라이언트 라이프사이클 관리.

    Usage:
        return await _with_client(lambda c: bid_api.search_bid_list(c, ...))
    """
    async with NaraClient(SETTINGS) as client:
        return await coro_factory(client)


# ─────────────────────────────────────────────────────────────
# Tool 1: search_procurement (검색 통합)
# ─────────────────────────────────────────────────────────────
@mcp.tool()
async def search_procurement(
    domain: Literal["bid", "award", "contract", "request", "shopping"] = "bid",
    business_type: str = "용역",
    keyword: str | None = None,
    institution: str | None = None,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """나라장터 통합 검색 도구.

    하나의 도구로 5개 영역을 모두 검색한다.

    Args:
        domain: 검색 영역
            - 'bid': 입찰공고
            - 'award': 낙찰결과
            - 'contract': 체결된 계약
            - 'request': 조달요청 (발주의 가장 이른 단계 — 영업 선행지표)
            - 'shopping': 종합쇼핑몰 품목 (단가계약 등록 품목)
        business_type: 업무구분 — '물품', '용역', '공사', '외자' (자연어 표현 자동 매핑)
            'shopping' 도메인은 이 파라미터를 무시.
        keyword: 공고명/품목명 키워드
        institution: 발주기관/계약기관명 (shopping에선 공급업체명으로 사용)
        period: 자연어 기간 — '최근 7일', '지난 3개월', '올해' 등 (date_from/to보다 우선)
        date_from: 시작일 YYYYMMDD
        date_to: 종료일 YYYYMMDD
        limit: 최대 결과 수 (1-100)

    Returns:
        {"items": [...], "total_count": int, "page_no": int}
    """
    # shopping 도메인은 업무구분이 없음 — 별도 처리
    if domain == "shopping":
        limit = max(1, min(100, limit))
        try:
            from .api import shopping as shopping_api
            return await _with_client(
                lambda c: shopping_api.search_shopping_items(
                    c,
                    keyword=keyword,
                    company_name=institution,  # 종합쇼핑몰에선 institution을 공급업체명으로
                    num_of_rows=limit,
                )
            )
        except NaraAPIError as e:
            return {"error": str(e), "code": e.code}

    # 자연어 정규화
    bt = normalize_business_type(business_type) or "용역"

    # 자연어 기간 처리
    if period:
        parsed = parse_relative_date_range(period)
        if parsed:
            date_from, date_to = parsed

    limit = max(1, min(100, limit))

    # API 라우팅
    try:
        if domain == "bid":
            return await _with_client(
                lambda c: bid_api.search_bid_list(
                    c,
                    bt,
                    keyword=keyword,
                    institution=institution,
                    date_from=date_from,
                    date_to=date_to,
                    num_of_rows=limit,
                )
            )
        if domain == "award":
            from .api import award as award_api
            return await _with_client(
                lambda c: award_api.search_award_list(
                    c,
                    bt,
                    keyword=keyword,
                    institution=institution,
                    date_from=date_from,
                    date_to=date_to,
                    num_of_rows=limit,
                )
            )
        if domain == "contract":
            from .api import contract as contract_api
            return await _with_client(
                lambda c: contract_api.search_contract_list(
                    c,
                    bt,
                    keyword=keyword,
                    institution=institution,
                    date_from=date_from,
                    date_to=date_to,
                    num_of_rows=limit,
                )
            )
        if domain == "request":
            from .api import request as request_api
            return await _with_client(
                lambda c: request_api.search_request_list(
                    c,
                    bt,
                    keyword=keyword,
                    institution=institution,
                    date_from=date_from,
                    date_to=date_to,
                    num_of_rows=limit,
                )
            )
    except NaraAPIError as e:
        return {"error": str(e), "code": e.code}

    return {"error": f"알 수 없는 domain: {domain}"}


# ─────────────────────────────────────────────────────────────
# Tool 2: get_procurement_detail
# ─────────────────────────────────────────────────────────────
@mcp.tool()
async def get_procurement_detail(
    domain: Literal["bid", "award", "contract", "request", "shopping"],
    notice_no: str,
    business_type: str = "용역",
    notice_ord: str = "00",
) -> dict[str, Any]:
    """입찰공고/낙찰/계약/조달요청/쇼핑몰품목 상세 정보 조회.

    Args:
        domain: 'bid'(입찰공고), 'award'(낙찰), 'contract'(계약),
                'request'(조달요청), 'shopping'(종합쇼핑몰 품목)
        notice_no: 식별 번호
            - bid/award: 입찰공고번호
            - contract: 확정계약번호
            - request: 조달요청번호
            - shopping: 품목식별번호
        business_type: 업무구분 (shopping은 무시)
        notice_ord: 공고차수 (보통 '00')
    """
    # shopping은 별도 분기
    if domain == "shopping":
        try:
            from .api import shopping as shopping_api
            return await _with_client(
                lambda c: shopping_api.get_shopping_item_detail(c, notice_no)
            )
        except NaraAPIError as e:
            return {"error": str(e), "code": e.code}

    bt = normalize_business_type(business_type) or "용역"

    try:
        if domain == "bid":
            return await _with_client(
                lambda c: bid_api.get_bid_detail(c, bt, notice_no, notice_ord)
            )
        if domain == "award":
            from .api import award as award_api
            return await _with_client(
                lambda c: award_api.get_award_detail(c, bt, notice_no, notice_ord)
            )
        if domain == "contract":
            from .api import contract as contract_api
            return await _with_client(
                lambda c: contract_api.get_contract_detail(c, bt, notice_no)
            )
        if domain == "request":
            from .api import request as request_api
            return await _with_client(
                lambda c: request_api.get_request_detail(c, bt, notice_no)
            )
    except NaraAPIError as e:
        return {"error": str(e), "code": e.code}

    return {"error": f"알 수 없는 domain: {domain}"}


# ─────────────────────────────────────────────────────────────
# Tool 3: trace_procurement_lifecycle ⭐ 시그니처 기능
# ─────────────────────────────────────────────────────────────
@mcp.tool()
async def trace_procurement_lifecycle(
    id_value: str,
    business_type: str = "용역",
    id_type: Literal["bid_notice", "spec", "plan", "request"] = "bid_notice",
) -> dict[str, Any]:
    """⭐ 조달 전 과정 추적 — 사전규격 → 공고 → 낙찰 → 계약을 한 번에.

    이 도구가 narajangteo-pro의 시그니처 기능. 식별자 하나만 알면
    조달 라이프사이클 전체를 추적해 타임라인으로 반환한다.

    Args:
        id_value: 식별 번호
        business_type: 업무구분
        id_type: 식별자 종류
            - 'bid_notice': 입찰공고번호 (가장 흔함)
            - 'spec': 사전규격등록번호
            - 'plan': 발주계획번호
            - 'request': 조달요청번호
    """
    bt = normalize_business_type(business_type) or "용역"

    try:
        return await _with_client(
            lambda c: lifecycle_api.trace_lifecycle(
                c, bt, id_type=id_type, id_value=id_value
            )
        )
    except NaraAPIError as e:
        return {"error": str(e), "code": e.code}


# ─────────────────────────────────────────────────────────────
# Tool 4: analyze_market
# ─────────────────────────────────────────────────────────────
@mcp.tool()
async def analyze_market(
    keyword: str,
    period_months: int = 12,
    business_type: str = "용역",
) -> dict[str, Any]:
    """특정 분야 시장 동향 분석.

    낙찰 데이터를 집계하여 월별 추이, 평균 낙찰가율, 상위 발주기관/낙찰업체,
    추정 시장 규모를 반환.

    Args:
        keyword: 분석 대상 키워드 (예: 'AI 챗봇', '클라우드')
        period_months: 분석 기간 — 기본 12개월
        business_type: 업무구분 또는 'all' (4개 합산)
    """
    bt = (
        "all"
        if business_type == "all"
        else (normalize_business_type(business_type) or "용역")
    )
    try:
        return await _with_client(
            lambda c: _analyze_market(
                c, keyword=keyword, period_months=period_months, business_type=bt
            )
        )
    except NaraAPIError as e:
        return {"error": str(e), "code": e.code}


# ─────────────────────────────────────────────────────────────
# Tool 5: analyze_competitor
# ─────────────────────────────────────────────────────────────
@mcp.tool()
async def analyze_competitor(
    company_name: str,
    period_months: int = 12,
    business_type: str = "all",
) -> dict[str, Any]:
    """특정 기업의 조달시장 활동 분석.

    낙찰 건수/금액, 주력 분야, 평균 낙찰가율, 거래 발주기관 패턴을 분석.

    Args:
        company_name: 기업명 (정확하지 않아도 부분 일치)
        period_months: 분석 기간
        business_type: 업무구분 또는 'all'
    """
    bt = (
        "all"
        if business_type == "all"
        else (normalize_business_type(business_type) or "용역")
    )
    try:
        return await _with_client(
            lambda c: _analyze_competitor(
                c,
                company_name=company_name,
                period_months=period_months,
                business_type=bt,
            )
        )
    except NaraAPIError as e:
        return {"error": str(e), "code": e.code}


# ─────────────────────────────────────────────────────────────
# Tool 6: score_bid_fit
# ─────────────────────────────────────────────────────────────
@mcp.tool()
async def score_bid_fit(
    bid_notice_no: str,
    business_type: str = "용역",
    profile_id: str | None = None,
    inline_profile: dict | None = None,
    notice_ord: str = "00",
) -> dict[str, Any]:
    """입찰 적합도 평가 — 0-100 점수 + 권고.

    회사 프로필(보유 면허, 매출, 실적)과 공고 요구사항을 매칭해 적합도를 산출.

    Args:
        bid_notice_no: 입찰공고번호
        business_type: 업무구분
        profile_id: 저장된 회사 프로필 ID (manage_company_profile로 미리 저장)
        inline_profile: 즉석 프로필 dict (저장 없이 일회성 평가)
            {"licenses": [...], "certifications": [...], "revenue": int, "prior_contracts": [...]}
        notice_ord: 공고차수
    """
    bt = normalize_business_type(business_type) or "용역"

    # 프로필 결정
    profile: dict[str, Any] | None = None
    if inline_profile:
        profile = {"name": "(inline)", **inline_profile}
    elif profile_id:
        profile = STORE.load_profile(profile_id)
        if not profile:
            return {"error": f"프로필 '{profile_id}'를 찾을 수 없습니다"}
    else:
        # 저장된 프로필이 1개면 자동 사용
        profiles = STORE.list_profiles()
        if len(profiles) == 1:
            profile = profiles[0]
        else:
            return {
                "error": (
                    "프로필이 필요합니다. profile_id를 지정하거나 inline_profile을 "
                    "전달하거나, manage_company_profile로 먼저 저장하세요."
                ),
                "available_profiles": [p["id"] for p in profiles],
            }

    try:
        return await _with_client(
            lambda c: _score_bid_fit(
                c,
                bid_notice_no=bid_notice_no,
                business_type=bt,
                profile=profile,
                bid_notice_ord=notice_ord,
            )
        )
    except NaraAPIError as e:
        return {"error": str(e), "code": e.code}


# ─────────────────────────────────────────────────────────────
# Tool 7: manage_watchlist
# ─────────────────────────────────────────────────────────────
@mcp.tool()
async def manage_watchlist(
    action: Literal["add", "remove", "list", "check_new"],
    keyword: str | None = None,
    business_type: str | None = None,
    institution: str | None = None,
    watch_id: int | None = None,
) -> dict[str, Any]:
    """관심 키워드 모니터링.

    actions:
        - 'add': 새 키워드 등록 (keyword 필수)
        - 'remove': 등록 해제 (watch_id 필수)
        - 'list': 등록된 키워드 목록
        - 'check_new': 등록한 키워드의 신규 공고 (마지막 확인 이후)
    """
    bt = normalize_business_type(business_type) if business_type else None

    if action == "add":
        if not keyword:
            return {"error": "add 액션에는 keyword가 필요합니다"}
        wid = STORE.add_watch(keyword, bt, institution)
        return {
            "action": "add",
            "watch_id": wid,
            "keyword": keyword,
            "business_type": bt,
            "institution": institution,
            "message": f"관심 키워드 등록: '{keyword}' (id={wid})",
        }

    if action == "remove":
        if watch_id is None:
            return {"error": "remove 액션에는 watch_id가 필요합니다"}
        success = STORE.remove_watch(watch_id)
        return {
            "action": "remove",
            "watch_id": watch_id,
            "success": success,
        }

    if action == "list":
        watches = STORE.list_watches()
        return {"action": "list", "count": len(watches), "watches": watches}

    if action == "check_new":
        watches = STORE.list_watches()
        all_new: list[dict[str, Any]] = []

        async with NaraClient(SETTINGS) as client:
            for w in watches:
                w_bt = w.get("business_type") or "용역"
                try:
                    result = await bid_api.search_bid_list(
                        client,
                        w_bt,
                        keyword=w["keyword"],
                        institution=w.get("institution"),
                        num_of_rows=20,
                    )
                except NaraAPIError as e:
                    logger.warning("watch %s 체크 실패: %s", w["id"], e)
                    continue

                items = result.get("items", [])
                bid_nos = [i.get("bidNtceNo") for i in items if i.get("bidNtceNo")]
                unseen = STORE.filter_unseen(w["id"], bid_nos)

                # 새 공고 표시
                new_items = [i for i in items if i.get("bidNtceNo") in unseen]
                for item in new_items:
                    item["_watch_id"] = w["id"]
                    item["_watch_keyword"] = w["keyword"]
                    all_new.append(item)
                    STORE.mark_seen(w["id"], item["bidNtceNo"])

                STORE.update_last_checked(w["id"])

        return {
            "action": "check_new",
            "watches_checked": len(watches),
            "new_items_count": len(all_new),
            "new_items": all_new,
        }

    return {"error": f"알 수 없는 action: {action}"}


# ─────────────────────────────────────────────────────────────
# Tool 8: manage_company_profile
# ─────────────────────────────────────────────────────────────
@mcp.tool()
async def manage_company_profile(
    action: Literal["save", "load", "list", "delete"],
    profile_id: str | None = None,
    name: str | None = None,
    licenses: list[str] | None = None,
    certifications: list[str] | None = None,
    revenue: int | str | None = None,
    prior_contracts: list[dict] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """회사 프로필 관리 — 적합도 평가에 재사용.

    actions:
        - 'save': 저장 (profile_id, name 필수). 같은 ID면 업데이트.
        - 'load': 조회 (profile_id 필수)
        - 'list': 모든 프로필 목록
        - 'delete': 삭제 (profile_id 필수)

    revenue는 자연어 표현 가능: '50억', '100억원' 등.
    """
    if action == "save":
        if not profile_id or not name:
            return {"error": "save 액션에는 profile_id와 name이 필요합니다"}
        revenue_int = parse_money(revenue) if revenue is not None else None
        STORE.save_profile(
            profile_id,
            name,
            licenses=licenses,
            certifications=certifications,
            revenue=revenue_int,
            prior_contracts=prior_contracts,
            notes=notes,
        )
        return {
            "action": "save",
            "profile_id": profile_id,
            "name": name,
            "revenue_formatted": format_money(revenue_int),
            "message": f"프로필 '{profile_id}' 저장 완료",
        }

    if action == "load":
        if not profile_id:
            return {"error": "load 액션에는 profile_id가 필요합니다"}
        p = STORE.load_profile(profile_id)
        if not p:
            return {"error": f"프로필 '{profile_id}' 없음"}
        if p.get("revenue"):
            p["revenue_formatted"] = format_money(p["revenue"])
        return {"action": "load", "profile": p}

    if action == "list":
        profiles = STORE.list_profiles()
        return {"action": "list", "count": len(profiles), "profiles": profiles}

    if action == "delete":
        if not profile_id:
            return {"error": "delete 액션에는 profile_id가 필요합니다"}
        success = STORE.delete_profile(profile_id)
        return {"action": "delete", "profile_id": profile_id, "success": success}

    return {"error": f"알 수 없는 action: {action}"}


# ─────────────────────────────────────────────────────────────
# 엔트리포인트
# ─────────────────────────────────────────────────────────────
def main() -> None:
    transport = SETTINGS.transport
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport in ("http", "streamable-http"):
        mcp.run(
            transport="streamable-http",
            host=SETTINGS.http_host,
            port=SETTINGS.http_port,
        )
    else:
        raise RuntimeError(f"지원하지 않는 트랜스포트: {transport}")


if __name__ == "__main__":
    main()
