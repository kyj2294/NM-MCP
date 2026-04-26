"""조달요청서비스 API 래퍼.

수요기관이 조달청에 계약체결을 요청한 정보 — 발주의 가장 이른 단계.
조달요청 → 사전규격 → 입찰공고 → 낙찰 → 계약 흐름의 시작점.

기존 narajangteo_mcp_server가 다루지 않는 영역.
"발주가 일어나기 전 단계"를 미리 포착하면 영업 활동에 큰 우위.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..config import BUSINESS_TYPE_SUFFIX
from .client import NaraAPIError, NaraClient


def _operation_for(business_type: str) -> str:
    suffix = BUSINESS_TYPE_SUFFIX.get(business_type)
    if not suffix:
        raise NaraAPIError(
            f"잘못된 업무구분: {business_type} (물품/용역/공사/외자 중 선택)"
        )
    return f"getPrcrmntReqstInfo{suffix}"


def _format_date(yyyymmdd: str | None, *, end_of_day: bool = False) -> str | None:
    if not yyyymmdd:
        return None
    cleaned = yyyymmdd.replace("-", "").replace(".", "")
    if len(cleaned) != 8:
        raise NaraAPIError(f"날짜 형식 오류 (YYYYMMDD 기대): {yyyymmdd}")
    return cleaned + ("2359" if end_of_day else "0000")


async def search_request_list(
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
    """조달요청 목록.

    조달요청은 모든 입찰에 존재하지 않을 수 있다 (수요기관이 자체 계약 가능).
    하지만 존재하는 경우, 입찰공고보다 1~3개월 먼저 나오는 경우가 많아
    영업 활동의 선행 지표로 활용 가능.
    """
    operation = _operation_for(business_type)

    if not date_from and not date_to:
        end = datetime.now()
        start = end - timedelta(days=30)
        date_from = start.strftime("%Y%m%d")
        date_to = end.strftime("%Y%m%d")

    params: dict[str, Any] = {
        "inqryDiv": "1",  # 1: 등록일자 기준
        "inqryBgnDt": _format_date(date_from),
        "inqryEndDt": _format_date(date_to, end_of_day=True),
        "pageNo": page_no,
        "numOfRows": num_of_rows,
    }
    if keyword:
        params["prcrmntReqNm"] = keyword
    if institution:
        params["dminsttNm"] = institution

    return await client.call("request", operation, params)


async def get_request_detail(
    client: NaraClient,
    business_type: str,
    request_no: str,
) -> dict[str, Any]:
    """조달요청번호로 상세 조회."""
    operation = _operation_for(business_type)
    params = {
        "inqryDiv": "2",  # 2: 조달요청번호 기준
        "prcrmntReqNo": request_no,
        "numOfRows": 10,
    }
    return await client.call("request", operation, params)
