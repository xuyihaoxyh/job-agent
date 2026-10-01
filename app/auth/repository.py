from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3
import uuid

import aiosqlite

from app.auth.security import hash_password, new_session_token, token_digest, verify_password
from app.schemas.auth import AuthUser


class DuplicateUserError(ValueError):
    pass


class SQLiteAuthRepository:
    def __init__(self, database_path: Path, session_ttl_hours: int = 168) -> None:
        self._database_path = database_path
        self._session_ttl_hours = session_ttl_hours

    async def setup(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.execute("PRAGMA busy_timeout=5000")
            await connection.execute("PRAGMA foreign_keys=ON")
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
                CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
                    ON auth_sessions(user_id);
                CREATE TABLE IF NOT EXISTS analysis_threads (
                    thread_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            await connection.execute("PRAGMA user_version=1")
            await connection.commit()

    async def create_user(
        self, username: str, email: str, password: str, display_name: str | None = None
    ) -> AuthUser:
        user_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        normalized_username = username.strip()
        normalized_email = email.strip().lower()
        name = (display_name or normalized_username).strip()
        try:
            async with aiosqlite.connect(self._database_path) as connection:
                await connection.execute("PRAGMA busy_timeout=5000")
                await connection.execute(
                    """
                    INSERT INTO users (id, username, email, display_name, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        normalized_username,
                        normalized_email,
                        name,
                        hash_password(password),
                        now,
                    ),
                )
                await connection.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateUserError("用户名或邮箱已被注册") from exc
        return AuthUser(
            id=user_id,
            username=normalized_username,
            email=normalized_email,
            display_name=name,
            created_at=datetime.fromisoformat(now),
        )

    async def authenticate(self, login: str, password: str) -> AuthUser | None:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            cursor = await connection.execute(
                """
                SELECT id, username, email, display_name, password_hash, created_at
                FROM users WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
                """,
                (login.strip(), login.strip()),
            )
            row = await cursor.fetchone()
        if row is None or not verify_password(password, row[4]):
            return None
        return self._to_user(row)

    async def create_session(self, user_id: str) -> str:
        token = new_session_token()
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=self._session_ttl_hours)
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            await connection.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?", (now.isoformat(),)
            )
            await connection.execute(
                """
                INSERT INTO auth_sessions (token_hash, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_digest(token), user_id, expires_at.isoformat(), now.isoformat()),
            )
            await connection.commit()
        return token

    async def user_for_session(self, token: str) -> AuthUser | None:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            cursor = await connection.execute(
                """
                SELECT u.id, u.username, u.email, u.display_name, u.password_hash, u.created_at
                FROM auth_sessions AS s
                JOIN users AS u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ?
                """,
                (token_digest(token), now),
            )
            row = await cursor.fetchone()
        return self._to_user(row) if row else None

    async def delete_session(self, token: str) -> None:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            await connection.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?", (token_digest(token),)
            )
            await connection.commit()

    async def update_display_name(self, user_id: str, display_name: str) -> AuthUser:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            await connection.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (display_name.strip(), user_id),
            )
            await connection.commit()
            cursor = await connection.execute(
                """
                SELECT id, username, email, display_name, password_hash, created_at
                FROM users WHERE id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise ValueError("用户不存在")
        return self._to_user(row)

    async def bind_thread(self, thread_id: str, user_id: str) -> None:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute(
                """
                INSERT OR IGNORE INTO analysis_threads (thread_id, user_id, created_at)
                VALUES (?, ?, ?)
                """,
                (thread_id, user_id, datetime.now(UTC).isoformat()),
            )
            await connection.commit()

    async def owns_thread(self, thread_id: str, user_id: str) -> bool:
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute("PRAGMA busy_timeout=5000")
            cursor = await connection.execute(
                "SELECT 1 FROM analysis_threads WHERE thread_id = ? AND user_id = ?",
                (thread_id, user_id),
            )
            return await cursor.fetchone() is not None

    @staticmethod
    def _to_user(row) -> AuthUser:
        return AuthUser(
            id=row[0],
            username=row[1],
            email=row[2],
            display_name=row[3],
            created_at=datetime.fromisoformat(row[5]),
        )
