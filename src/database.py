import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)

logger = logging.getLogger("career_pilot.database")

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "mysql+aiomysql://root:password@127.0.0.1:3306/career_pilot"
)

logger.info("Initializing SQLAlchemy Async Engine pool...")
async_engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
)

async_session_pool = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session: AsyncSession = async_session_pool()
    try:
        yield session
        await session.commit()
    except Exception as exc:
        logger.error(f"Database session encountered an error, rolling back: {exc}", exc_info=True)
        await session.rollback()
        raise
    finally:
        await session.close()

async def init_db() -> None:
    logger.info("Verifying and building MySQL database tables...")
    try:
        from src.models import Base
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schemas initialized successfully.")
    except Exception as exc:
        logger.critical(f"Failed to bootstrap MySQL database schemas: {exc}", exc_info=True)
        raise
