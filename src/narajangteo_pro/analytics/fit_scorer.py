"""입찰 적합도 평가 엔진.

회사 프로필 (보유 면허·인증·실적·매출)과 특정 입찰공고를 매칭해
0-100 점수와 권고를 산출.

기존 Top 5 추천보다 한 단계 더 들어가서 "왜 이 점수인지" 설명한다.
"""
from __future__ import annotations

import re
from typing import Any

from ..api import bid as bid_api
from ..api.client import NaraClient


def _extract_required_licenses(detail_item: dict[str, Any]) -> list[str]:
    """공고 상세에서 요구 면허 추출.

    면허제한정보 필드는 API마다 이름이 다를 수 있어 휴리스틱하게 찾음.
    """
    candidates: list[str] = []
    for key, value in detail_item.items():
        if not isinstance(value, str):
            continue
        if "면허" in key or "lcns" in key.lower() or "license" in key.lower():
            candidates.append(value)
    # 추가로 본문에서 정규식으로 면허 패턴 추출 시도
    return [v for v in candidates if v.strip()]


def _safe_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _score_license_match(
    required: list[str], owned: list[str]
) -> tuple[float, str]:
    """면허 일치 점수 (0-100)."""
    if not required:
        return 80.0, "공고에 명시된 면허 제한 정보가 없습니다 (확인 필요)"
    matched = []
    missing = []
    for req in required:
        if any(req in own or own in req for own in owned):
            matched.append(req)
        else:
            missing.append(req)
    if not missing:
        return 100.0, f"요구 면허 모두 보유: {', '.join(matched)}"
    if not matched:
        return 0.0, f"요구 면허 미보유: {', '.join(missing)}"
    ratio = len(matched) / len(required)
    return ratio * 100, (
        f"일부 면허 보유 ({len(matched)}/{len(required)}). "
        f"미보유: {', '.join(missing)}"
    )


def _score_revenue_fit(
    estimated_price: int | None, revenue: int | None
) -> tuple[float, str]:
    """매출 규모 적합도 (추정가의 일정 배수 매출 권장)."""
    if not estimated_price:
        return 70.0, "추정가 정보 없음"
    if not revenue:
        return 50.0, "회사 매출 정보 없음 (프로필 등록 권장)"

    # 휴리스틱: 매출이 추정가의 3배 이상이면 안정적, 1배 미만이면 부담
    ratio = revenue / estimated_price
    if ratio >= 3:
        return 100.0, f"매출 규모 충분 (추정가의 {ratio:.1f}배)"
    if ratio >= 1.5:
        return 80.0, f"매출 규모 적정 (추정가의 {ratio:.1f}배)"
    if ratio >= 1.0:
        return 60.0, f"매출 규모 빠듯 (추정가의 {ratio:.1f}배). 컨소시엄 고려"
    if ratio >= 0.5:
        return 30.0, f"매출 규모 부족 (추정가의 {ratio:.1f}배). 단독 수주 어려움"
    return 10.0, f"매출 대비 사업 규모 과다 (추정가의 {ratio:.1f}배)"


def _score_prior_contract_fit(
    prior_contracts: list[dict], bid_keyword: str
) -> tuple[float, str]:
    """과거 유사 실적 점수."""
    if not prior_contracts:
        return 30.0, "과거 실적 데이터 없음"

    related = [
        c
        for c in prior_contracts
        if any(kw in (c.get("name", "") + c.get("category", "")) for kw in [bid_keyword])
    ]
    if not related:
        return 40.0, f"동일/유사 분야 실적 없음 ({len(prior_contracts)}건 보유)"
    return min(100.0, 50 + len(related) * 15), (
        f"유사 실적 {len(related)}건 보유"
    )


async def score_bid_fit(
    client: NaraClient,
    *,
    bid_notice_no: str,
    business_type: str,
    profile: dict[str, Any],
    bid_notice_ord: str = "00",
) -> dict[str, Any]:
    """입찰 적합도 종합 평가.

    Args:
        bid_notice_no: 입찰공고번호
        business_type: 업무구분
        profile: 회사 프로필 dict
            {
                "name": str,
                "licenses": list[str],
                "certifications": list[str],
                "revenue": int,
                "prior_contracts": [{"name": ..., "category": ..., "amount": ...}, ...]
            }

    Returns:
        {
            "bid": {...},  # 공고 요약
            "scores": {
                "license": (점수, 사유),
                "revenue": (점수, 사유),
                "experience": (점수, 사유),
            },
            "total_score": float,  # 0-100
            "recommendation": "강력추천" | "검토 권장" | "신중 검토" | "비추천",
            "reasoning": str,  # 종합 설명
        }
    """
    # 1) 공고 상세 가져오기
    detail = await bid_api.get_bid_detail(
        client, business_type, bid_notice_no, bid_notice_ord
    )
    items = detail.get("items", [])
    if not items:
        return {
            "error": f"공고 {bid_notice_no}을(를) 찾을 수 없습니다.",
        }
    item = items[0] if isinstance(items, list) else items

    bid_name = item.get("bidNtceNm", "")
    estimated = _safe_int(item.get("presmptPrce")) or _safe_int(item.get("bssamt"))

    # 2) 항목별 점수
    required_licenses = _extract_required_licenses(item)
    license_score, license_reason = _score_license_match(
        required_licenses, profile.get("licenses", [])
    )
    revenue_score, revenue_reason = _score_revenue_fit(
        estimated, profile.get("revenue")
    )
    # 키워드는 공고명 첫 단어 추출 (간단한 휴리스틱)
    bid_keyword = re.split(r"[\s\-_/(]", bid_name)[0] if bid_name else ""
    experience_score, experience_reason = _score_prior_contract_fit(
        profile.get("prior_contracts", []), bid_keyword
    )

    # 3) 가중 평균 (면허 50%, 매출 25%, 실적 25%)
    total = (
        license_score * 0.5 + revenue_score * 0.25 + experience_score * 0.25
    )

    # 4) 권고
    if total >= 80:
        recommendation = "강력추천"
    elif total >= 60:
        recommendation = "검토 권장"
    elif total >= 40:
        recommendation = "신중 검토"
    else:
        recommendation = "비추천"

    return {
        "bid": {
            "bid_notice_no": bid_notice_no,
            "name": bid_name,
            "business_type": business_type,
            "estimated_price": estimated,
            "institution": item.get("ntceInsttNm"),
            "deadline": item.get("bidClseDt"),
        },
        "scores": {
            "license": {"score": round(license_score, 1), "reason": license_reason},
            "revenue": {"score": round(revenue_score, 1), "reason": revenue_reason},
            "experience": {
                "score": round(experience_score, 1),
                "reason": experience_reason,
            },
        },
        "total_score": round(total, 1),
        "recommendation": recommendation,
        "reasoning": (
            f"{recommendation} (종합 {total:.1f}점). "
            f"면허 {license_score:.0f}점, 매출 {revenue_score:.0f}점, "
            f"실적 {experience_score:.0f}점."
        ),
    }
