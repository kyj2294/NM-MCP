"""analytics/fit_scorer 단위 테스트.

내부 헬퍼들은 모듈 private이지만, 점수 알고리즘이 핵심 로직이므로
직접 import해서 검증한다.
"""
from narajangteo_pro.analytics.fit_scorer import (
    _score_license_match,
    _score_prior_contract_fit,
    _score_revenue_fit,
)


# ─────────────────────────────────────────────────────────────
# 면허 매칭
# ─────────────────────────────────────────────────────────────
class TestLicenseMatch:
    def test_요구_면허_없으면_중간점수(self):
        score, reason = _score_license_match([], ["소프트웨어개발업"])
        assert score == 80.0
        assert "확인 필요" in reason

    def test_모두_보유시_만점(self):
        score, _ = _score_license_match(
            ["소프트웨어개발업"],
            ["소프트웨어개발업", "정보통신공사업"],
        )
        assert score == 100.0

    def test_전혀_없으면_0점(self):
        score, reason = _score_license_match(
            ["전기공사업"],
            ["소프트웨어개발업"],
        )
        assert score == 0.0
        assert "미보유" in reason

    def test_부분_보유시_비례_점수(self):
        score, reason = _score_license_match(
            ["A업", "B업", "C업", "D업"],
            ["A업", "B업"],
        )
        assert score == 50.0  # 2/4
        assert "일부 면허 보유" in reason

    def test_부분_문자열_매칭(self):
        """면허명이 정확히 같지 않아도 부분 일치하면 인정"""
        score, _ = _score_license_match(
            ["소프트웨어개발업"],
            ["소프트웨어개발"],  # 끝의 '업'이 빠진 형태
        )
        assert score == 100.0


# ─────────────────────────────────────────────────────────────
# 매출 적합도
# ─────────────────────────────────────────────────────────────
class TestRevenueFit:
    def test_매출_3배_이상은_만점(self):
        score, reason = _score_revenue_fit(
            estimated_price=100_000_000,  # 1억
            revenue=400_000_000,  # 4억 (4배)
        )
        assert score == 100.0
        assert "충분" in reason

    def test_매출_적정은_80점대(self):
        score, _ = _score_revenue_fit(100_000_000, 200_000_000)  # 2배
        assert score == 80.0

    def test_매출_빠듯하면_60점(self):
        score, reason = _score_revenue_fit(100_000_000, 120_000_000)  # 1.2배
        assert score == 60.0
        assert "컨소시엄" in reason

    def test_매출_부족시_저점수(self):
        score, _ = _score_revenue_fit(1_000_000_000, 600_000_000)  # 0.6배
        assert score == 30.0

    def test_매출_과다는_경고(self):
        score, reason = _score_revenue_fit(10_000_000_000, 100_000_000)  # 0.01배
        assert score == 10.0
        assert "과다" in reason

    def test_매출_정보_없으면_50점(self):
        score, reason = _score_revenue_fit(100_000_000, None)
        assert score == 50.0
        assert "프로필 등록" in reason

    def test_추정가_정보_없으면_70점(self):
        score, _ = _score_revenue_fit(None, 1_000_000_000)
        assert score == 70.0


# ─────────────────────────────────────────────────────────────
# 과거 실적
# ─────────────────────────────────────────────────────────────
class TestPriorContractFit:
    def test_실적_없으면_저점수(self):
        score, reason = _score_prior_contract_fit([], "AI")
        assert score == 30.0
        assert "없음" in reason

    def test_관련_없는_실적만_있으면_중간(self):
        score, reason = _score_prior_contract_fit(
            [{"name": "회계 시스템 구축", "category": "ERP"}],
            "AI",
        )
        assert score == 40.0

    def test_유사_실적_많을수록_고점수(self):
        contracts = [
            {"name": "AI 챗봇 개발", "category": "AI"},
            {"name": "AI 분석 시스템", "category": "AI"},
            {"name": "AI 추천 엔진", "category": "AI"},
        ]
        score, reason = _score_prior_contract_fit(contracts, "AI")
        assert score >= 80.0
        assert "유사 실적" in reason

    def test_점수_상한_100(self):
        contracts = [{"name": f"AI 프로젝트 {i}", "category": "AI"} for i in range(20)]
        score, _ = _score_prior_contract_fit(contracts, "AI")
        assert score <= 100.0
