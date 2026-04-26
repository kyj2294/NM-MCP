"""utils/nl_mapping 단위 테스트."""
from datetime import datetime, timedelta

from narajangteo_pro.utils.nl_mapping import (
    format_money,
    normalize_business_type,
    parse_money,
    parse_relative_date_range,
)


# ─────────────────────────────────────────────────────────────
# 업무구분 정규화
# ─────────────────────────────────────────────────────────────
class TestBusinessType:
    def test_표준_명칭은_그대로_통과(self):
        assert normalize_business_type("물품") == "물품"
        assert normalize_business_type("용역") == "용역"
        assert normalize_business_type("공사") == "공사"
        assert normalize_business_type("외자") == "외자"

    def test_동의어_매핑(self):
        assert normalize_business_type("서비스") == "용역"
        assert normalize_business_type("건설") == "공사"
        assert normalize_business_type("구매") == "물품"
        assert normalize_business_type("수입") == "외자"

    def test_영문_매핑(self):
        assert normalize_business_type("service") == "용역"
        assert normalize_business_type("Service") == "용역"  # 대소문자 무관
        assert normalize_business_type("construction") == "공사"

    def test_미지의_값은_None(self):
        assert normalize_business_type("xyz") is None
        assert normalize_business_type("") is None
        assert normalize_business_type(None) is None


# ─────────────────────────────────────────────────────────────
# 자연어 날짜 → YYYYMMDD 범위
# ─────────────────────────────────────────────────────────────
class TestRelativeDate:
    def test_최근_N일(self):
        result = parse_relative_date_range("최근 7일")
        assert result is not None
        start, end = result
        assert len(start) == 8
        assert len(end) == 8
        # 종료일이 오늘
        assert end == datetime.now().strftime("%Y%m%d")
        # 시작일은 7일 전
        expected_start = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
        assert start == expected_start

    def test_지난_3개월(self):
        result = parse_relative_date_range("지난 3개월")
        assert result is not None
        start, end = result
        # 90일 = 3개월 근사
        expected_start = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        assert start == expected_start

    def test_특수_키워드_오늘(self):
        result = parse_relative_date_range("오늘")
        today = datetime.now().strftime("%Y%m%d")
        assert result == (today, today)

    def test_특수_키워드_올해(self):
        result = parse_relative_date_range("올해")
        assert result is not None
        start, end = result
        # 시작은 1월 1일
        year = datetime.now().year
        assert start == f"{year}0101"

    def test_영문도_매핑(self):
        result = parse_relative_date_range("last 30 days")
        assert result is not None
        start, _ = result
        expected = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        assert start == expected

    def test_매칭_실패는_None(self):
        assert parse_relative_date_range("이상한 표현") is None
        assert parse_relative_date_range(None) is None
        assert parse_relative_date_range("") is None


# ─────────────────────────────────────────────────────────────
# 금액 파싱
# ─────────────────────────────────────────────────────────────
class TestMoneyParse:
    def test_억_단위(self):
        assert parse_money("5억") == 500_000_000
        assert parse_money("1.5억") == 150_000_000
        assert parse_money("100억원") == 10_000_000_000

    def test_천만_백만_만_단위(self):
        assert parse_money("3천만") == 30_000_000
        assert parse_money("500만") == 5_000_000
        assert parse_money("50백만") == 50_000_000

    def test_숫자만_들어오면_int_그대로(self):
        assert parse_money(500_000_000) == 500_000_000
        assert parse_money("1234567") == 1234567

    def test_콤마와_원_단위_제거(self):
        assert parse_money("1,000,000원") == 1_000_000

    def test_파싱_실패는_None(self):
        assert parse_money(None) is None
        # 빈 문자열은 정규식이 매칭 못 하므로 None
        assert parse_money("") is None
        assert parse_money("abc") is None


# ─────────────────────────────────────────────────────────────
# 금액 포맷
# ─────────────────────────────────────────────────────────────
class TestMoneyFormat:
    def test_억_표시(self):
        assert format_money(500_000_000) == "5억원"
        assert format_money(150_000_000) == "1억 5,000만원"

    def test_만_표시(self):
        assert format_money(50_000) == "5만원"
        assert format_money(1_500_000) == "150만원"

    def test_원_단위(self):
        assert format_money(500) == "500원"

    def test_None과_빈값(self):
        assert format_money(None) == "-"
        assert format_money("") == "-"

    def test_왕복_변환_일관성(self):
        """parse → format → parse가 동일해야"""
        original = "5억"
        parsed = parse_money(original)
        formatted = format_money(parsed)
        re_parsed = parse_money(formatted)
        assert re_parsed == parsed
