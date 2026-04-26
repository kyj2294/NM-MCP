"""storage/db 단위 테스트."""
from pathlib import Path

import pytest

from narajangteo_pro.storage.db import StateStore


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    """매 테스트마다 깨끗한 임시 DB."""
    db_path = tmp_path / "test.db"
    return StateStore(db_path)


# ─────────────────────────────────────────────────────────────
# Watchlist
# ─────────────────────────────────────────────────────────────
class TestWatchlist:
    def test_등록과_목록(self, store):
        wid = store.add_watch("AI 챗봇", "용역", "행정안전부")
        assert wid > 0

        watches = store.list_watches()
        assert len(watches) == 1
        assert watches[0]["keyword"] == "AI 챗봇"
        assert watches[0]["business_type"] == "용역"
        assert watches[0]["institution"] == "행정안전부"

    def test_중복_등록은_같은_id_반환(self, store):
        wid1 = store.add_watch("클라우드", "용역")
        wid2 = store.add_watch("클라우드", "용역")
        assert wid1 == wid2
        assert len(store.list_watches()) == 1

    def test_제거(self, store):
        wid = store.add_watch("키워드", "용역")
        assert store.remove_watch(wid) is True
        assert len(store.list_watches()) == 0

    def test_없는_id_제거시_False(self, store):
        assert store.remove_watch(99999) is False

    def test_seen_관리(self, store):
        wid = store.add_watch("AI", "용역")
        # 처음에는 모두 unseen
        candidates = ["BID001", "BID002", "BID003"]
        unseen = store.filter_unseen(wid, candidates)
        assert set(unseen) == set(candidates)

        # 하나 mark_seen 후
        store.mark_seen(wid, "BID001")
        unseen = store.filter_unseen(wid, candidates)
        assert "BID001" not in unseen
        assert "BID002" in unseen
        assert "BID003" in unseen

    def test_seen은_watch별로_독립(self, store):
        wid1 = store.add_watch("a", "용역")
        wid2 = store.add_watch("b", "용역")
        store.mark_seen(wid1, "BID001")
        # wid1에서는 seen, wid2에서는 unseen
        assert store.filter_unseen(wid1, ["BID001"]) == []
        assert store.filter_unseen(wid2, ["BID001"]) == ["BID001"]

    def test_watch_삭제시_seen도_cascade_삭제(self, store):
        wid = store.add_watch("키워드", "용역")
        store.mark_seen(wid, "BID001")
        store.remove_watch(wid)
        # cascade로 seen_bid도 같이 삭제됨 (FK ON DELETE CASCADE)
        # 새로 만든 watch에서 같은 BID001은 다시 unseen
        new_wid = store.add_watch("키워드", "용역")
        assert store.filter_unseen(new_wid, ["BID001"]) == ["BID001"]


# ─────────────────────────────────────────────────────────────
# Company profile
# ─────────────────────────────────────────────────────────────
class TestCompanyProfile:
    def test_저장과_로드(self, store):
        store.save_profile(
            "acme",
            name="ACME Corp",
            licenses=["소프트웨어개발업", "정보통신공사업"],
            certifications=["ISO27001"],
            revenue=10_000_000_000,
            prior_contracts=[
                {"name": "A기관 챗봇 구축", "amount": 500_000_000}
            ],
            notes="중소기업 확인 보유",
        )
        profile = store.load_profile("acme")
        assert profile is not None
        assert profile["name"] == "ACME Corp"
        assert profile["licenses"] == ["소프트웨어개발업", "정보통신공사업"]
        assert profile["certifications"] == ["ISO27001"]
        assert profile["revenue"] == 10_000_000_000
        assert len(profile["prior_contracts"]) == 1
        assert profile["prior_contracts"][0]["name"] == "A기관 챗봇 구축"
        assert profile["notes"] == "중소기업 확인 보유"

    def test_같은_id로_저장시_업데이트(self, store):
        store.save_profile("x", name="처음 이름", revenue=1_000_000)
        store.save_profile("x", name="바뀐 이름", revenue=2_000_000)
        p = store.load_profile("x")
        assert p["name"] == "바뀐 이름"
        assert p["revenue"] == 2_000_000
        # 여전히 1개만 존재
        assert len(store.list_profiles()) == 1

    def test_없는_프로필_로드시_None(self, store):
        assert store.load_profile("nonexistent") is None

    def test_삭제(self, store):
        store.save_profile("y", name="Y")
        assert store.delete_profile("y") is True
        assert store.load_profile("y") is None

    def test_한국어_프로필(self, store):
        """한국어 데이터가 깨지지 않는지 확인."""
        store.save_profile(
            "한국기업",
            name="한국주식회사",
            licenses=["전기공사업", "소방시설공사업"],
            notes="대표이사 홍길동",
        )
        p = store.load_profile("한국기업")
        assert p["name"] == "한국주식회사"
        assert "전기공사업" in p["licenses"]
        assert p["notes"] == "대표이사 홍길동"
