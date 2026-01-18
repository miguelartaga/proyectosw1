import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from . import crud, models, schemas
from .database import Base, SessionLocal, engine
from .routers import ai, auth, diagrams

load_dotenv()

DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@gmail.com")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "123")


def ensure_user_tokens_table() -> None:
    inspector = inspect(engine)
    if "user_tokens" in inspector.get_table_names():
        return

    try:
        models.UserToken.__table__.create(bind=engine)
    except SQLAlchemyError as exc:
        print(f"Failed to create user_tokens table: {exc}")


def ensure_prompt_history_user_column() -> None:
    inspector = inspect(engine)
    if "prompt_history" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("prompt_history")}
    if "user_id" in columns:
        return

    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE prompt_history ADD COLUMN user_id INT NULL"))

            default_user_id = connection.execute(
                text("SELECT id FROM users ORDER BY id LIMIT 1")
            ).scalar()

            if default_user_id is not None:
                connection.execute(
                    text("UPDATE prompt_history SET user_id = :uid WHERE user_id IS NULL"),
                    {"uid": default_user_id},
                )

            connection.execute(text("ALTER TABLE prompt_history MODIFY COLUMN user_id INT NOT NULL"))

            indexes = {index["name"] for index in inspector.get_indexes("prompt_history")}
            if "ix_prompt_history_user_id" not in indexes:
                connection.execute(
                    text("ALTER TABLE prompt_history ADD INDEX ix_prompt_history_user_id (user_id)")
                )

            fk_names = {
                fk["name"] for fk in inspector.get_foreign_keys("prompt_history") if fk.get("name")
            }
            if "fk_prompt_history_user_id" not in fk_names:
                connection.execute(
                    text(
                        "ALTER TABLE prompt_history "
                        "ADD CONSTRAINT fk_prompt_history_user_id "
                        "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
                    )
                )
    except SQLAlchemyError as exc:
        print(f"Failed to ensure prompt_history.user_id column: {exc}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if not crud.get_user_by_email(db, DEFAULT_ADMIN_EMAIL):
            crud.create_user(
                db,
                schemas.UserCreate(
                    email=DEFAULT_ADMIN_EMAIL,
                    password=DEFAULT_ADMIN_PASSWORD,
                ),
            )

    ensure_user_tokens_table()
    ensure_prompt_history_user_column()

    yield


app = FastAPI(title="UML/ER Editor API", lifespan=lifespan)

raw_origins = os.getenv("CORS_ORIGINS")
base_origins = {"http://localhost:5173", "http://localhost:8081"}

configured_origins: set[str] = set(base_origins)
if raw_origins:
    configured_origins.update(
        origin.strip() for origin in raw_origins.split(",") if origin.strip()
    )

expanded_origins: set[str] = set()
for origin in configured_origins:
    expanded_origins.add(origin)
    if "://localhost" in origin:
        expanded_origins.add(origin.replace("://localhost", "://127.0.0.1"))
    if "://127.0.0.1" in origin:
        expanded_origins.add(origin.replace("://127.0.0.1", "://localhost"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(expanded_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(diagrams.router)
api_router.include_router(ai.router)

app.include_router(api_router)
app.include_router(auth.router)
app.include_router(diagrams.router)
app.include_router(ai.router)


@app.get("/")
async def healthcheck() -> dict[str, bool]:
    return {"ok": True}



