"""환경설정 및 상수.

모든 환경변수와 API 엔드포인트를 한 곳에서 관리한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────────────────────
# API 엔드포인트
# ─────────────────────────────────────────────────────────────
API_BASE: Final[str] = "http://apis.data.go.kr/1230000"

# 6개 API 서비스 경로
SERVICE_PATHS: Final[dict[str, str]] = {
    "bid": "/ad/BidPublicInfoService",                     # 입찰공고정보
    "award": "/as/ScsbidInfoService",                      # 낙찰정보
    "contract": "/ao/CntrctInfoService",                   # 계약정보
    "lifecycle": "/ao/CntrctProcssIntgOpenService",        # 계약과정통합공개 ⭐
    "request": "/ao/PrcrmntReqstInfoService",              # 조달요청
    "shopping": "/at/ShoppingMallPrdctInfoService",        # 종합쇼핑몰 품목
}


# ─────────────────────────────────────────────────────────────
# 업무구분 (모든 API 공통)
# ─────────────────────────────────────────────────────────────
BUSINESS_TYPES: Final[tuple[str, ...]] = ("물품", "용역", "공사", "외자")

# 업무구분 → API 오퍼레이션 접미사 매핑
# 예) 입찰공고목록 조회 시:
#   - 물품: getBidPblancListInfoThngPPSSrch
#   - 용역: getBidPblancListInfoServcPPSSrch
#   - 공사: getBidPblancListInfoCnstwkPPSSrch
#   - 외자: getBidPblancListInfoFrgcptPPSSrch
BUSINESS_TYPE_SUFFIX: Final[dict[str, str]] = {
    "물품": "Thng",
    "용역": "Servc",
    "공사": "Cnstwk",
    "외자": "Frgcpt",
}


# ─────────────────────────────────────────────────────────────
# 환경설정 로드
# ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Settings:
    """런타임 환경설정. 환경변수에서 로드."""

    api_key: str
    transport: str
    http_host: str
    http_port: int
    state_db_path: Path
    cache_ttl: int
    log_level: str

    @classmethod
    def load(cls) -> Settings:
        api_key = os.getenv("NARA_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "NARA_API_KEY 환경변수가 설정되지 않았습니다. "
                "공공데이터포털(https://www.data.go.kr)에서 발급받은 ServiceKey의 "
                "Decoding 값을 NARA_API_KEY로 설정하세요."
            )

        # 상태 DB 경로 (기본: ~/.narajangteo-pro/state.db)
        db_path_env = os.getenv("STATE_DB_PATH", "").strip()
        if db_path_env:
            db_path = Path(db_path_env).expanduser().resolve()
        else:
            db_path = Path.home() / ".narajangteo-pro" / "state.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        return cls(
            api_key=api_key,
            transport=os.getenv("TRANSPORT", "stdio").lower(),
            http_host=os.getenv("HTTP_HOST", "0.0.0.0"),
            http_port=int(os.getenv("HTTP_PORT", "8000")),
            state_db_path=db_path,
            cache_ttl=int(os.getenv("CACHE_TTL", "300")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


# ─────────────────────────────────────────────────────────────
# HTTP 클라이언트 설정
# ─────────────────────────────────────────────────────────────
HTTP_TIMEOUT: Final[float] = 30.0
HTTP_RETRIES: Final[int] = 2
USER_AGENT: Final[str] = "narajangteo-pro/0.1.0"
DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 100
