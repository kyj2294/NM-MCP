"""공통 나라장터 API 클라이언트.

모든 6개 서비스(bid/award/contract/lifecycle/request/shopping)가 공유하는
HTTP 호출, 캐싱, 재시도, 응답 정규화 로직을 한 곳에 모은다.

설계 원칙:
- 응답 포맷이 XML/JSON 혼재 가능 → 항상 JSON 요청 (`type=json`)
- 공공데이터포털 트래픽 제한 대응 → in-memory TTL 캐시
- 모든 응답을 표준 형식으로 정규화
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import httpx

from ..config import (
    API_BASE,
    DEFAULT_PAGE_SIZE,
    HTTP_RETRIES,
    HTTP_TIMEOUT,
    MAX_PAGE_SIZE,
    SERVICE_PATHS,
    USER_AGENT,
    Settings,
)

logger = logging.getLogger(__name__)


class NaraAPIError(Exception):
    """나라장터 API 호출 실패."""

    def __init__(self, message: str, *, code: str | None = None, raw: Any = None):
        super().__init__(message)
        self.code = code
        self.raw = raw


class _TTLCache:
    """간단한 in-memory TTL 캐시. 트래픽 제한 대응용."""

    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if not entry:
            return None
        ts, value = entry
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)

    def clear(self) -> None:
        self._store.clear()


class NaraClient:
    """나라장터 6개 API 통합 클라이언트.

    Usage:
        async with NaraClient(settings) as client:
            data = await client.call("bid", "getBidPblancListInfoServcPPSSrch", {...})
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache = _TTLCache(settings.cache_ttl)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> NaraClient:
        self._client = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ────────────────────────────────────────────────────────
    # 핵심 호출 메서드
    # ────────────────────────────────────────────────────────
    async def call(
        self,
        service: str,
        operation: str,
        params: dict[str, Any] | None = None,
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """API 호출.

        Args:
            service: 'bid' | 'award' | 'contract' | 'lifecycle' | 'request' | 'shopping'
            operation: 오퍼레이션명 (예: 'getBidPblancListInfoServcPPSSrch')
            params: 추가 쿼리 파라미터
            use_cache: TTL 캐시 사용 여부 (기본 True)

        Returns:
            정규화된 응답 dict:
                {
                    "items": [...],         # 리스트 결과
                    "total_count": int,
                    "page_no": int,
                    "num_of_rows": int,
                    "raw": {...}            # 원본 (디버깅용)
                }
        """
        if service not in SERVICE_PATHS:
            raise NaraAPIError(f"알 수 없는 서비스: {service}")

        if self._client is None:
            raise NaraAPIError("클라이언트가 초기화되지 않았습니다 (async with 사용 필요)")

        # 파라미터 빌드
        full_params = self._build_params(params or {})
        url = f"{API_BASE}{SERVICE_PATHS[service]}/{operation}"

        # 캐시 체크
        cache_key = self._cache_key(url, full_params)
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("cache hit: %s/%s", service, operation)
                return cached

        # HTTP 호출 (재시도 포함)
        raw = await self._http_get_with_retry(url, full_params)

        # 응답 정규화
        normalized = self._normalize(raw)

        if use_cache:
            self._cache.set(cache_key, normalized)

        return normalized

    # ────────────────────────────────────────────────────────
    # 내부 헬퍼
    # ────────────────────────────────────────────────────────
    def _build_params(self, user_params: dict[str, Any]) -> dict[str, Any]:
        """ServiceKey + 기본 파라미터 + 사용자 파라미터 병합."""
        params: dict[str, Any] = {
            "serviceKey": self.settings.api_key,
            "type": "json",
            "numOfRows": DEFAULT_PAGE_SIZE,
            "pageNo": 1,
        }
        # None 값 제거
        for k, v in user_params.items():
            if v is not None:
                params[k] = v

        # 페이지 크기 상한
        if int(params.get("numOfRows", DEFAULT_PAGE_SIZE)) > MAX_PAGE_SIZE:
            params["numOfRows"] = MAX_PAGE_SIZE

        return params

    async def _http_get_with_retry(
        self, url: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """재시도 포함 HTTP GET."""
        assert self._client is not None
        last_error: Exception | None = None

        for attempt in range(HTTP_RETRIES + 1):
            try:
                response = await self._client.get(url, params=params)
                response.raise_for_status()

                # 일부 API는 에러 시에도 200을 주고 본문에 에러를 담음
                # JSON 파싱 시도, 실패하면 텍스트 본문 노출
                try:
                    return response.json()
                except json.JSONDecodeError:
                    text = response.text[:500]
                    raise NaraAPIError(
                        f"JSON 파싱 실패. 본문 일부: {text}",
                        raw=response.text,
                    ) from None

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    "HTTP %s on attempt %d: %s",
                    e.response.status_code,
                    attempt + 1,
                    url,
                )
                # 4xx는 재시도 의미 없음
                if 400 <= e.response.status_code < 500:
                    raise NaraAPIError(
                        f"클라이언트 오류 ({e.response.status_code}): {e.response.text[:300]}",
                        code=str(e.response.status_code),
                    ) from e
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                logger.warning("network error on attempt %d: %s", attempt + 1, e)

            # 백오프 후 재시도
            if attempt < HTTP_RETRIES:
                await asyncio.sleep(0.5 * (2 ** attempt))

        raise NaraAPIError(
            f"API 호출 실패 (최대 재시도 도달): {last_error}",
        ) from last_error

    @staticmethod
    def _cache_key(url: str, params: dict[str, Any]) -> str:
        """URL + 파라미터를 결정론적으로 해싱."""
        # serviceKey는 캐시 키에서 제외 (로그 노출 방지)
        sanitized = {k: v for k, v in params.items() if k != "serviceKey"}
        payload = url + "?" + json.dumps(sanitized, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
        """공공데이터포털 표준 응답을 평탄화.

        표준 응답 구조:
            {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                    "body": {
                        "items": [...] or {...},
                        "totalCount": int,
                        "pageNo": int,
                        "numOfRows": int
                    }
                }
            }
        """
        response = raw.get("response", {})
        header = response.get("header", {})
        body = response.get("body", {})

        # 에러 체크
        result_code = header.get("resultCode")
        if result_code and result_code not in ("00", "0"):
            msg = header.get("resultMsg", "Unknown error")
            raise NaraAPIError(
                f"API 에러 (code={result_code}): {msg}",
                code=result_code,
                raw=raw,
            )

        # items가 단일 객체일 때도 있고 리스트일 때도 있음 → 항상 리스트로
        items = body.get("items", [])
        if isinstance(items, dict):
            # 일부 API는 {"item": [...]} 형태로 한 단계 더 감쌈
            inner = items.get("item", [])
            items = inner if isinstance(inner, list) else [inner] if inner else []
        elif not isinstance(items, list):
            items = []

        return {
            "items": items,
            "total_count": int(body.get("totalCount", 0) or 0),
            "page_no": int(body.get("pageNo", 1) or 1),
            "num_of_rows": int(body.get("numOfRows", 0) or 0),
            "raw": raw,
        }

    def clear_cache(self) -> None:
        self._cache.clear()
