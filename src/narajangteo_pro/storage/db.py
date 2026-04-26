"""SQLite 기반 상태 저장소.

기존 narajangteo_mcp_server는 stateless. 우리는 다음을 영속 저장:
- 관심 키워드 (watchlist) — 신규 공고 모니터링
- 회사 프로필 — 적합도 평가에 재사용
- 최근 검색/조회 이력 (선택)

DB 위치는 settings.state_db_path (기본 ~/.narajangteo-pro/state.db).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    business_type TEXT,
    institution TEXT,
    created_at TEXT NOT NULL,
    last_checked_at TEXT,
    UNIQUE(keyword, business_type, institution)
);

CREATE TABLE IF NOT EXISTS company_profile (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    licenses_json TEXT NOT NULL DEFAULT '[]',
    certifications_json TEXT NOT NULL DEFAULT '[]',
    revenue INTEGER,
    prior_contracts_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_bid (
    bid_notice_no TEXT NOT NULL,
    watch_id INTEGER NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (bid_notice_no, watch_id),
    FOREIGN KEY (watch_id) REFERENCES watchlist(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_watchlist_keyword ON watchlist(keyword);
CREATE INDEX IF NOT EXISTS idx_seen_bid_watch ON seen_bid(watch_id);
"""


class StateStore:
    """SQLite 상태 저장소.

    스레드 단위 연결을 사용하지 않고, 매 호출마다 짧은 연결을 연다.
    동시성이 낮은 로컬 도구라 충분.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_SQL)
            current = conn.execute(
                "SELECT version FROM schema_version LIMIT 1"
            ).fetchone()
            if current is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )

    # ─── Watchlist ───────────────────────────────────────────
    def add_watch(
        self,
        keyword: str,
        business_type: str | None = None,
        institution: str | None = None,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            # 먼저 기존 항목이 있는지 조회 (UPSERT가 lastrowid 동작이 SQLite 버전마다 달라
            # 명시적 SELECT-then-INSERT 패턴이 가장 안전)
            row = conn.execute(
                """
                SELECT id FROM watchlist
                WHERE keyword = ?
                  AND IFNULL(business_type, '') = IFNULL(?, '')
                  AND IFNULL(institution, '') = IFNULL(?, '')
                """,
                (keyword, business_type, institution),
            ).fetchone()
            if row:
                return int(row["id"])

            cur = conn.execute(
                """
                INSERT INTO watchlist (keyword, business_type, institution, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (keyword, business_type, institution, now),
            )
            return int(cur.lastrowid) if cur.lastrowid else -1

    def remove_watch(self, watch_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM watchlist WHERE id = ?", (watch_id,))
            return cur.rowcount > 0

    def list_watches(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_seen(self, watch_id: int, bid_notice_no: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO seen_bid (bid_notice_no, watch_id, seen_at)
                VALUES (?, ?, ?)
                """,
                (bid_notice_no, watch_id, now),
            )

    def filter_unseen(self, watch_id: int, bid_notice_nos: list[str]) -> list[str]:
        if not bid_notice_nos:
            return []
        with self._conn() as conn:
            placeholders = ",".join("?" * len(bid_notice_nos))
            rows = conn.execute(
                f"""
                SELECT bid_notice_no FROM seen_bid
                WHERE watch_id = ? AND bid_notice_no IN ({placeholders})
                """,
                (watch_id, *bid_notice_nos),
            ).fetchall()
            seen = {r["bid_notice_no"] for r in rows}
            return [b for b in bid_notice_nos if b not in seen]

    def update_last_checked(self, watch_id: int) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            conn.execute(
                "UPDATE watchlist SET last_checked_at = ? WHERE id = ?",
                (now, watch_id),
            )

    # ─── Company profile ────────────────────────────────────
    def save_profile(
        self,
        profile_id: str,
        name: str,
        *,
        licenses: list[str] | None = None,
        certifications: list[str] | None = None,
        revenue: int | None = None,
        prior_contracts: list[dict] | None = None,
        notes: str | None = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM company_profile WHERE id = ?", (profile_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE company_profile
                    SET name=?, licenses_json=?, certifications_json=?,
                        revenue=?, prior_contracts_json=?, notes=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        name,
                        json.dumps(licenses or [], ensure_ascii=False),
                        json.dumps(certifications or [], ensure_ascii=False),
                        revenue,
                        json.dumps(prior_contracts or [], ensure_ascii=False),
                        notes,
                        now,
                        profile_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO company_profile
                        (id, name, licenses_json, certifications_json,
                         revenue, prior_contracts_json, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        name,
                        json.dumps(licenses or [], ensure_ascii=False),
                        json.dumps(certifications or [], ensure_ascii=False),
                        revenue,
                        json.dumps(prior_contracts or [], ensure_ascii=False),
                        notes,
                        now,
                        now,
                    ),
                )

    def load_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM company_profile WHERE id = ?", (profile_id,)
            ).fetchone()
            if not row:
                return None
            return self._profile_row_to_dict(row)

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM company_profile ORDER BY updated_at DESC"
            ).fetchall()
            return [self._profile_row_to_dict(r) for r in rows]

    def delete_profile(self, profile_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM company_profile WHERE id = ?", (profile_id,)
            )
            return cur.rowcount > 0

    @staticmethod
    def _profile_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["licenses"] = json.loads(d.pop("licenses_json", "[]"))
        d["certifications"] = json.loads(d.pop("certifications_json", "[]"))
        d["prior_contracts"] = json.loads(d.pop("prior_contracts_json", "[]"))
        return d
