from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os


DEFAULT_DB_TYPE = os.getenv("DB_TYPE", "postgresql").lower()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123")
DB_NAME = os.getenv("DB_NAME", "uml_editor")


def _build_database_url() -> str:
    if db_url := os.getenv("DATABASE_URL"):
        return db_url

    driver = "postgresql+psycopg2"
    port = DB_PORT or "5432"
    if DEFAULT_DB_TYPE == "mysql":
        driver = "mysql+pymysql"
        port = DB_PORT or "3306"

    return f"{driver}://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{port}/{DB_NAME}"


DATABASE_URL = _build_database_url()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
