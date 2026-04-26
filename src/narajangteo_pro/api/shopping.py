"""종합쇼핑몰 품목정보 API 래퍼.

조달청 종합쇼핑몰에 등록된 단가계약 품목 — 입찰 없이 바로 구매 가능한 항목.
공공기관 입장에서는 "이미 조달청과 단가계약된 거라 바로 살 수 있는지" 확인용.
민간 기업 입장에서는 "우리 제품도 이렇게 등록할 수 있는지" 벤치마킹용.

종합쇼핑몰은 업무구분 분기가 없는 단일 오퍼레이션.
"""
from __future__ import annotations

from typing import Any

from .client import NaraClient


async def search_shopping_items(
    client: NaraClient,
    *,
    keyword: str | None = None,
    category_no: str | None = None,
    company_name: str | None = None,
    page_no: int = 1,
    num_of_rows: int = 20,
) -> dict[str, Any]:
    """종합쇼핑몰 품목 검색.

    Args:
        keyword: 품목명 키워드
        category_no: 물품분류번호 (8자리)
        company_name: 공급업체명
    """
    params: dict[str, Any] = {
        "pageNo": page_no,
        "numOfRows": num_of_rows,
    }
    if keyword:
        params["prdctIdntNoNm"] = keyword
    if category_no:
        params["dtlsClsfcNo"] = category_no
    if company_name:
        params["corpNm"] = company_name

    # 종합쇼핑몰은 단일 오퍼레이션
    return await client.call("shopping", "getShoppingMallPrdctInfoList", params)


async def get_shopping_item_detail(
    client: NaraClient,
    product_id: str,
) -> dict[str, Any]:
    """식별번호로 품목 상세."""
    params = {
        "prdctIdntNo": product_id,
        "numOfRows": 10,
    }
    return await client.call("shopping", "getShoppingMallPrdctInfoList", params)
