"""SQLite-backed persistent learning, reporting, and adaptation store for Lazarus."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


def default_db_path() -> Path:
    env_path = os.environ.get("LAZARUS_DB_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "data" / "lazarus.db"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LearningEntry:
    id: int
    topic: str
    content: str
    source: str
    tags: list[str]
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReportEntry:
    id: int
    title: str
    summary: str
    category: str
    confidence: float
    honest_gaps: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AdaptationEntry:
    id: int
    trigger: str
    change: str
    rationale: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class KnowledgeStore:
    """Durable SQLite memory for Lazarus learnings, transparent reports, and adaptations."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser().resolve() if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS learnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'direct-observation',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_learnings_topic ON learnings(topic);

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
                    honest_gaps TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS adaptations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger TEXT NOT NULL,
                    change TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def learn(
        self,
        topic: str,
        content: str,
        source: str = "direct-observation",
        tags: list[str] | None = None,
    ) -> LearningEntry:
        clean_tags = [t.strip() for t in (tags or []) if t.strip()]
        created_at = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO learnings (topic, content, source, tags_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    topic.strip(),
                    content.strip(),
                    source.strip(),
                    json.dumps(clean_tags),
                    created_at,
                ),
            )
            entry_id = int(cur.lastrowid or 0)
        return LearningEntry(
            id=entry_id,
            topic=topic.strip(),
            content=content.strip(),
            source=source.strip(),
            tags=clean_tags,
            created_at=created_at,
        )

    def recall(self, query: str = "", limit: int = 20) -> list[LearningEntry]:
        q = query.strip()
        with self._connect() as conn:
            if q:
                like = f"%{q}%"
                rows = conn.execute(
                    """
                    SELECT id, topic, content, source, tags_json, created_at
                    FROM learnings
                    WHERE topic LIKE ? OR content LIKE ? OR source LIKE ? OR tags_json LIKE ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (like, like, like, like, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, topic, content, source, tags_json, created_at
                    FROM learnings
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [
            LearningEntry(
                id=row["id"],
                topic=row["topic"],
                content=row["content"],
                source=row["source"],
                tags=json.loads(row["tags_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def log_report(
        self,
        title: str,
        summary: str,
        category: str = "general",
        confidence: float = 0.85,
        honest_gaps: str = "",
    ) -> ReportEntry:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        created_at = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO reports (title, summary, category, confidence, honest_gaps, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    summary.strip(),
                    category.strip(),
                    float(confidence),
                    honest_gaps.strip(),
                    created_at,
                ),
            )
            entry_id = int(cur.lastrowid or 0)
        return ReportEntry(
            id=entry_id,
            title=title.strip(),
            summary=summary.strip(),
            category=category.strip(),
            confidence=float(confidence),
            honest_gaps=honest_gaps.strip(),
            created_at=created_at,
        )

    def list_reports(self, limit: int = 20) -> list[ReportEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, summary, category, confidence, honest_gaps, created_at
                FROM reports
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            ReportEntry(
                id=row["id"],
                title=row["title"],
                summary=row["summary"],
                category=row["category"],
                confidence=row["confidence"],
                honest_gaps=row["honest_gaps"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def record_adaptation(self, trigger: str, change: str, rationale: str) -> AdaptationEntry:
        created_at = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO adaptations (trigger, change, rationale, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (trigger.strip(), change.strip(), rationale.strip(), created_at),
            )
            entry_id = int(cur.lastrowid or 0)
        return AdaptationEntry(
            id=entry_id,
            trigger=trigger.strip(),
            change=change.strip(),
            rationale=rationale.strip(),
            created_at=created_at,
        )

    def list_adaptations(self, limit: int = 20) -> list[AdaptationEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, trigger, change, rationale, created_at
                FROM adaptations
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            AdaptationEntry(
                id=row["id"],
                trigger=row["trigger"],
                change=row["change"],
                rationale=row["rationale"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            learnings_count = conn.execute("SELECT COUNT(*) FROM learnings").fetchone()[0]
            reports_count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
            adaptations_count = conn.execute("SELECT COUNT(*) FROM adaptations").fetchone()[0]
        return {
            "learnings": int(learnings_count),
            "reports": int(reports_count),
            "adaptations": int(adaptations_count),
        }
