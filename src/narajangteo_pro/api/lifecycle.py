"""계약과정통합공개서비스 API 래퍼 ⭐ 시그니처 기능.

공고번호/사전규격번호/발주계획번호/조달요청번호 중 하나만 알면
사전규격 → 입찰공고 → 낙찰 → 계약 전체 라이프사이클을 한 번에 조회.

기존 narajangteo_mcp_server가 제공하지 않는 차별화 영역.
"""
from __future__ import annotations

from typing import Any

from ..config import BUSINESS_TYPE_SUFFIX
from .client import NaraAPIError, NaraClient


def _operation_for(business_type: str) -> str:
    """업무구분에 맞는 계약과정통합공개 오퍼레이션."""
    suffix = BUSINESS_TYPE_SUFFIX.get(business_type)
    if not suffix:
        raise NaraAPIError(
            f"잘못된 업무구분: {business_type} (물품/용역/공사/외자 중 선택)"
        )
    return f"getCntrctProcssIntgOpen{suffix}"


# 식별자 종류 → API 파라미터명
ID_PARAM_MAP: dict[str, str] = {
    "bid_notice": "bidNtceNo",        # 입찰공고번호
    "spec": "specRgstNo",             # 사전규격등록번호
    "plan": "ordPlanRgstNo",          # 발주계획번호
    "request": "prcrmntReqNo",        # 조달요청번호
}


async def trace_lifecycle(
    client: NaraClient,
    business_type: str,
    *,
    id_type: str,
    id_value: str,
) -> dict[str, Any]:
    """공고/사전규격/발주계획/조달요청 번호 중 하나로 전체 과정 조회.

    Args:
        business_type: 물품/용역/공사/외자
        id_type: 'bid_notice' | 'spec' | 'plan' | 'request'
        id_value: 해당 번호

    Returns:
        사전규격, 입찰공고, 낙찰, 계약 정보가 묶인 dict.
    """
    if id_type not in ID_PARAM_MAP:
        raise NaraAPIError(
            f"알 수 없는 식별자 타입: {id_type} "
            f"(bid_notice/spec/plan/request 중 선택)"
        )

    operation = _operation_for(business_type)
    param_name = ID_PARAM_MAP[id_type]
    params: dict[str, Any] = {
        param_name: id_value,
        "numOfRows": 50,
    }
    return await client.call("lifecycle", operation, params)
