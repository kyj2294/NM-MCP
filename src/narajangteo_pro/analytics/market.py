"""시장 분석 엔진.

낙찰정보 + 입찰공고 데이터를 조합해 다음을 계산:
- 월별 발주 추이
- 평균 낙찰가율 (낙찰가 / 추정가)
- 상위 발주기관 / 낙찰업체
- 평균 경쟁률
- 유찰률 (대략)

기존 narajangteo_mcp_server에는 없는 영역 — 진짜 차별화.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from ..api import award as award_api
from ..api import bid as bid_api
from ..api.client import NaraClient


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _yyyymm(date_str: str | None) -> str | None:
    """'2026-04-15 14:30:00' 또는 '202604151430' → '202604'."""
    if not date_str:
        return None
    s = str(date_str).replace("-", "").replace(":", "").replace(" ", "")
    if len(s) >= 6:
        return s[:6]
    return None


async def analyze_market(
    client: NaraClient,
    *,
    keyword: str,
    period_months: int = 12,
    business_type: str = "용역",
    sample_limit: int = 500,
) -> dict[str, Any]:
    """시장 분석.

    Args:
        keyword: 분석 대상 키워드 (예: 'AI 챗봇')
        period_months: 분석 기간 (월)
        business_type: 업무구분 (단일). 'all' 시 4개 모두 합산.
        sample_limit: API 호출 페이지 크기 (트래픽 절약)

    Returns:
        {
            "period": {"from": "20250426", "to": "20260426", "months": 12},
            "keyword": "...",
            "summary": {
                "total_awards": int,
                "total_bid_count": int,
                "avg_award_rate": float,    # 평균 낙찰가율 (%)
                "avg_competition": float,   # 평균 경쟁률
                "estimated_market_size": int,  # 추정 시장규모 (원)
            },
            "monthly_trend": [{"month": "202604", "count": 12, "amount": ...}, ...],
            "top_institutions": [{"name": "...", "count": 5}, ...],
            "top_winners": [{"name": "...", "count": 3, "total_amount": ...}, ...],
        }
    """
    # 기간 계산
    today = datetime.now()
    start = today - timedelta(days=30 * period_months)
    date_from = start.strftime("%Y%m%d")
    date_to = today.strftime("%Y%m%d")

    business_types = (
        ["물품", "용역", "공사", "외자"] if business_type == "all" else [business_type]
    )

    # 낙찰 데이터 수집 (페이지네이션은 일단 첫 페이지만 — sample_limit 만큼)
    all_awards: list[dict[str, Any]] = []
    for bt in business_types:
        result = await award_api.search_award_list(
            client,
            bt,
            keyword=keyword,
            date_from=date_from,
            date_to=date_to,
            num_of_rows=min(sample_limit, 100),
        )
        all_awards.extend(result.get("items", []))

    # 집계
    monthly: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_amount": 0}
    )
    institution_counter: Counter[str] = Counter()
    winner_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_amount": 0}
    )
    award_rates: list[float] = []
    total_amount = 0

    for item in all_awards:
        # 발주기관
        inst = item.get("dminsttNm") or item.get("ntceInsttNm") or "(미상)"
        institution_counter[inst] += 1

        # 낙찰자
        winner = item.get("opengCorpNm") or item.get("scsbidCorpNm") or "(미상)"
        # 낙찰가
        award_amount = (
            _safe_int(item.get("scsbidAmt"))
            or _safe_int(item.get("opengAmt"))
            or 0
        )
        # 추정가
        estimated = _safe_int(item.get("presmptPrce")) or _safe_int(
            item.get("bssamt")
        )

        winner_stats[winner]["count"] += 1
        winner_stats[winner]["total_amount"] += award_amount
        total_amount += award_amount

        # 낙찰가율
        if award_amount and estimated and estimated > 0:
            rate = (award_amount / estimated) * 100
            if 30 <= rate <= 130:  # 이상치 제거
                award_rates.append(rate)

        # 월별
        month_key = (
            _yyyymm(item.get("opengDt"))
            or _yyyymm(item.get("scsbidDt"))
            or _yyyymm(item.get("rgstDt"))
        )
        if month_key:
            monthly[month_key]["count"] += 1
            monthly[month_key]["total_amount"] += award_amount

    # 평균 경쟁률은 별도 필드가 있으면 사용, 없으면 추정
    competition_values: list[int] = []
    for item in all_awards:
        n = _safe_int(item.get("prtcptCnum"))  # 참가업체수
        if n and n > 0:
            competition_values.append(n)

    avg_competition = (
        sum(competition_values) / len(competition_values) if competition_values else 0
    )
    avg_award_rate = sum(award_rates) / len(award_rates) if award_rates else 0

    # 정렬해서 상위 N개만
    top_inst = [
        {"name": name, "count": cnt}
        for name, cnt in institution_counter.most_common(10)
    ]
    top_win = sorted(
        [
            {"name": name, **stats}
            for name, stats in winner_stats.items()
            if name != "(미상)"
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    monthly_sorted = [
        {"month": m, **data}
        for m, data in sorted(monthly.items())
    ]

    return {
        "period": {
            "from": date_from,
            "to": date_to,
            "months": period_months,
        },
        "keyword": keyword,
        "business_types": business_types,
        "summary": {
            "total_awards": len(all_awards),
            "avg_award_rate_percent": round(avg_award_rate, 2),
            "avg_competition": round(avg_competition, 2),
            "estimated_market_size": total_amount,
        },
        "monthly_trend": monthly_sorted,
        "top_institutions": top_inst,
        "top_winners": top_win,
        "_note": (
            f"샘플 {len(all_awards)}건 기반. "
            "정확한 분석을 위해서는 페이지네이션을 통해 더 많은 데이터 수집 필요."
        ),
    }


async def analyze_competitor(
    client: NaraClient,
    *,
    company_name: str,
    period_months: int = 12,
    business_type: str = "all",
) -> dict[str, Any]:
    """특정 기업의 조달시장 활동 분석."""
    today = datetime.now()
    start = today - timedelta(days=30 * period_months)
    date_from = start.strftime("%Y%m%d")
    date_to = today.strftime("%Y%m%d")

    business_types = (
        ["물품", "용역", "공사", "외자"] if business_type == "all" else [business_type]
    )

    matched: list[dict[str, Any]] = []
    for bt in business_types:
        # 회사명을 키워드로 직접 검색하기는 API가 지원 안 할 수 있어
        # 우선 기간 내 데이터를 가져와 클라이언트 측에서 필터
        result = await award_api.search_award_list(
            client,
            bt,
            date_from=date_from,
            date_to=date_to,
            num_of_rows=100,
        )
        for item in result.get("items", []):
            winner = item.get("opengCorpNm") or item.get("scsbidCorpNm") or ""
            if company_name in winner:
                item["_business_type"] = bt
                matched.append(item)

    # 집계
    field_counter: Counter[str] = Counter()
    institution_counter: Counter[str] = Counter()
    award_rates: list[float] = []
    total_amount = 0
    by_business: Counter[str] = Counter()

    for item in matched:
        amt = _safe_int(item.get("scsbidAmt")) or 0
        est = _safe_int(item.get("presmptPrce")) or _safe_int(item.get("bssamt"))
        total_amount += amt
        if amt and est and est > 0:
            rate = (amt / est) * 100
            if 30 <= rate <= 130:
                award_rates.append(rate)

        category = item.get("prdctClsfcNoNm") or item.get("bidNtceNm") or ""
        if category:
            field_counter[category[:30]] += 1

        inst = item.get("dminsttNm") or item.get("ntceInsttNm") or "(미상)"
        institution_counter[inst] += 1
        by_business[item.get("_business_type", "?")] += 1

    return {
        "company_name": company_name,
        "period": {
            "from": date_from,
            "to": date_to,
            "months": period_months,
        },
        "summary": {
            "total_awards": len(matched),
            "total_amount": total_amount,
            "avg_award_rate_percent": round(
                sum(award_rates) / len(award_rates) if award_rates else 0, 2
            ),
            "by_business_type": dict(by_business),
        },
        "top_categories": [
            {"category": k, "count": v} for k, v in field_counter.most_common(10)
        ],
        "top_clients": [
            {"institution": k, "count": v}
            for k, v in institution_counter.most_common(10)
        ],
        "_note": (
            "샘플 데이터 기반 부분 분석. 정확도를 위해서는 더 넓은 기간/페이지네이션 필요."
        ),
    }
