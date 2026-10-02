from __future__ import annotations

import pytest

from app.memory.user_profile import SQLiteUserProfileRepository
from app.schemas.domain import UserProfile


@pytest.mark.asyncio
async def test_user_profile_round_trip(tmp_path):
    repository = SQLiteUserProfileRepository(tmp_path / "app.db")
    await repository.setup()
    profile = UserProfile(skills=["Java", "Redis"], preferred_locations=["上海"])
    await repository.upsert("user-1", profile)

    restored = await repository.get("user-1")
    assert restored == profile
