"""낙찰정보서비스 API 래퍼.

낙찰자, 개찰순위, 복수예비가, 예비가격 정보 조회.
시장 분석과 경쟁사 분석의 핵심 데이터 소스.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..config import BUSINESS_TYPE_SUFFIX
from .client import NaraAPIError, NaraClient


def _operation_for(base: str, business_type: str) -> str:
    suffix = BUSINESS_TYPE_SUFFIX.get(business_type)
    if not suffix:
        raise NaraAPIError(
            f"잘못된 업무구분: {business_type} (물품/용역/공사/외자 중 선택)"
        )
    return f"{base}{suffix}"


def _format_date(yyyymmdd: str | None, *, end_of_day: bool = False) -> str | None:
    if not yyyymmdd:
        return None
    cleaned = yyyymmdd.replace("-", "").replace(".", "")
    if len(cleaned) != 8:
        raise NaraAPIError(f"날짜 형식 오류 (YYYYMMDD 기대): {yyyymmdd}")
    return cleaned + ("2359" if end_of_day else "0000")


async def search_award_list(
    client: NaraClient,
    business_type: str,
    *,
    keyword: str | None = None,
    institution: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page_no: int = 1,
    num_of_rows: int = 20,
) -> dict[str, Any]:
    """개찰완료 낙찰정보 목록.

    낙찰자, 낙찰가격, 추정가격 등 분석에 필요한 핵심 데이터를 반환.
    """
    operation = _operation_for("getScsbidListSttus", business_type)

    if not date_from and not date_to:
        end = datetime.now()
        start = end - timedelta(days=30)
        date_from = start.strftime("%Y%m%d")
        date_to = end.strftime("%Y%m%d")

    params: dict[str, Any] = {
        "inqryDiv": "1",  # 1: 개찰일시 기준
        "inqryBgnDt": _format_date(date_from),
        "inqryEndDt": _format_date(date_to, end_of_day=True),
        "pageNo": page_no,
        "numOfRows": num_of_rows,
    }
    if keyword:
        params["bidNtceNm"] = keyword
    if institution:
        params["dminsttNm"] = institution

    return await client.call("award", operation, params)


async def get_award_detail(
    client: NaraClient,
    business_type: str,
    bid_notice_no: str,
    bid_notice_ord: str = "00",
) -> dict[str, Any]:
    """특정 공고의 낙찰 결과 상세 (개찰순위, 복수예비가 등)."""
    operation = _operation_for("getScsbidListSttus", business_type)
    params = {
        "inqryDiv": "2",
        "bidNtceNo": bid_notice_no,
        "bidNtceOrd": bid_notice_ord,
        "numOfRows": 50,
    }
    return await client.call("award", operation, params)
