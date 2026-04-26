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
    return s[:6] if len(s) >= 6 else None


def _month_ranges(period_months: int) -> list[tuple[str, str]]:
    """오늘 기준 과거 period_months 개월을 1개월 단위 (date_from, date_to) 리스트로 반환."""
    ranges: list[tuple[str, str]] = []
    today = datetime.now()
    # 최신 달부터 거슬러 올라감
    end = today
    for _ in range(period_months):
        # 해당 달 첫날
        start = end.replace(day=1)
        ranges.append((start.strftime("%Y%m%d"), end.strftime("%Y%m%d")))
        # 전 달 마지막날로 이동
        end = start - timedelta(days=1)
    return list(reversed(ranges))


async def _fetch_awards_by_month(
    client: NaraClient,
    business_types: list[str],
    period_months: int,
    keyword: str | None = None,
    company_name: str | None = None,
    rows_per_month: int = 100,
) -> list[dict[str, Any]]:
    """월 단위로 쪼개서 낙찰 데이터를 수집한다.

    한 번 요청의 최대 결과가 100건이므로, 기간 전체를 1개월 단위로 나눠
    각 달마다 API를 호출해 더 완전한 데이터를 확보한다.
    """
    all_items: list[dict[str, Any]] = []
    for date_from, date_to in _month_ranges(period_months):
        for bt in business_types:
            result = await award_api.search_award_list(
                client,
                bt,
                keyword=keyword,
                date_from=date_from,
                date_to=date_to,
                num_of_rows=rows_per_month,
            )
            items = result.get("items", [])
            if company_name:
                items = [
                    i for i in items
                    if company_name in (i.get("opengCorpNm") or i.get("scsbidCorpNm") or "")
                ]
                for i in items:
                    i["_business_type"] = bt
            all_items.extend(items)
    return all_items


async def analyze_market(
    client: NaraClient,
    *,
    keyword: str,
    period_months: int = 12,
    business_type: str = "용역",
) -> dict[str, Any]:
    """시장 분석.

    Args:
        keyword: 분석 대상 키워드 (예: 'AI 챗봇')
        period_months: 분석 기간 (월)
        business_type: 업무구분 (단일). 'all' 시 4개 모두 합산.

    Returns:
        {
            "period": {"from": "20250426", "to": "20260426", "months": 12},
            "keyword": "...",
            "summary": {...},
            "monthly_trend": [...],
            "top_institutions": [...],
            "top_winners": [...],
        }
    """
    today = datetime.now()
    start = today - timedelta(days=30 * period_months)
    date_from = start.strftime("%Y%m%d")
    date_to = today.strftime("%Y%m%d")

    business_types = (
        ["물품", "용역", "공사", "외자"] if business_type == "all" else [business_type]
    )

    # 1개월 단위로 쪼개서 수집
    all_awards = await _fetch_awards_by_month(
        client, business_types, period_months, keyword=keyword
    )

    # 집계
    monthly: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "total_amount": 0})
    institution_counter: Counter[str] = Counter()
    winner_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "total_amount": 0})
    award_rates: list[float] = []
    competition_values: list[int] = []
    total_amount = 0

    for item in all_awards:
        inst = item.get("dminsttNm") or item.get("ntceInsttNm") or "(미상)"
        institution_counter[inst] += 1

        winner = item.get("opengCorpNm") or item.get("scsbidCorpNm") or "(미상)"
        award_amount = _safe_int(item.get("scsbidAmt")) or _safe_int(item.get("opengAmt")) or 0
        estimated = _safe_int(item.get("presmptPrce")) or _safe_int(item.get("bssamt"))

        winner_stats[winner]["count"] += 1
        winner_stats[winner]["total_amount"] += award_amount
        total_amount += award_amount

        if award_amount and estimated and estimated > 0:
            rate = (award_amount / estimated) * 100
            if 30 <= rate <= 130:
                award_rates.append(rate)

        month_key = (
            _yyyymm(item.get("opengDt"))
            or _yyyymm(item.get("scsbidDt"))
            or _yyyymm(item.get("rgstDt"))
        )
        if month_key:
            monthly[month_key]["count"] += 1
            monthly[month_key]["total_amount"] += award_amount

        n = _safe_int(item.get("prtcptCnum"))
        if n and n > 0:
            competition_values.append(n)

    avg_award_rate = sum(award_rates) / len(award_rates) if award_rates else 0
    avg_competition = sum(competition_values) / len(competition_values) if competition_values else 0

    top_inst = [{"name": n, "count": c} for n, c in institution_counter.most_common(10)]
    top_win = sorted(
        [{"name": n, **s} for n, s in winner_stats.items() if n != "(미상)"],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]
    monthly_sorted = [{"month": m, **d} for m, d in sorted(monthly.items())]

    return {
        "period": {"from": date_from, "to": date_to, "months": period_months},
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
        "_note": f"{period_months}개월을 1개월 단위로 분할 수집 — 총 {len(all_awards)}건.",
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

    # 1개월 단위로 쪼개서 수집 + 회사명 필터
    matched = await _fetch_awards_by_month(
        client, business_types, period_months, company_name=company_name
    )

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
        "period": {"from": date_from, "to": date_to, "months": period_months},
        "summary": {
            "total_awards": len(matched),
            "total_amount": total_amount,
            "avg_award_rate_percent": round(
                sum(award_rates) / len(award_rates) if award_rates else 0, 2
            ),
            "by_business_type": dict(by_business),
        },
        "top_categories": [{"category": k, "count": v} for k, v in field_counter.most_common(10)],
        "top_clients": [
            {"institution": k, "count": v} for k, v in institution_counter.most_common(10)
        ],
        "_note": f"{period_months}개월을 1개월 단위로 분할 수집 — 총 {len(matched)}건.",
    }
