import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.settings import settings

logger = logging.getLogger(__name__)

# Get database URL with safe fallback
_db_url = settings.database_url or "sqlite:///./adina.db"

# Render provides postgres:// but SQLAlchemy 2.x requires postgresql://
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    logger.info("Rewrote postgres:// to postgresql:// for SQLAlchemy compatibility")

_connect_args = {}
if _db_url.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
    logger.info("Using SQLite database")
else:
    # Require SSL for PostgreSQL unless the URL already specifies sslmode
    if "sslmode" not in _db_url:
        _connect_args["sslmode"] = "require"
        logger.info("Enabled SSL (sslmode=require) for PostgreSQL connection")
    logger.info("Using PostgreSQL database")

# Create engine with connection pooling settings suitable for production
try:
    engine = create_engine(
        _db_url,
        connect_args=_connect_args,
        pool_pre_ping=True,  # Verify connections before using them
        pool_recycle=300,    # Recycle connections after 5 minutes
    )
    logger.info("Database engine created successfully")
except Exception as e:
    logger.error("Failed to create database engine: %s", e)
    # Fallback to SQLite if PostgreSQL fails
    logger.warning("Falling back to SQLite database")
    engine = create_engine(
        "sqlite:///./adina.db",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
