from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_schema_migrado(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
        assert "system_state" in tables
        assert "alembic_version" in tables
        extensions = (await conn.execute(text("SELECT extname FROM pg_extension"))).scalars().all()
        assert "vector" in extensions
