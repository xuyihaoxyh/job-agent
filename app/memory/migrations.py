from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import aiosqlite

Migration = Callable[[aiosqlite.Connection], Awaitable[None]]


async def _columns(connection: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await connection.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in await cursor.fetchall()}


async def _migration_1(connection: aiosqlite.Connection) -> None:
    await connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS analysis_threads (
            thread_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )


async def _migration_2(connection: aiosqlite.Connection) -> None:
    columns = await _columns(connection, "analysis_threads")
    additions = {
        "company_name": "TEXT",
        "job_title": "TEXT",
        "status": "TEXT NOT NULL DEFAULT 'completed'",
        "match_score": "INTEGER",
        "recommendation": "TEXT",
        "updated_at": "TEXT",
    }
    for name, declaration in additions.items():
        if name not in columns:
            await connection.execute(
                f"ALTER TABLE analysis_threads ADD COLUMN {name} {declaration}"
            )
    await connection.execute(
        "UPDATE analysis_threads SET updated_at = created_at WHERE updated_at IS NULL"
    )


async def _migration_3(connection: aiosqlite.Connection) -> None:
    await connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
            ON auth_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_threads_user_updated
            ON analysis_threads(user_id, updated_at DESC);
        """
    )


MIGRATIONS: tuple[Migration, ...] = (
    _migration_1,
    _migration_2,
    _migration_3,
)


class SQLiteMigrationRunner:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def migrate(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.execute("PRAGMA busy_timeout=5000")
            await connection.execute("PRAGMA foreign_keys=ON")
            cursor = await connection.execute("PRAGMA user_version")
            row = await cursor.fetchone()
            current_version = int(row[0]) if row else 0
            for version, migration in enumerate(MIGRATIONS, start=1):
                if version <= current_version:
                    continue
                await migration(connection)
                await connection.execute(f"PRAGMA user_version={version}")
                await connection.commit()
