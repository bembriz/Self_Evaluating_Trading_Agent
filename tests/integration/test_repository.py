from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.repositories import SqlAlchemySystemStateRepository


async def test_repository_set_get_y_upsert(session: AsyncSession) -> None:
    repo = SqlAlchemySystemStateRepository(session)
    await repo.set("k", {"a": 1})
    assert await repo.get("k") == {"a": 1}
    await repo.set("k", {"a": 2})
    assert await repo.get("k") == {"a": 2}
    assert await repo.get("no_existe") is None


async def test_repository_ping(session: AsyncSession) -> None:
    repo = SqlAlchemySystemStateRepository(session)
    assert await repo.ping() is True
