import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.models.sqlalchemy import Base

DATABASE_URL = os.environ.get("DATABASE_URL")

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create session factory
async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Dependency to get DB session
async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session

# Create tables (for development)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)