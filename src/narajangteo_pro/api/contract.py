"""계약정보서비스 API 래퍼.

체결된 계약 정보 - 실제 단가, 계약기간, 계약변경이력 등.
"실제로 시장에서 거래되는 가격" 데이터의 원천.
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


async def search_contract_list(
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
    """계약 체결 목록.

    계약체결일자 기준으로 검색.
    """
    operation = _operation_for("getCntrctInfoList", business_type)

    if not date_from and not date_to:
        end = datetime.now()
        start = end - timedelta(days=30)
        date_from = start.strftime("%Y%m%d")
        date_to = end.strftime("%Y%m%d")

    params: dict[str, Any] = {
        "inqryDiv": "1",  # 1: 계약체결일자 기준
        "inqryBgnDate": _format_date(date_from),
        "inqryEndDate": _format_date(date_to, end_of_day=True),
        "pageNo": page_no,
        "numOfRows": num_of_rows,
    }
    if keyword:
        params["prdctClsfcNoNm"] = keyword
    if institution:
        params["cntrctInsttNm"] = institution

    return await client.call("contract", operation, params)


async def get_contract_detail(
    client: NaraClient,
    business_type: str,
    contract_no: str,
) -> dict[str, Any]:
    """확정계약번호로 계약 상세 조회."""
    operation = _operation_for("getCntrctInfoList", business_type)
    params = {
        "inqryDiv": "3",  # 3: 확정계약번호 기준
        "cntrctNo": contract_no,
        "numOfRows": 10,
    }
    return await client.call("contract", operation, params)
