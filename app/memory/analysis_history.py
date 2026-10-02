from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from app.memory.migrations import SQLiteMigrationRunner
from app.schemas.history import AnalysisHistoryItem


class SQLiteAnalysisHistoryRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def setup(self) -> None:
        await SQLiteMigrationRunner(self._database_path).migrate()

    async def record(
        self,
        *,
        thread_id: str,
        user_id: str,
        company_name: str,
        job_title: str | None,
        status: str,
        match_score: int | None,
        recommendation: str | None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            await connection.execute(
                """
                INSERT INTO analysis_threads (
                    thread_id, user_id, company_name, job_title, status,
                    match_score, recommendation, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    company_name = excluded.company_name,
                    job_title = excluded.job_title,
                    status = excluded.status,
                    match_score = excluded.match_score,
                    recommendation = excluded.recommendation,
                    updated_at = excluded.updated_at
                WHERE analysis_threads.user_id = excluded.user_id
                """,
                (
                    thread_id,
                    user_id,
                    company_name,
                    job_title,
                    status,
                    match_score,
                    recommendation,
                    now,
                    now,
                ),
            )
            await connection.commit()

    async def list_for_user(self, user_id: str, *, limit: int = 20) -> list[AnalysisHistoryItem]:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            cursor = await connection.execute(
                """
                SELECT thread_id, company_name, job_title, status, match_score,
                       recommendation, created_at, COALESCE(updated_at, created_at)
                FROM analysis_threads
                WHERE user_id = ?
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()
        return [
            AnalysisHistoryItem(
                thread_id=row[0],
                company_name=row[1] or "历史分析",
                job_title=row[2],
                status=row[3] or "completed",
                match_score=row[4],
                recommendation=row[5],
                created_at=datetime.fromisoformat(row[6]),
                updated_at=datetime.fromisoformat(row[7]),
            )
            for row in rows
        ]
