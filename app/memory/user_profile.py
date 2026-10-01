from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from app.memory.migrations import SQLiteMigrationRunner
from app.schemas.domain import UserProfile


class SQLiteUserProfileRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def setup(self) -> None:
        await SQLiteMigrationRunner(self._database_path).migrate()

    async def get(self, user_id: str) -> UserProfile | None:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            cursor = await connection.execute(
                "SELECT profile_json FROM user_profiles WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return UserProfile.model_validate(json.loads(row[0]))

    async def upsert(self, user_id: str, profile: UserProfile) -> None:
        payload = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False)
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            await connection.execute(
                """
                INSERT INTO user_profiles (user_id, profile_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, payload),
            )
            await connection.commit()
