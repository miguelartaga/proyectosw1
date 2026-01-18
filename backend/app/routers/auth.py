import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import SessionLocal


router = APIRouter(prefix="/auth", tags=["auth"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def issue_token(db: Session, user: models.User) -> str:
    crud.delete_user_tokens(db, user.id)
    token = secrets.token_urlsafe(32)
    crud.create_user_token(db, user.id, token)
    return token


@router.post("/register", response_model=schemas.AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, payload.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="El correo ya esta registrado")

    user = crud.create_user(db, payload)
    token = issue_token(db, user)
    return schemas.AuthResponse(token=token, user=schemas.UserRead.model_validate(user))


@router.post("/login", response_model=schemas.AuthResponse)
async def login(
    request: Request,
    db: Session = Depends(get_db),
):
    email: str | None = None
    password: str | None = None

    # Intentar JSON primero (email/password)
    try:
        body = await request.json()
        if isinstance(body, dict):
            email = body.get("email")
            password = body.get("password")
    except Exception:
        pass

    # Si no vino JSON válido, intentar formulario (username/password o email/password)
    if not email or not password:
        form = await request.form()
        email = form.get("username") or form.get("email")
        password = form.get("password")

    if not email or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Faltan credenciales")

    user = crud.authenticate_user(db, email, password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")

    token = issue_token(db, user)
    return schemas.AuthResponse(token=token, user=schemas.UserRead.model_validate(user))
