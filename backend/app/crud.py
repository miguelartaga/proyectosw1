from typing import List, Optional

from sqlalchemy.orm import Session

from . import models, schemas
from .utils import security


def create_diagram(db: Session, data: schemas.DiagramCreate) -> models.Diagram:
    diagram = models.Diagram(
        project_id=data.project_id,
        name=data.name,
        graph=data.graph,
    )
    db.add(diagram)
    db.commit()
    db.refresh(diagram)
    return diagram


def get_diagram(db: Session, diagram_id: int) -> Optional[models.Diagram]:
    return db.query(models.Diagram).filter(models.Diagram.id == diagram_id).first()


def list_diagrams(db: Session, project_id: Optional[int] = None) -> List[models.Diagram]:
    query = db.query(models.Diagram)
    if project_id is not None:
        query = query.filter(models.Diagram.project_id == project_id)
    return query.order_by(models.Diagram.id.desc()).all()


def update_diagram(db: Session, diagram_id: int, data: schemas.DiagramUpdate) -> Optional[models.Diagram]:
    diagram = get_diagram(db, diagram_id)
    if not diagram:
        return None

    if data.name is not None:
        diagram.name = data.name
    if data.graph is not None:
        diagram.graph = data.graph

    db.commit()
    db.refresh(diagram)
    return diagram


def delete_diagram(db: Session, diagram_id: int) -> bool:
    diagram = get_diagram(db, diagram_id)
    if not diagram:
        return False

    db.delete(diagram)
    db.commit()
    return True


def create_prompt_history(db: Session, user_id: int, data: schemas.PromptHistoryCreate) -> models.PromptHistory:
    entry = models.PromptHistory(
        user_id=user_id,
        prompt=data.prompt,
        graph=data.graph,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_prompt_history(
    db: Session,
    user_id: int,
    history_id: int,
    data: schemas.PromptHistoryCreate,
) -> models.PromptHistory | None:
    entry = (
        db.query(models.PromptHistory)
        .filter(
            models.PromptHistory.id == history_id,
            models.PromptHistory.user_id == user_id,
        )
        .first()
    )
    if not entry:
        return None

    entry.prompt = data.prompt
    entry.graph = data.graph
    db.commit()
    db.refresh(entry)
    return entry


def list_prompt_history(db: Session, user_id: int, limit: int = 30) -> List[models.PromptHistory]:
    query = (
        db.query(models.PromptHistory)
        .filter(models.PromptHistory.user_id == user_id)
        .order_by(models.PromptHistory.created_at.desc())
    )
    if limit:
        query = query.limit(limit)
    return query.all()


def delete_prompt_history(db: Session, user_id: int, history_id: int) -> bool:
    entry = (
        db.query(models.PromptHistory)
        .filter(
            models.PromptHistory.id == history_id,
            models.PromptHistory.user_id == user_id,
        )
        .first()
    )
    if not entry:
        return False

    db.delete(entry)
    db.commit()
    return True


def clear_prompt_history(db: Session, user_id: int) -> int:
    deleted = (
        db.query(models.PromptHistory)
        .filter(models.PromptHistory.user_id == user_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def create_user_token(db: Session, user_id: int, token: str) -> models.UserToken:
    record = models.UserToken(user_id=user_id, token=token)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def delete_user_tokens(db: Session, user_id: int) -> None:
    db.query(models.UserToken).filter(models.UserToken.user_id == user_id).delete(synchronize_session=False)
    db.commit()


def get_user_by_token(db: Session, token: str) -> Optional[models.User]:
    token_row = db.query(models.UserToken).filter(models.UserToken.token == token).first()
    return token_row.user if token_row else None


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()


def create_user(db: Session, data: schemas.UserCreate) -> models.User:
    hashed = security.create_password_hash(data.password)
    user = models.User(email=data.email.lower(), hashed_password=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    user = get_user_by_email(db, email.lower())
    if not user:
        return None
    if not security.verify_password(password, user.hashed_password):
        return None
    return user


