from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import SessionLocal
from ..utils.er_to_sql import to_sql
from ..utils.graph_to_spring import generate_spring_boot_zip

router = APIRouter(prefix="/diagrams", tags=["diagrams"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=list[schemas.DiagramRead])
def list_diagrams(project_id: int | None = None, db: Session = Depends(get_db)):
    return crud.list_diagrams(db, project_id)


@router.post("/", response_model=schemas.DiagramRead, status_code=status.HTTP_201_CREATED)
def create_diagram(payload: schemas.DiagramCreate, db: Session = Depends(get_db)):
    return crud.create_diagram(db, payload)


@router.get("/{diagram_id}", response_model=schemas.DiagramRead)
def read_diagram(diagram_id: int, db: Session = Depends(get_db)):
    diagram = crud.get_diagram(db, diagram_id)
    if not diagram:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diagram not found")
    return diagram


@router.put("/{diagram_id}", response_model=schemas.DiagramRead)
def update_diagram(diagram_id: int, payload: schemas.DiagramUpdate, db: Session = Depends(get_db)):
    diagram = crud.update_diagram(db, diagram_id, payload)
    if not diagram:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diagram not found")
    return diagram


@router.delete("/{diagram_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_diagram(diagram_id: int, db: Session = Depends(get_db)):
    removed = crud.delete_diagram(db, diagram_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diagram not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/to-sql")
def export_sql(payload: schemas.DiagramBase):
    return {"sql": to_sql(payload.graph)}


@router.post("/export/spring")
def export_spring_boot(payload: schemas.DiagramBase):
    graph = payload.graph if isinstance(payload.graph, dict) else None
    if not graph:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El grafo enviado es invalido")
    try:
        filename, buffer = generate_spring_boot_zip(payload.name, graph)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    headers = {"Content-Disposition": f"attachment; filename=\"{filename}\""}
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)
