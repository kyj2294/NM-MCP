"""한국어 행정용어 ↔ API 파라미터 매핑.

LLM이 자연어로 받은 표현을 API가 이해하는 파라미터로 변환하는 헬퍼들.
이건 외산 MCP가 흉내낼 수 없는 로컬라이제이션 우위 영역.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────
# 업무구분 동의어 사전
# ─────────────────────────────────────────────────────────────
BUSINESS_TYPE_ALIASES: dict[str, str] = {
    # 물품
    "물품": "물품", "물자": "물품", "구매": "물품", "조달": "물품",
    "thing": "물품", "goods": "물품",
    # 용역
    "용역": "용역", "서비스": "용역", "컨설팅": "용역", "유지보수": "용역",
    "service": "용역",
    # 공사
    "공사": "공사", "건설": "공사", "토목": "공사", "건축": "공사",
    "construction": "공사",
    # 외자
    "외자": "외자", "수입": "외자", "해외조달": "외자",
    "foreign": "외자",
}


def normalize_business_type(value: str | None) -> str | None:
    """자연어 표현을 표준 업무구분(물품/용역/공사/외자)으로."""
    if not value:
        return None
    key = value.strip().lower()
    return BUSINESS_TYPE_ALIASES.get(key) or BUSINESS_TYPE_ALIASES.get(value.strip())


# ─────────────────────────────────────────────────────────────
# 자연어 날짜 표현 → YYYYMMDD
# ─────────────────────────────────────────────────────────────
_RELATIVE_DATE_RE = re.compile(
    r"(?:최근|지난|past|last)?\s*(\d+)\s*(일|주|개월|달|년|day|week|month|year)",
    re.IGNORECASE,
)


def parse_relative_date_range(expression: str | None) -> tuple[str, str] | None:
    """'최근 7일', '지난 3개월' 같은 표현 → (start, end) YYYYMMDD 튜플.

    매칭 실패 시 None 반환 (호출 측에서 다른 처리).
    """
    if not expression:
        return None

    today = datetime.now()

    # 특수 키워드
    text = expression.strip().lower()
    if text in ("오늘", "today"):
        s = today
        return s.strftime("%Y%m%d"), today.strftime("%Y%m%d")
    if text in ("어제", "yesterday"):
        s = today - timedelta(days=1)
        return s.strftime("%Y%m%d"), s.strftime("%Y%m%d")
    if text in ("이번주", "this week"):
        s = today - timedelta(days=today.weekday())
        return s.strftime("%Y%m%d"), today.strftime("%Y%m%d")
    if text in ("이번달", "this month"):
        s = today.replace(day=1)
        return s.strftime("%Y%m%d"), today.strftime("%Y%m%d")
    if text in ("올해", "this year"):
        s = today.replace(month=1, day=1)
        return s.strftime("%Y%m%d"), today.strftime("%Y%m%d")

    m = _RELATIVE_DATE_RE.search(expression)
    if not m:
        return None

    n = int(m.group(1))
    unit = m.group(2).lower()

    if unit in ("일", "day"):
        delta = timedelta(days=n)
    elif unit in ("주", "week"):
        delta = timedelta(weeks=n)
    elif unit in ("개월", "달", "month"):
        delta = timedelta(days=30 * n)
    elif unit in ("년", "year"):
        delta = timedelta(days=365 * n)
    else:
        return None

    start = today - delta
    return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")


# ─────────────────────────────────────────────────────────────
# 금액 자연어 표현 → int (원)
# ─────────────────────────────────────────────────────────────
_MONEY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(억|천만|백만|만|원|billion|million)?",
    re.IGNORECASE,
)


def parse_money(expression: str | None) -> int | None:
    """'5억', '3천만원', '1.5억', '500만' → 원 단위 int."""
    if expression is None:
        return None
    if isinstance(expression, (int, float)):
        return int(expression)

    text = str(expression).replace(",", "").replace("원", "").strip()
    m = _MONEY_RE.search(text)
    if not m:
        return None

    num = float(m.group(1))
    unit = (m.group(2) or "").lower()

    multiplier = 1
    if unit == "억":
        multiplier = 100_000_000
    elif unit == "천만":
        multiplier = 10_000_000
    elif unit == "백만" or unit == "million":
        multiplier = 1_000_000
    elif unit == "만":
        multiplier = 10_000
    elif unit == "billion":
        multiplier = 1_000_000_000

    return int(num * multiplier)


def format_money(amount: int | float | str | None) -> str:
    """원 단위 → '5억', '3,500만원' 형태 사람 친화적 포맷."""
    if amount is None or amount == "":
        return "-"
    try:
        n = int(float(amount))
    except (ValueError, TypeError):
        return str(amount)

    if n >= 100_000_000:
        eok = n // 100_000_000
        man = (n % 100_000_000) // 10_000
        if man:
            return f"{eok:,}억 {man:,}만원"
        return f"{eok:,}억원"
    if n >= 10_000:
        return f"{n // 10_000:,}만원"
    return f"{n:,}원"
