from __future__ import annotations

import aiosqlite
import pytest

from app.memory.migrations import MIGRATIONS, SQLiteMigrationRunner


@pytest.mark.asyncio
async def test_migrations_are_versioned_and_idempotent(tmp_path):
    database = tmp_path / "app.db"
    runner = SQLiteMigrationRunner(database)

    await runner.migrate()
    await runner.migrate()

    async with aiosqlite.connect(database) as connection:
        cursor = await connection.execute("PRAGMA user_version")
        assert (await cursor.fetchone())[0] == len(MIGRATIONS)
        cursor = await connection.execute("PRAGMA table_info(analysis_threads)")
        columns = {row[1] for row in await cursor.fetchall()}

    assert {
        "company_name",
        "job_title",
        "status",
        "match_score",
        "recommendation",
        "updated_at",
    } <= columns


@pytest.mark.asyncio
async def test_migrations_upgrade_existing_v1_database(tmp_path):
    database = tmp_path / "legacy.db"
    async with aiosqlite.connect(database) as connection:
        await connection.executescript(
            """
            CREATE TABLE users (id TEXT PRIMARY KEY);
            CREATE TABLE auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE analysis_threads (
                thread_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        await connection.execute("PRAGMA user_version=1")
        await connection.commit()

    await SQLiteMigrationRunner(database).migrate()

    async with aiosqlite.connect(database) as connection:
        cursor = await connection.execute("PRAGMA table_info(analysis_threads)")
        columns = {row[1] for row in await cursor.fetchall()}
    assert "match_score" in columns
    assert "updated_at" in columns
