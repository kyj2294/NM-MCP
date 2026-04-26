"""입찰공고정보서비스 API 래퍼.

업무구분(물품/용역/공사/외자)에 따라 다른 오퍼레이션을 자동 호출.
사용자는 business_type만 지정하면 알아서 라우팅된다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..config import BUSINESS_TYPE_SUFFIX
from .client import NaraAPIError, NaraClient


def _operation_for(base: str, business_type: str) -> str:
    """예: ('getBidPblancListInfo', '용역') → 'getBidPblancListInfoServcPPSSrch'"""
    suffix = BUSINESS_TYPE_SUFFIX.get(business_type)
    if not suffix:
        raise NaraAPIError(
            f"잘못된 업무구분: {business_type} (물품/용역/공사/외자 중 선택)"
        )
    return f"{base}{suffix}PPSSrch"


def _format_date(yyyymmdd: str | None, *, end_of_day: bool = False) -> str | None:
    """YYYYMMDD → YYYYMMDDHHMM. 입찰공고 API는 분 단위 요구."""
    if not yyyymmdd:
        return None
    cleaned = yyyymmdd.replace("-", "").replace(".", "")
    if len(cleaned) != 8:
        raise NaraAPIError(f"날짜 형식 오류 (YYYYMMDD 기대): {yyyymmdd}")
    return cleaned + ("2359" if end_of_day else "0000")


async def search_bid_list(
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
    """입찰공고 목록 검색.

    검색 조건이 모두 None이면 최근 7일치를 반환.
    """
    operation = _operation_for("getBidPblancListInfo", business_type)

    # 기본값: 최근 7일
    if not date_from and not date_to:
        end = datetime.now()
        start = end - timedelta(days=7)
        date_from = start.strftime("%Y%m%d")
        date_to = end.strftime("%Y%m%d")

    params: dict[str, Any] = {
        "inqryDiv": "1",  # 1: 등록일시 기준
        "inqryBgnDt": _format_date(date_from),
        "inqryEndDt": _format_date(date_to, end_of_day=True),
        "pageNo": page_no,
        "numOfRows": num_of_rows,
    }
    if keyword:
        params["bidNtceNm"] = keyword
    if institution:
        params["ntceInsttNm"] = institution

    return await client.call("bid", operation, params)


async def get_bid_detail(
    client: NaraClient,
    business_type: str,
    bid_notice_no: str,
    bid_notice_ord: str = "00",
) -> dict[str, Any]:
    """입찰공고 상세 정보.

    Args:
        bid_notice_no: 입찰공고번호
        bid_notice_ord: 입찰공고차수 (보통 '00')
    """
    # 상세 조회는 List 부분이 빠짐
    operation = _operation_for("getBidPblancListInfo", business_type)
    params = {
        "inqryDiv": "2",  # 2: 입찰공고번호 기준
        "bidNtceNo": bid_notice_no,
        "bidNtceOrd": bid_notice_ord,
        "numOfRows": 10,
    }
    return await client.call("bid", operation, params)
