from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


readonly_engine = create_async_engine(
    settings.readonly_database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

ReadonlySessionLocal = async_sessionmaker(
    readonly_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


async def get_readonly_session():
    async with ReadonlySessionLocal() as session:
        yield session
