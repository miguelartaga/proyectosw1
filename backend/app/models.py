import json

from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, TIMESTAMP, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class JSONText(Text):
    cache_ok = True

    def bind_processor(self, dialect):
        text_processor = super().bind_processor(dialect)

        def process(value):
            if value is None:
                return None
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=True)
            return text_processor(value) if text_processor else value

        return process

    def result_processor(self, dialect, coltype):
        text_processor = super().result_processor(dialect, coltype)

        def process(value):
            if text_processor:
                value = text_processor(value)
            if value is None:
                return None
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                return value

        return process


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    prompt_history = relationship(
        "PromptHistory",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tokens = relationship(
        "UserToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserToken(Base):
    __tablename__ = "user_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    user = relationship("User", back_populates="tokens")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)

    diagrams = relationship(
        "Diagram",
        back_populates="project",
        cascade="all, delete"
    )


class Diagram(Base):
    __tablename__ = "diagrams"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(120), nullable=False)
    graph = Column(JSONText, nullable=False)  # nodos/edges React Flow

    project = relationship("Project", back_populates="diagrams")


class PromptHistory(Base):
    __tablename__ = "prompt_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    graph = Column(JSONText, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    user = relationship("User", back_populates="prompt_history")

