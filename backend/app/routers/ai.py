import anyio
import base64
import json
import logging
import math
import os
import re
import unicodedata
from copy import deepcopy
from functools import lru_cache
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from openai import OpenAI, OpenAIError

from .. import crud, models, schemas
from ..database import SessionLocal

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)
VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")
MAX_IMAGE_SIZE_BYTES = 8 * 1024 * 1024  # 8 MB safety limit

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_current_user(authorization: str | None, db: Session) -> models.User:
    """
    Para despliegues sin login: si hay token lo valida; si no, devuelve el primer usuario
    o crea uno por defecto para permitir operar sin autenticacion previa.
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            user = crud.get_user_by_token(db, token)
            if user:
                return user

    existing = db.query(models.User).order_by(models.User.id).first()
    if existing:
        return existing

    # Crear usuario por defecto si no existe ninguno.
    default_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@gmail.com")
    default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "123")
    return crud.create_user(
        db,
        schemas.UserCreate(email=default_email, password=default_password),
    )

class GraphNode(BaseModel):
    id: str
    type: str | None = None
    position: Dict[str, Any]
    data: Dict[str, Any]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None
    data: Dict[str, Any] | None = None


class GraphPayload(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)


class PromptRequest(BaseModel):
    prompt: str
    graph: GraphPayload | None = None
    history_id: int | None = None

def build_node(
    node_id: str,
    label: str,
    columns: List[Dict[str, Any]],
    *,
    x: int,
    y: int,
    is_join: bool = False,
    join_of: Tuple[str, str] | None = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {"label": label, "columns": columns}
    if is_join:
        data["isJoin"] = True
        if join_of:
            data["joinOf"] = list(join_of)
    return {
        "id": node_id,
        "type": "databaseNode",
        "position": {"x": x, "y": y},
        "data": data,
    }


def build_edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    source_mult: str,
    target_mult: str,
    kind: str = "simple",
    label: str = "",
) -> Dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "label": label,
        "data": {
            "id": edge_id,
            "source": source,
            "target": target,
            "kind": kind,
            "sourceMult": source_mult,
            "targetMult": target_mult,
            "label": label,
        },
    }




MAX_DYNAMIC_ENTITIES = 8

STOPWORDS = {
    "ademas",
    "aplicacion",
    "aplicaciones",
    "app",
    "asi",
    "base",
    "bases",
    "cada",
    "como",
    "con",
    "crea",
    "crear",
    "creo",
    "datos",
    "debe",
    "deben",
    "del",
    "detalle",
    "detalles",
    "diagrama",
    "diagramas",
    "disena",
    "disenar",
    "diseno",
    "donde",
    "estructura",
    "favor",
    "genera",
    "generar",
    "gestion",
    "gestiona",
    "gestionar",
    "haz",
    "hacer",
    "hace",
    "incluya",
    "incluyan",
    "incluye",
    "incluyen",
    "informacion",
    "las",
    "los",
    "maneja",
    "manejar",
    "maneje",
    "modelo",
    "modelos",
    "necesaria",
    "necesario",
    "necesita",
    "necesito",
    "para",
    "pertenece",
    "pertenecen",
    "pertenecer",
    "plataforma",
    "por",
    "principal",
    "principales",
    "que",
    "quiere",
    "quiero",
    "relacion",
    "relaciones",
    "requiere",
    "requiero",
    "sistema",
    "sistemas",
    "solucion",
    "solucionar",
    "tabla",
    "tablas",
    "tambien",
    "tener",
    "tiene",
    "tipo",
    "tipos",
    "trabajan",
    "trabajar",
    "una",
    "unas",
    "uno",
    "unos",
    "usar",
    "utilizar",
}

CATEGORY_KEYWORDS = {
    "person": {
        "administrador",
        "alumno",
        "cliente",
        "doctor",
        "docente",
        "empleado",
        "estudiante",
        "jefe",
        "medico",
        "paciente",
        "personal",
        "profesor",
        "tecnico",
        "usuario",
    },
    "event": {
        "cita",
        "clase",
        "consulta",
        "entrega",
        "ingreso",
        "inscripcion",
        "matricula",
        "pago",
        "pedido",
        "reserva",
        "turno",
        "venta",
    },
    "location": {
        "aula",
        "campus",
        "departamento",
        "habitacion",
        "laboratorio",
        "oficina",
        "planta",
        "sala",
        "sede",
    },
    "item": {
        "activo",
        "curso",
        "equipo",
        "herramienta",
        "inventario",
        "libro",
        "material",
        "medicamento",
        "producto",
        "recurso",
        "servicio",
    },
    "document": {
        "expediente",
        "factura",
        "historial",
        "reporte",
        "solicitud",
    },
    "organization": {
        "clinica",
        "empresa",
        "escuela",
        "facultad",
        "hospital",
        "instituto",
        "tienda",
        "universidad",
    },
}

CATEGORY_COLUMNS = {
    "person": [
        ("nombre", "VARCHAR(150)", False),
        ("apellido", "VARCHAR(150)", True),
        ("email", "VARCHAR(150)", True),
        ("telefono", "VARCHAR(50)", True),
    ],
    "event": [
        ("fecha", "DATETIME", False),
        ("estado", "VARCHAR(50)", True),
        ("descripcion", "TEXT", True),
    ],
    "location": [
        ("nombre", "VARCHAR(120)", False),
        ("ubicacion", "VARCHAR(150)", True),
        ("capacidad", "INT", True),
    ],
    "item": [
        ("nombre", "VARCHAR(150)", False),
        ("descripcion", "TEXT", True),
        ("cantidad", "INT", True),
        ("precio", "DECIMAL(10,2)", True),
    ],
    "document": [
        ("titulo", "VARCHAR(180)", False),
        ("descripcion", "TEXT", True),
        ("fecha", "DATE", True),
    ],
    "organization": [
        ("nombre", "VARCHAR(180)", False),
        ("direccion", "VARCHAR(200)", True),
        ("telefono", "VARCHAR(60)", True),
    ],
    "default": [
        ("nombre", "VARCHAR(150)", False),
        ("descripcion", "TEXT", True),
    ],
}

TYPE_KEYWORDS = {
    "entero",
    "integer",
    "int",
    "texto",
    "text",
    "string",
    "varchar",
    "char",
    "decimal",
    "numeric",
    "numero",
    "number",
    "float",
    "double",
    "fecha",
    "date",
    "datetime",
    "hora",
    "time",
    "boolean",
    "bool",
    "pk",
    "fk",
    "primary",
    "foreign",
}

def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_text(text: str) -> str:
    ascii_text = strip_accents(text)
    ascii_text = ascii_text.lower()
    return re.sub(r"[^a-z0-9\s]", " ", ascii_text)


def normalize_text_keep_commas(text: str) -> str:
    ascii_text = strip_accents(text)
    ascii_text = ascii_text.lower()
    return re.sub(r"[^a-z0-9\s,]", " ", ascii_text)


def normalize_text_keep_relation_symbols(text: str) -> str:
    ascii_text = strip_accents(text)
    ascii_text = ascii_text.lower()
    return re.sub(r"[^a-z0-9\s,.*:>\-]", " ", ascii_text)


def normalize_token(token: str) -> str:
    ascii_value = strip_accents(token)
    ascii_value = ascii_value.lower()
    return re.sub(r"[^a-z0-9]+", "", ascii_value)


def slugify(value: str) -> str:
    normalized = normalize_token(value)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug


def titleize(value: str) -> str:
    words = re.split(r"[\s_-]+", value.strip())
    return " ".join(word.capitalize() for word in words if word)


def to_snake_case(value: str) -> str:
    ascii_value = strip_accents(value).lower()
    ascii_value = re.sub(r"[^a-z0-9]+", "_", ascii_value)
    ascii_value = re.sub(r"_+", "_", ascii_value).strip("_")
    return ascii_value or "campo"


def singularize_word(word: str) -> str:
    if word.endswith("ces"):
        return word[:-3] + "z"
    if word.endswith("iones"):
        return word[:-5] + "ion"
    if word.endswith("es") and not word.endswith("ses"):
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def pluralize_word(word: str) -> str:
    if word.endswith("z"):
        return word[:-1] + "ces"
    if word.endswith("ion"):
        return word + "es"
    if word.endswith("s"):
        return word
    return word + "s"


def categorize_entity(token: str) -> str:
    base = singularize_word(token)
    for category, keywords in CATEGORY_KEYWORDS.items():
        if base in keywords:
            return category
    if base.endswith(("cion", "sion", "miento")):
        return "event"
    if base.endswith(("ista", "nte", "dor", "dora", "ero", "era")):
        return "person"
    if base.endswith(("orio", "oria")):
        return "location"
    return "default"


def build_base_columns(slug: str, category: str) -> List[Dict[str, Any]]:
    columns: List[Dict[str, Any]] = [
        {"id": f"{slug}-id", "name": "id", "type": "INT", "pk": True, "nullable": False}
    ]
    presets = CATEGORY_COLUMNS.get(category, CATEGORY_COLUMNS["default"])
    for name, column_type, nullable in presets:
        column_id = f"{slug}-{name.replace('_', '-')}"
        column: Dict[str, Any] = {
            "id": column_id,
            "name": name,
            "type": column_type,
            "nullable": nullable,
        }
        columns.append(column)
    return columns


ADD_COLUMN_VERBS = (
    "agrega|agregue|agregar|a\u00f1ade|a\u00f1adir|anade|aumenta|aumentar|incluye|incluir|"
    "actualiza|actualizar|modifica|modificar|suma|sumar"
)
ADD_TABLE_VERBS = (
    "agrega|agregue|agregar|a\u00f1ade|a\u00f1adir|anade|crea|crear|inserta|insertar|"
    "incluye|incluir|define|definir"
)
COLUMN_TOKEN_PATTERN = r"(?:[a-z0-9]+(?:\s+|,\s*)){0,5}[a-z0-9]+"
TABLE_TOKEN_PATTERN = r"(?:[a-z0-9]+\s+){0,3}[a-z0-9]+"
ADD_TABLE_PATTERN = re.compile(
    rf"(?:{ADD_TABLE_VERBS})\s+(?:(?:una?|la|el|los|las)\s+)?tabla\s+(?:llamada\s+|denominada\s+)?(?P<table>[a-z0-9_\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\s-]+?)"
    rf"(?:\s+(?:con|que\s+tiene)\s+(?:los\s+)?(?:atributos|campos|columnas)\s+(?P<columns>[^.;\n]+))?"
    rf"(?=(?:\s+y\s+(?:crea|crear|agrega|a\u00f1ade|anade)|[.;,\n]|$))",
    re.IGNORECASE,
)
COLUMN_BEFORE_TABLE_PATTERN = re.compile(
    rf"(?:{ADD_COLUMN_VERBS})\s+(?:el|la|los|las|un|una|unos|unas)?\s*"
    rf"(?:nuevo|nueva|nuevos|nuevas)?\s*(?:atributo|atributos|columna|columnas|campo|campos)\s+"
    rf"(?P<column>{COLUMN_TOKEN_PATTERN})\s+(?:a|en|para|al)\s+"
    rf"(?:la|el)?\s*tabla\s+(?P<table>{TABLE_TOKEN_PATTERN})"
)
ATTRIBUTE_STOP_PATTERN = re.compile(
    r"\b(?:y\s+(?:crea|crear|agrega|a\u00f1ade|anade|define|establece|configura)|ademas|tambien)\b",
    re.IGNORECASE,
)
TABLE_BEFORE_COLUMN_PATTERN = re.compile(
    rf"(?:{ADD_COLUMN_VERBS})\s+(?:a|en|para|al)\s+(?:la|el)?\s*tabla\s+"
    rf"(?P<table>{TABLE_TOKEN_PATTERN})\s+(?:con\s+)?"
    rf"(?:el|la|los|las|un|una|unos|unas)?\s*(?:nuevo|nueva|nuevos|nuevas)?\s*"
    rf"(?:atributo|atributos|columna|columnas|campo|campos)\s+(?P<column>{COLUMN_TOKEN_PATTERN})"
)
RELATION_KIND_PATTERN = (
    r"(?:asociacion|agregacion|composicion|segmentada|discontinua|flecha\s+blanca|flecha\s+negra)"
)
MULTIPLICITY_ANCHOR_PATTERN = re.compile(r"(?:multiplicidad|multiplidad)")
MULTIPLICITY_TOKEN_PATTERN = (
    r"(?:0\.\.1|0\.\.(?:\*|n|m)|1\.\.(?:\*|n|m)|1|0|\*|uno|una|cero|muchos|muchas|varios|varias|n|m)"
)
MULTIPLICITY_PAIR_PATTERN = re.compile(
    rf"(?P<left>{MULTIPLICITY_TOKEN_PATTERN})\s*(?:a|->|:)\s*(?P<right>{MULTIPLICITY_TOKEN_PATTERN})"
)
MULTIPLICITY_TABLE_PATTERN = re.compile(
    rf"(?:multiplicidad|multiplidad)\s+(?:entre|de)\s+"
    rf"(?:la|el)?\s*(?:tabla\s+)?(?P<left>{TABLE_TOKEN_PATTERN})\s+"
    rf"(?:con|y|entre)\s+(?:la|el)?\s*(?:tabla\s+)?(?P<right>{TABLE_TOKEN_PATTERN})"
    rf"(?=(?:\s+(?:con|de)?\s*{MULTIPLICITY_TOKEN_PATTERN}\s*(?:a|->|:))|[.;,\n]|$)",
    re.IGNORECASE,
)
RELATION_TABLE_PATTERN = re.compile(
    rf"(?:relacion(?:es)?\s*(?:de)?\s*)?"
    rf"(?:{RELATION_KIND_PATTERN}\s*)?"
    rf"(?:entre\s+)?"
    rf"(?:la|el)?\s*(?:tabla\s+)?(?P<left>{TABLE_TOKEN_PATTERN})\s+"
    rf"(?:con|y|entre)\s+(?:la|el)?\s*(?:tabla\s+)?(?P<right>{TABLE_TOKEN_PATTERN})"
    rf"(?=(?:\s+(?:con|de)?\s*(?:multiplicidad|multiplidad))"
    rf"|(?:\s+(?:con|de)?\s*{MULTIPLICITY_TOKEN_PATTERN}\s*(?:a|->|:))"
    rf"|[.;,\n]|$)",
    re.IGNORECASE,
)
RELATION_TAIL_STOPWORDS = {
    "relacion",
    "relaciones",
    "asociacion",
    "asociaciones",
    "multiplicidad",
    "multiplidad",
}


def split_column_phrase(column_raw: str) -> List[str]:
    parts = re.split(r"\s*,\s*|\b(?:y|e)\b", column_raw)
    columns: List[str] = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^(?:el|la|los|las|un|una|unos|unas)\s+", "", cleaned)
        cleaned = re.sub(r"^(?:nuevo|nueva|nuevos|nuevas)\s+", "", cleaned)
        cleaned = re.sub(r"^(?:atributo|atributos|columna|columnas|campo|campos)\s+", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            columns.append(cleaned)
    return columns


def clean_attribute_name(raw: str) -> str | None:
    cleaned = raw.strip(" .;,")
    if not cleaned:
        return None
    cleaned = re.sub(r"^(?:el|la|los|las|un|una|unos|unas)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:nuevo|nueva|nuevos|nuevas)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:campo|campos|atributo|atributos|columna|columnas)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    tokens = cleaned.split()
    while tokens and normalize_token(tokens[-1]) in TYPE_KEYWORDS:
        tokens.pop()
    cleaned = " ".join(tokens).strip()
    if not cleaned:
        return None
    return cleaned


def extract_add_table_actions(prompt: str) -> List[Tuple[str, List[str]]]:
    if not prompt:
        return []
    table_map: Dict[str, List[str]] = {}
    for match in ADD_TABLE_PATTERN.finditer(prompt):
        table_raw = (match.group("table") or "").strip()
        table_raw = re.sub(r"^(?:llamada|denominada)\s+", "", table_raw, flags=re.IGNORECASE)
        table_clean = clean_table_phrase(table_raw)
        if not table_clean:
            continue
        table_key = normalize_token(table_clean)
        if not table_key:
            continue
        columns_raw = match.group("columns")
        attributes: List[str] = []
        if columns_raw:
            truncated = ATTRIBUTE_STOP_PATTERN.split(columns_raw, 1)[0]
            for candidate in split_column_phrase(truncated):
                column_clean = clean_attribute_name(candidate)
                if column_clean:
                    attributes.append(column_clean)
        entry = table_map.setdefault(table_clean, [])
        for attribute in attributes:
            if attribute not in entry:
                entry.append(attribute)
    return [(name, attrs) for name, attrs in table_map.items()]

def clean_table_phrase(table_raw: str) -> str:
    tokens = table_raw.strip().split()
    if not tokens:
        return ""
    filler = {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "con"}
    while tokens and tokens[0] in filler:
        tokens.pop(0)
    while tokens and tokens[-1] in filler:
        tokens.pop()
    return " ".join(tokens)


def extract_add_column_actions(prompt: str) -> List[Tuple[str, str]]:
    normalized = re.sub(r"\s+", " ", normalize_text_keep_commas(prompt)).strip()
    if not normalized:
        return []

    actions: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for pattern in (COLUMN_BEFORE_TABLE_PATTERN, TABLE_BEFORE_COLUMN_PATTERN):
        for match in pattern.finditer(normalized):
            table_raw = match.group("table").strip()
            table_clean = clean_table_phrase(table_raw)
            if not table_clean:
                continue
            column_raw = match.group("column").strip()
            if not table_raw or not column_raw:
                continue
            for column_name in split_column_phrase(column_raw):
                key = (table_clean, column_name.strip())
                if key in seen:
                    continue
                seen.add(key)
                actions.append(key)
    return actions


def clean_relation_table_name(table_raw: str) -> str:
    tokens = clean_table_phrase(table_raw).split()
    if not tokens:
        return ""
    filler = {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "con"}
    while tokens and (tokens[0] in filler or tokens[0] in RELATION_TAIL_STOPWORDS):
        tokens.pop(0)
    while tokens and (tokens[-1] in filler or tokens[-1] in RELATION_TAIL_STOPWORDS):
        tokens.pop()
    return " ".join(tokens)


def strip_multiplicity_suffix(table_name: str) -> str:
    if not table_name:
        return table_name
    tokens = table_name.split()
    while tokens:
        tail = tokens[-1]
        if tail in {"a", "->", ":"}:
            tokens.pop()
            continue
        if normalize_multiplicity_token(tail) is not None:
            tokens.pop()
            continue
        break
    return " ".join(tokens)


def normalize_multiplicity_token(token: str) -> str | None:
    value = token.strip()
    if not value:
        return None
    if value in {"uno", "una", "1", "1..1"}:
        return "1"
    if value in {"0..1"}:
        return "0..1"
    if value in {"0..*", "0..n", "0..m"}:
        return "0..*"
    if value in {"1..*", "1..n", "1..m"}:
        return "1..*"
    if value in {"*", "n", "m", "muchos", "muchas", "varios", "varias"}:
        return "*"
    return None


def parse_multiplicity_pair(prompt: str) -> tuple[str, str] | None:
    text = strip_accents(prompt).lower()
    anchor = MULTIPLICITY_ANCHOR_PATTERN.search(text)
    search_text = text[anchor.end():] if anchor else text
    match = MULTIPLICITY_PAIR_PATTERN.search(search_text)
    if not match:
        return None
    raw_left = match.group("left").strip().lower()
    raw_right = match.group("right").strip().lower()
    left = normalize_multiplicity_token(raw_left)
    right = normalize_multiplicity_token(raw_right)
    if left and right:
        return left, right
    if raw_left in {"0", "cero"}:
        if raw_right in {"1", "uno", "una"}:
            return "1", "0..1"
        if raw_right in {"*", "n", "m", "muchos", "muchas", "varios", "varias"}:
            return "1", "0..*"
    return None


def parse_relationship_kind(prompt: str) -> str | None:
    text = strip_accents(prompt).lower()
    if "segmentada" in text or "discontinua" in text:
        return "segmentada"
    if "flecha blanca" in text or "agregacion" in text:
        return "flechaBlanca"
    if "flecha negra" in text or "composicion" in text:
        return "flechaNegra"
    if "asociacion" in text:
        return "simple"
    return None


def extract_relation_actions(prompt: str) -> tuple[List[Dict[str, Any]], bool]:
    normalized = re.sub(r"\s+", " ", normalize_text_keep_relation_symbols(prompt)).strip()
    if not normalized:
        return [], False

    multiplicity_intent = bool(MULTIPLICITY_ANCHOR_PATTERN.search(strip_accents(prompt).lower()))
    multiplicities = parse_multiplicity_pair(prompt)
    source_mult = multiplicities[0] if multiplicities else None
    target_mult = multiplicities[1] if multiplicities else None
    relation_kind = parse_relationship_kind(prompt)

    actions: List[Dict[str, Any]] = []
    matched = False
    if multiplicity_intent and not relation_kind:
        for match in MULTIPLICITY_TABLE_PATTERN.finditer(normalized):
            matched = True
            left_raw = match.group("left") or ""
            right_raw = match.group("right") or ""
            left = clean_relation_table_name(left_raw)
            right = clean_relation_table_name(right_raw)
            if source_mult and target_mult:
                left = strip_multiplicity_suffix(left)
                right = strip_multiplicity_suffix(right)
            if not left or not right:
                continue
            if not (source_mult and target_mult):
                continue
            actions.append(
                {
                    "source": left,
                    "target": right,
                    "kind": relation_kind,
                    "source_mult": source_mult,
                    "target_mult": target_mult,
                    "label": None,
                }
            )
    else:
        for match in RELATION_TABLE_PATTERN.finditer(normalized):
            matched = True
            left_raw = match.group("left") or ""
            right_raw = match.group("right") or ""
            left = clean_relation_table_name(left_raw)
            right = clean_relation_table_name(right_raw)
            if multiplicity_intent and source_mult and target_mult:
                left = strip_multiplicity_suffix(left)
                right = strip_multiplicity_suffix(right)
            if not left or not right:
                continue
            if not relation_kind and not (multiplicity_intent and source_mult and target_mult):
                continue
            actions.append(
                {
                    "source": left,
                    "target": right,
                    "kind": relation_kind,
                    "source_mult": source_mult,
                    "target_mult": target_mult,
                    "label": None,
                }
            )
    return actions, matched


def build_label_lookup(nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        data = node.get("data") or {}
        label = data.get("label")
        if not isinstance(label, str):
            continue
        normalized = normalize_token(label)
        candidates = {normalized}
        if normalized:
            singular = singularize_word(normalized)
            plural = pluralize_word(singular)
            candidates.update({singular, plural})
        slug = slugify(label)
        if slug:
            candidates.add(slug.replace("-", ""))
        candidates = {candidate for candidate in candidates if candidate}
        for candidate in candidates:
            lookup.setdefault(candidate, node)
    return lookup


def find_node_by_name(lookup: Dict[str, Dict[str, Any]], table_name: str) -> Dict[str, Any] | None:
    candidates: set[str] = set()
    normalized = normalize_token(table_name)
    if normalized:
        candidates.add(normalized)
        singular = singularize_word(normalized)
        candidates.add(singular)
        candidates.add(pluralize_word(singular))
    slug = slugify(table_name)
    if slug:
        candidates.add(slug.replace("-", ""))
    for candidate in candidates:
        if candidate and candidate in lookup:
            return lookup[candidate]
    return None


def add_column_to_node(node: Dict[str, Any], column_name: str) -> str:
    data = node.setdefault("data", {})
    columns = data.setdefault("columns", [])
    if not isinstance(columns, list):
        columns = []
        data["columns"] = columns

    column_key = normalize_token(column_name)
    if not column_key:
        return "invalid"

    existing_keys = {
        normalize_token(str(column.get("name", ""))) for column in columns if isinstance(column, dict)
    }
    if column_key in existing_keys:
        return "duplicate"

    snake_name = to_snake_case(column_name)
    if not snake_name:
        return "invalid"

    existing_snake = {
        to_snake_case(str(column.get("name", ""))) for column in columns if isinstance(column, dict)
    }
    if snake_name in existing_snake:
        return "duplicate"

    base_slug = slugify(column_name) or column_key
    base_slug = base_slug.strip("-")
    if not base_slug:
        base_slug = column_key
    candidate_id = f"{node.get('id', 'node')}-{base_slug or 'col'}"
    existing_ids = {str(column.get("id")) for column in columns if isinstance(column, dict)}
    new_id = candidate_id
    suffix = 2
    while new_id in existing_ids:
        new_id = f"{candidate_id}-{suffix}"
        suffix += 1

    columns.append(
        {
            "id": new_id,
            "name": snake_name,
            "type": "VARCHAR(120)",
            "nullable": True,
            "pk": False,
        }
    )
    return "added"


def suggest_new_node_position(existing_nodes: List[Dict[str, Any]]) -> Dict[str, int]:
    spacing_x = 280
    spacing_y = 220
    index = len(existing_nodes)
    col = index % 4
    row = index // 4
    return {"x": 160 + col * spacing_x, "y": 140 + row * spacing_y}


def register_node_in_lookup(lookup: Dict[str, Dict[str, Any]], node: Dict[str, Any]) -> None:
    data = node.get("data") or {}
    label = data.get("label")
    if not isinstance(label, str):
        return
    normalized = normalize_token(label)
    candidates = {normalized}
    if normalized:
        singular = singularize_word(normalized)
        plural = pluralize_word(singular)
        candidates.update({singular, plural})
    slug = slugify(label)
    if slug:
        candidates.add(slug.replace("-", ""))
    for candidate in candidates:
        if candidate:
            lookup[candidate] = node


def create_node_with_defaults(table_name: str, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    label = titleize(table_name)
    slug = slugify(table_name) or f"tabla-{len(nodes) + 1}"
    normalized = normalize_token(table_name)
    category = categorize_entity(normalized) if normalized else "default"
    columns = build_base_columns(slug, category)

    node_id_base = f"node-{slug or 'tabla'}"
    existing_ids = {str(node.get("id")) for node in nodes}
    node_id = node_id_base
    suffix = 2
    while node_id in existing_ids:
        node_id = f"{node_id_base}-{suffix}"
        suffix += 1

    position = suggest_new_node_position(nodes)

    node = {
        "id": node_id,
        "type": "databaseNode",
        "position": position,
        "data": {
            "label": label,
            "columns": columns,
        },
    }
    nodes.append(node)
    return node


def find_edge_between(
    edges: List[Dict[str, Any]],
    source_id: str,
    target_id: str,
) -> tuple[Dict[str, Any], bool] | None:
    for edge in edges:
        if edge.get("source") == source_id and edge.get("target") == target_id:
            return edge, False
        if edge.get("source") == target_id and edge.get("target") == source_id:
            return edge, True
    return None


def ensure_unique_edge_id(source_id: str, target_id: str, used: set[str]) -> str:
    base = f"edge-{source_id}-{target_id}"
    edge_id = base
    suffix = 2
    while edge_id in used:
        edge_id = f"{base}-{suffix}"
        suffix += 1
    used.add(edge_id)
    return edge_id


def upsert_relation_edge(
    edges: List[Dict[str, Any]],
    source_id: str,
    target_id: str,
    *,
    kind: str | None,
    source_mult: str | None,
    target_mult: str | None,
    label: str | None,
    used_edge_ids: set[str],
    allow_create: bool,
) -> bool:
    existing = find_edge_between(edges, source_id, target_id)
    if existing:
        edge, _ = existing
        data = edge.get("data") or {}
        desired_kind = kind or data.get("kind") or "simple"
        desired_source_mult = source_mult or data.get("sourceMult") or "1"
        desired_target_mult = target_mult or data.get("targetMult") or "*"
        changed = False

        if edge.get("source") != source_id:
            edge["source"] = source_id
            changed = True
        if edge.get("target") != target_id:
            edge["target"] = target_id
            changed = True
        if label is not None and edge.get("label") != label:
            edge["label"] = label
            changed = True

        if data.get("id") != edge.get("id"):
            data["id"] = edge.get("id")
            changed = True
        if data.get("source") != source_id:
            data["source"] = source_id
            changed = True
        if data.get("target") != target_id:
            data["target"] = target_id
            changed = True
        if data.get("kind") != desired_kind:
            data["kind"] = desired_kind
            changed = True
        if data.get("sourceMult") != desired_source_mult:
            data["sourceMult"] = desired_source_mult
            changed = True
        if data.get("targetMult") != desired_target_mult:
            data["targetMult"] = desired_target_mult
            changed = True
        if label is not None and data.get("label") != label:
            data["label"] = label
            changed = True

        edge["data"] = data
        return changed

    if not allow_create:
        return False

    new_edge_id = ensure_unique_edge_id(source_id, target_id, used_edge_ids)
    new_edge = build_edge(
        new_edge_id,
        source_id,
        target_id,
        source_mult=source_mult or "1",
        target_mult=target_mult or "*",
        kind=kind or "simple",
        label=label or "",
    )
    edges.append(new_edge)
    return True


def apply_incremental_updates(prompt: str, graph: GraphPayload) -> Dict[str, Any] | None:
    table_actions = extract_add_table_actions(prompt)
    column_actions = extract_add_column_actions(prompt)
    relation_actions, relation_intent = extract_relation_actions(prompt)
    if not table_actions and not column_actions and not relation_actions:
        if relation_intent:
            graph_dict = graph.model_dump()
            return {
                "nodes": deepcopy(graph_dict.get("nodes", [])),
                "edges": deepcopy(graph_dict.get("edges", [])),
            }
        return None

    graph_dict = graph.model_dump()
    nodes = deepcopy(graph_dict.get("nodes", []))
    edges = deepcopy(graph_dict.get("edges", []))

    lookup = build_label_lookup(nodes)
    duplicates: List[Tuple[str, str]] = []
    relation_duplicates: List[Tuple[str, str]] = []
    missing_relations: List[Tuple[str, str]] = []
    used_edge_ids = {str(edge.get("id")) for edge in edges if edge.get("id")}
    mutated = False

    for table_raw, attributes in table_actions:
        node = find_node_by_name(lookup, table_raw)
        if not node:
            node = create_node_with_defaults(table_raw, nodes)
            register_node_in_lookup(lookup, node)
            mutated = True
        for attribute in attributes:
            column_status = add_column_to_node(node, attribute)
            if column_status == "added":
                mutated = True
            elif column_status == "duplicate":
                duplicates.append((table_raw, attribute))

    for table_raw, column_raw in column_actions:
        node = find_node_by_name(lookup, table_raw)
        if not node:
            node = create_node_with_defaults(table_raw, nodes)
            register_node_in_lookup(lookup, node)
            mutated = True
        column_status = add_column_to_node(node, column_raw)
        if column_status == "added":
            mutated = True
        elif column_status == "duplicate":
            duplicates.append((table_raw, column_raw))

    for action in relation_actions:
        source_name = action["source"]
        target_name = action["target"]
        allow_create = action.get("kind") is not None
        source_node = find_node_by_name(lookup, source_name)
        if not source_node:
            if not allow_create:
                missing_relations.append((source_name, target_name))
                continue
            source_node = create_node_with_defaults(source_name, nodes)
            register_node_in_lookup(lookup, source_node)
            mutated = True
        if not source_node:
            continue
        target_node = find_node_by_name(lookup, target_name)
        if not target_node:
            if not allow_create:
                missing_relations.append((source_name, target_name))
                continue
            target_node = create_node_with_defaults(target_name, nodes)
            register_node_in_lookup(lookup, target_node)
            mutated = True
        if not target_node:
            continue

        if not allow_create and not find_edge_between(edges, source_node["id"], target_node["id"]):
            missing_relations.append((source_name, target_name))
            continue

        edge_changed = upsert_relation_edge(
            edges,
            source_node["id"],
            target_node["id"],
            kind=action.get("kind"),
            source_mult=action.get("source_mult"),
            target_mult=action.get("target_mult"),
            label=action.get("label"),
            used_edge_ids=used_edge_ids,
            allow_create=allow_create,
        )
        if edge_changed:
            mutated = True
        else:
            relation_duplicates.append((source_name, target_name))

    if missing_relations:
        pairs = ", ".join(f"{src} y {dst}" for src, dst in missing_relations)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No hay relacion entre las tablas {pairs}. "
                "Primero crea la relacion y luego ajusta la multiplicidad."
            ),
        )

    if not mutated:
        if duplicates or relation_duplicates or relation_intent:
            return {"nodes": nodes, "edges": edges}
        return None

    return {"nodes": nodes, "edges": edges}

def extract_entity_candidates(raw_text: str, max_entities: int = MAX_DYNAMIC_ENTITIES) -> List[str]:
    entities: List[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\w+", raw_text):
        original = match.group()
        normalized = normalize_token(original)
        if not normalized or len(normalized) < 3:
            continue
        if normalized.isdigit():
            continue
        variants = {
            normalized,
            singularize_word(normalized),
            normalized.rstrip("s"),
        }
        variants = {variant for variant in variants if variant}
        if any(variant in STOPWORDS for variant in variants):
            continue
        if any(variant in seen for variant in variants):
            continue
        seen.update(variants)
        entities.append(original)
        if len(entities) >= max_entities:
            break
    return entities


def build_word_forms(token: str) -> List[str]:
    base = singularize_word(token)
    forms = {token, base, pluralize_word(base)}
    return [form for form in forms if form]


def detect_relation(norm_text: str, child_forms: List[str], parent_forms: List[str]) -> bool:
    for child_form in child_forms:
        child_pattern = re.escape(child_form)
        for parent_form in parent_forms:
            parent_pattern = re.escape(parent_form)
            direct_pattern = rf"\b{child_pattern}\b\s+(?:de|del|para|con|sobre)\s+\b{parent_pattern}\b"
            if re.search(direct_pattern, norm_text):
                return True
            reverse_pattern = rf"\b{parent_pattern}\b\s+(?:con|para|de)\s+\b{child_pattern}\b"
            if re.search(reverse_pattern, norm_text):
                return True
            between_pattern = rf"\bentre\s+{parent_pattern}\s+y\s+{child_pattern}\b"
            if re.search(between_pattern, norm_text):
                return True
    return False


def infer_relations(norm_text: str, entries: List[Dict[str, Any]]) -> List[tuple[int, int]]:
    relations: List[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for child_idx, child in enumerate(entries):
        child_forms = build_word_forms(child["normalized"])
        for parent_idx, parent in enumerate(entries):
            if parent_idx == child_idx:
                continue
            pair = (parent_idx, child_idx)
            if pair in seen:
                continue
            parent_forms = build_word_forms(parent["normalized"])
            if detect_relation(norm_text, child_forms, parent_forms):
                relations.append(pair)
                seen.add(pair)
    return relations


def generate_dynamic_diagram(raw_text: str) -> Dict[str, Any] | None:
    candidates = extract_entity_candidates(raw_text)
    if len(candidates) < 2:
        return None

    norm_text = normalize_text(raw_text)
    entries: List[Dict[str, Any]] = []
    used_slugs: set[str] = set()

    for idx, original_name in enumerate(candidates, start=1):
        normalized = normalize_token(original_name)
        if not normalized:
            continue
        slug_base = slugify(original_name) or f"entidad-{idx}"
        slug = slug_base
        suffix = 2
        while slug in used_slugs:
            slug = f"{slug_base}-{suffix}"
            suffix += 1
        used_slugs.add(slug)

        label = titleize(original_name)
        category = categorize_entity(normalized)
        singular = singularize_word(normalized)
        columns = build_base_columns(slug, category)
        entries.append(
            {
                "original": original_name,
                "normalized": normalized,
                "slug": slug,
                "label": label,
                "category": category,
                "singular": singular,
                "columns": columns,
            }
        )

    if len(entries) < 2:
        return None

    relationships = infer_relations(norm_text, entries)

    child_parent: dict[int, int] = {}
    for parent_idx, child_idx in relationships:
        if parent_idx == child_idx or child_idx == 0 or parent_idx >= len(entries) or child_idx >= len(entries):
            continue
        if child_idx not in child_parent:
            child_parent[child_idx] = parent_idx

    for idx in range(1, len(entries)):
        child_parent.setdefault(idx, 0)

    edges: List[Dict[str, Any]] = []
    used_edge_ids: set[str] = set()

    for child_idx, parent_idx in sorted(child_parent.items()):
        parent_entry = entries[parent_idx]
        child_entry = entries[child_idx]

        fk_base = parent_entry["singular"] or parent_entry["slug"]
        fk_name = f"{fk_base.replace('-', '_')}_id"
        if not any(column["name"] == fk_name for column in child_entry["columns"]):
            child_entry["columns"].append(
                {
                    "id": f"{child_entry['slug']}-{parent_entry['slug']}-id",
                    "name": fk_name,
                    "type": "INT",
                    "nullable": False,
                }
            )

        edge_id_base = f"edge-{parent_entry['slug']}-{child_entry['slug']}"
        edge_id = edge_id_base
        suffix = 2
        while edge_id in used_edge_ids:
            edge_id = f"{edge_id_base}-{suffix}"
            suffix += 1
        used_edge_ids.add(edge_id)

        edges.append(
            build_edge(
                edge_id,
                f"node-{parent_entry['slug']}",
                f"node-{child_entry['slug']}",
                source_mult="1",
                target_mult="*",
            )
        )

    nodes: List[Dict[str, Any]] = []
    cols = 3
    x_start = 160
    y_start = 140
    x_step = 260
    y_step = 220

    for idx, entry in enumerate(entries):
        x_pos = x_start + (idx % cols) * x_step
        y_pos = y_start + (idx // cols) * y_step
        nodes.append(
            build_node(
                f"node-{entry['slug']}",
                entry["label"],
                entry["columns"],
                x=x_pos,
                y=y_pos,
            )
        )

    return {"nodes": nodes, "edges": edges}


def build_relation_first_diagram(raw_text: str) -> Dict[str, Any] | None:
    relation_actions, _ = extract_relation_actions(raw_text)
    if not relation_actions:
        return None

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    lookup = build_label_lookup(nodes)
    used_edge_ids: set[str] = set()

    for action in relation_actions:
        source_name = action.get("source") or ""
        target_name = action.get("target") or ""
        if not source_name or not target_name:
            continue

        source_node = find_node_by_name(lookup, source_name)
        if not source_node:
            source_node = create_node_with_defaults(source_name, nodes)
            register_node_in_lookup(lookup, source_node)

        target_node = find_node_by_name(lookup, target_name)
        if not target_node:
            target_node = create_node_with_defaults(target_name, nodes)
            register_node_in_lookup(lookup, target_node)

        upsert_relation_edge(
            edges,
            source_node["id"],
            target_node["id"],
            kind=action.get("kind") or "simple",
            source_mult=action.get("source_mult") or "1",
            target_mult=action.get("target_mult") or "*",
            label=action.get("label"),
            used_edge_ids=used_edge_ids,
            allow_create=True,
        )

    if not edges:
        return None
    return {"nodes": nodes, "edges": edges}


def university_diagram() -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = [
        build_node(
            "node-universidad",
            "Universidad",
            [
                {"id": "uni-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "uni-nombre", "name": "nombre", "type": "VARCHAR(180)", "nullable": False},
                {"id": "uni-direccion", "name": "direccion", "type": "VARCHAR(200)", "nullable": True},
                {"id": "uni-telefono", "name": "telefono", "type": "VARCHAR(60)", "nullable": True},
            ],
            x=200,
            y=60,
        ),
        build_node(
            "node-facultades",
            "Facultades",
            [
                {"id": "fac-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "fac-nombre", "name": "nombre", "type": "VARCHAR(160)", "nullable": False},
                {"id": "fac-decano", "name": "decano", "type": "VARCHAR(150)", "nullable": True},
                {"id": "fac-universidad", "name": "universidad_id", "type": "INT", "nullable": False},
            ],
            x=500,
            y=60,
        ),
        build_node(
            "node-carreras",
            "Carreras",
            [
                {"id": "car-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "car-nombre", "name": "nombre", "type": "VARCHAR(160)", "nullable": False},
                {"id": "car-duracion", "name": "duracion", "type": "INT", "nullable": True},
                {"id": "car-facultad", "name": "facultad_id", "type": "INT", "nullable": False},
            ],
            x=800,
            y=60,
        ),
        build_node(
            "node-cursos",
            "Cursos",
            [
                {"id": "cur-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "cur-codigo", "name": "codigo", "type": "VARCHAR(40)", "nullable": False},
                {"id": "cur-nombre", "name": "nombre", "type": "VARCHAR(180)", "nullable": False},
                {"id": "cur-creditos", "name": "creditos", "type": "INT", "nullable": False},
                {"id": "cur-carrera", "name": "carrera_id", "type": "INT", "nullable": False},
            ],
            x=1100,
            y=60,
        ),
        build_node(
            "node-estudiantes",
            "Estudiantes",
            [
                {"id": "est-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "est-nombre", "name": "nombre", "type": "VARCHAR(160)", "nullable": False},
                {"id": "est-email", "name": "email", "type": "VARCHAR(160)", "nullable": False},
                {"id": "est-carrera", "name": "carrera_id", "type": "INT", "nullable": False},
            ],
            x=200,
            y=320,
        ),
        build_node(
            "node-profesores",
            "Profesores",
            [
                {"id": "pro-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "pro-nombre", "name": "nombre", "type": "VARCHAR(160)", "nullable": False},
                {"id": "pro-especialidad", "name": "especialidad", "type": "VARCHAR(160)", "nullable": True},
                {"id": "pro-facultad", "name": "facultad_id", "type": "INT", "nullable": False},
            ],
            x=500,
            y=320,
        ),
        build_node(
            "node-matriculas",
            "Matriculas",
            [
                {"id": "mat-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "mat-fecha", "name": "fecha", "type": "DATE", "nullable": False},
                {"id": "mat-estado", "name": "estado", "type": "VARCHAR(60)", "nullable": True},
                {"id": "mat-estudiante", "name": "estudiante_id", "type": "INT", "nullable": False},
                {"id": "mat-curso", "name": "curso_id", "type": "INT", "nullable": False},
            ],
            x=800,
            y=320,
            is_join=True,
            join_of=("Estudiantes", "Cursos"),
        ),
        build_node(
            "node-aulas",
            "Aulas",
            [
                {"id": "aul-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "aul-codigo", "name": "codigo", "type": "VARCHAR(40)", "nullable": False},
                {"id": "aul-capacidad", "name": "capacidad", "type": "INT", "nullable": True},
                {"id": "aul-ubicacion", "name": "ubicacion", "type": "VARCHAR(120)", "nullable": True},
                {"id": "aul-facultad", "name": "facultad_id", "type": "INT", "nullable": False},
            ],
            x=1100,
            y=320,
        ),
    ]

    edges = [
        build_edge("edge-universidad-facultades", "node-universidad", "node-facultades", source_mult="1", target_mult="*"),
        build_edge("edge-facultades-carreras", "node-facultades", "node-carreras", source_mult="1", target_mult="*"),
        build_edge("edge-carreras-cursos", "node-carreras", "node-cursos", source_mult="1", target_mult="*"),
        build_edge("edge-carreras-estudiantes", "node-carreras", "node-estudiantes", source_mult="1", target_mult="*"),
        build_edge("edge-facultades-profesores", "node-facultades", "node-profesores", source_mult="1", target_mult="*"),
        build_edge("edge-cursos-profesores", "node-profesores", "node-cursos", source_mult="1", target_mult="*"),
        build_edge("edge-matriculas-estudiantes", "node-estudiantes", "node-matriculas", source_mult="1", target_mult="*"),
        build_edge("edge-matriculas-cursos", "node-cursos", "node-matriculas", source_mult="1", target_mult="*"),
        build_edge("edge-facultades-aulas", "node-facultades", "node-aulas", source_mult="1", target_mult="*"),
    ]

    return {"nodes": nodes, "edges": edges}


def veterinary_diagram() -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = [
        build_node(
            "node-clinica",
            "Clinica",
            [
                {"id": "cli-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "cli-nombre", "name": "nombre", "type": "VARCHAR(150)", "nullable": False},
                {"id": "cli-direccion", "name": "direccion", "type": "VARCHAR(200)", "nullable": True},
                {"id": "cli-telefono", "name": "telefono", "type": "VARCHAR(60)", "nullable": True},
            ],
            x=220,
            y=80,
        ),
        build_node(
            "node-clientes",
            "Clientes",
            [
                {"id": "cli-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "cli-nombre", "name": "nombre", "type": "VARCHAR(160)", "nullable": False},
                {"id": "cli-email", "name": "email", "type": "VARCHAR(160)", "nullable": True},
                {"id": "cli-telefono", "name": "telefono", "type": "VARCHAR(60)", "nullable": True},
            ],
            x=520,
            y=80,
        ),
        build_node(
            "node-mascotas",
            "Mascotas",
            [
                {"id": "mas-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "mas-nombre", "name": "nombre", "type": "VARCHAR(120)", "nullable": False},
                {"id": "mas-especie", "name": "especie", "type": "VARCHAR(80)", "nullable": False},
                {"id": "mas-raza", "name": "raza", "type": "VARCHAR(80)", "nullable": True},
                {"id": "mas-cliente", "name": "cliente_id", "type": "INT", "nullable": False},
            ],
            x=820,
            y=80,
        ),
        build_node(
            "node-veterinarios",
            "Veterinarios",
            [
                {"id": "vet-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "vet-nombre", "name": "nombre", "type": "VARCHAR(160)", "nullable": False},
                {"id": "vet-especialidad", "name": "especialidad", "type": "VARCHAR(120)", "nullable": True},
                {"id": "vet-telefono", "name": "telefono", "type": "VARCHAR(60)", "nullable": True},
            ],
            x=220,
            y=320,
        ),
        build_node(
            "node-citas",
            "Citas",
            [
                {"id": "cit-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "cit-fecha", "name": "fecha", "type": "DATETIME", "nullable": False},
                {"id": "cit-motivo", "name": "motivo", "type": "VARCHAR(200)", "nullable": True},
                {"id": "cit-cliente", "name": "cliente_id", "type": "INT", "nullable": False},
                {"id": "cit-mascota", "name": "mascota_id", "type": "INT", "nullable": False},
                {"id": "cit-veterinario", "name": "veterinario_id", "type": "INT", "nullable": False},
            ],
            x=520,
            y=320,
            is_join=True,
            join_of=("Clientes", "Mascotas"),
        ),
        build_node(
            "node-tratamientos",
            "Tratamientos",
            [
                {"id": "tra-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "tra-descripcion", "name": "descripcion", "type": "TEXT", "nullable": False},
                {"id": "tra-costo", "name": "costo", "type": "DECIMAL(10,2)", "nullable": True},
                {"id": "tra-cita", "name": "cita_id", "type": "INT", "nullable": False},
            ],
            x=820,
            y=320,
        ),
        build_node(
            "node-historial",
            "HistorialMedico",
            [
                {"id": "his-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "his-diagnostico", "name": "diagnostico", "type": "TEXT", "nullable": False},
                {"id": "his-mascota", "name": "mascota_id", "type": "INT", "nullable": False},
                {"id": "his-veterinario", "name": "veterinario_id", "type": "INT", "nullable": False},
                {"id": "his-fecha", "name": "fecha", "type": "DATE", "nullable": False},
            ],
            x=1120,
            y=320,
        ),
    ]

    edges = [
        build_edge("edge-clinica-clientes", "node-clinica", "node-clientes", source_mult="1", target_mult="*"),
        build_edge("edge-clientes-mascotas", "node-clientes", "node-mascotas", source_mult="1", target_mult="*"),
        build_edge("edge-clinica-veterinarios", "node-clinica", "node-veterinarios", source_mult="1", target_mult="*"),
        build_edge("edge-clientes-citas", "node-clientes", "node-citas", source_mult="1", target_mult="*"),
        build_edge("edge-mascotas-citas", "node-mascotas", "node-citas", source_mult="1", target_mult="*"),
        build_edge("edge-veterinarios-citas", "node-veterinarios", "node-citas", source_mult="1", target_mult="*"),
        build_edge("edge-citas-tratamientos", "node-citas", "node-tratamientos", source_mult="1", target_mult="*"),
        build_edge("edge-mascotas-historial", "node-mascotas", "node-historial", source_mult="1", target_mult="*"),
        build_edge("edge-veterinarios-historial", "node-veterinarios", "node-historial", source_mult="1", target_mult="*"),
    ]

    return {"nodes": nodes, "edges": edges}


def supermarket_diagram() -> Dict[str, Any]:
    nodes = [
        build_node(
            "node-productos",
            "Productos",
            [
                {"id": "prod-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "prod-nombre", "name": "nombre", "type": "VARCHAR(120)", "nullable": False},
                {"id": "prod-precio", "name": "precio", "type": "DECIMAL(10,2)", "nullable": False},
                {"id": "prod-stock", "name": "stock", "type": "INT", "nullable": False},
            ],
            x=460,
            y=140,
        ),
        build_node(
            "node-categorias",
            "Categorias",
            [
                {"id": "cat-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "cat-nombre", "name": "nombre", "type": "VARCHAR(120)", "nullable": False},
                {"id": "cat-descripcion", "name": "descripcion", "type": "TEXT", "nullable": True},
            ],
            x=180,
            y=80,
        ),
        build_node(
            "node-proveedores",
            "Proveedores",
            [
                {"id": "prov-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "prov-nombre", "name": "nombre", "type": "VARCHAR(150)", "nullable": False},
                {"id": "prov-telefono", "name": "telefono", "type": "VARCHAR(50)", "nullable": True},
                {"id": "prov-email", "name": "email", "type": "VARCHAR(120)", "nullable": True},
            ],
            x=760,
            y=80,
        ),
        build_node(
            "node-clientes",
            "Clientes",
            [
                {"id": "cli-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "cli-nombre", "name": "nombre", "type": "VARCHAR(150)", "nullable": False},
                {"id": "cli-email", "name": "email", "type": "VARCHAR(150)", "nullable": True},
                {"id": "cli-telefono", "name": "telefono", "type": "VARCHAR(50)", "nullable": True},
            ],
            x=180,
            y=360,
        ),
        build_node(
            "node-empleados",
            "Empleados",
            [
                {"id": "emp-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "emp-nombre", "name": "nombre", "type": "VARCHAR(150)", "nullable": False},
                {"id": "emp-rol", "name": "rol", "type": "VARCHAR(80)", "nullable": False},
            ],
            x=760,
            y=360,
        ),
        build_node(
            "node-ventas",
            "Ventas",
            [
                {"id": "ven-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "ven-fecha", "name": "fecha", "type": "DATETIME", "nullable": False},
                {"id": "ven-total", "name": "total", "type": "DECIMAL(10,2)", "nullable": False},
                {"id": "ven-cliente", "name": "cliente_id", "type": "INT", "nullable": False},
                {"id": "ven-empleado", "name": "empleado_id", "type": "INT", "nullable": False},
            ],
            x=460,
            y=360,
        ),
        build_node(
            "node-detalle-venta",
            "DetalleVenta",
            [
                {"id": "det-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "det-venta", "name": "venta_id", "type": "INT", "nullable": False},
                {"id": "det-producto", "name": "producto_id", "type": "INT", "nullable": False},
                {"id": "det-cantidad", "name": "cantidad", "type": "INT", "nullable": False},
                {"id": "det-precio", "name": "precio_unitario", "type": "DECIMAL(10,2)", "nullable": False},
            ],
            x=460,
            y=560,
            is_join=True,
            join_of=("Ventas", "Productos"),
        ),
        build_node(
            "node-inventario",
            "Inventario",
            [
                {"id": "inv-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "inv-producto", "name": "producto_id", "type": "INT", "nullable": False},
                {"id": "inv-sucursal", "name": "sucursal", "type": "VARCHAR(80)", "nullable": False},
                {"id": "inv-stock", "name": "stock_actual", "type": "INT", "nullable": False},
            ],
            x=900,
            y=360,
        ),
    ]

    edges = [
        build_edge(
            "edge-cat-productos",
            "node-categorias",
            "node-productos",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-prov-productos",
            "node-proveedores",
            "node-productos",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-productos-inventario",
            "node-productos",
            "node-inventario",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-clientes-ventas",
            "node-clientes",
            "node-ventas",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-empleados-ventas",
            "node-empleados",
            "node-ventas",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-ventas-detalle",
            "node-ventas",
            "node-detalle-venta",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-productos-detalle",
            "node-productos",
            "node-detalle-venta",
            source_mult="1",
            target_mult="*",
        ),
    ]

    return {"nodes": nodes, "edges": edges}



def hospital_diagram() -> Dict[str, Any]:
    nodes = [
        build_node(
            "node-pacientes",
            "Pacientes",
            [
                {"id": "pac-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "pac-nombre", "name": "nombre_completo", "type": "VARCHAR(150)", "nullable": False},
                {"id": "pac-fecha", "name": "fecha_nacimiento", "type": "DATE", "nullable": False},
                {"id": "pac-telefono", "name": "telefono", "type": "VARCHAR(50)", "nullable": True},
            ],
            x=120,
            y=200,
        ),
        build_node(
            "node-doctores",
            "Doctores",
            [
                {"id": "doc-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "doc-nombre", "name": "nombre_completo", "type": "VARCHAR(150)", "nullable": False},
                {"id": "doc-especialidad", "name": "especialidad", "type": "VARCHAR(120)", "nullable": False},
                {"id": "doc-departamento", "name": "departamento_id", "type": "INT", "nullable": False},
            ],
            x=720,
            y=200,
        ),
        build_node(
            "node-departamentos",
            "Departamentos",
            [
                {"id": "dep-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "dep-nombre", "name": "nombre", "type": "VARCHAR(120)", "nullable": False},
                {"id": "dep-ubicacion", "name": "ubicacion", "type": "VARCHAR(80)", "nullable": True},
            ],
            x=720,
            y=40,
        ),
        build_node(
            "node-citas",
            "Citas",
            [
                {"id": "cit-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "cit-paciente", "name": "paciente_id", "type": "INT", "nullable": False},
                {"id": "cit-doctor", "name": "doctor_id", "type": "INT", "nullable": False},
                {"id": "cit-fecha", "name": "fecha", "type": "DATETIME", "nullable": False},
                {"id": "cit-motivo", "name": "motivo", "type": "VARCHAR(200)", "nullable": True},
                {"id": "cit-estado", "name": "estado", "type": "VARCHAR(50)", "nullable": False},
            ],
            x=420,
            y=200,
        ),
        build_node(
            "node-habitaciones",
            "Habitaciones",
            [
                {"id": "hab-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "hab-numero", "name": "numero", "type": "VARCHAR(20)", "nullable": False},
                {"id": "hab-tipo", "name": "tipo", "type": "VARCHAR(50)", "nullable": False},
                {"id": "hab-departamento", "name": "departamento_id", "type": "INT", "nullable": False},
                {"id": "hab-estado", "name": "estado", "type": "VARCHAR(50)", "nullable": False},
            ],
            x=720,
            y=360,
        ),
        build_node(
            "node-ingresos",
            "Ingresos",
            [
                {"id": "ing-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "ing-paciente", "name": "paciente_id", "type": "INT", "nullable": False},
                {"id": "ing-habitacion", "name": "habitacion_id", "type": "INT", "nullable": False},
                {"id": "ing-ingreso", "name": "fecha_ingreso", "type": "DATETIME", "nullable": False},
                {"id": "ing-alta", "name": "fecha_alta", "type": "DATETIME", "nullable": True},
            ],
            x=420,
            y=360,
        ),
        build_node(
            "node-tratamientos",
            "Tratamientos",
            [
                {"id": "trat-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                {"id": "trat-cita", "name": "cita_id", "type": "INT", "nullable": False},
                {"id": "trat-descripcion", "name": "descripcion", "type": "TEXT", "nullable": False},
                {"id": "trat-medicamento", "name": "medicamento", "type": "VARCHAR(120)", "nullable": True},
                {"id": "trat-dosis", "name": "dosis", "type": "VARCHAR(60)", "nullable": True},
            ],
            x=420,
            y=40,
        ),
    ]

    edges = [
        build_edge(
            "edge-departamentos-doctores",
            "node-departamentos",
            "node-doctores",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-pacientes-citas",
            "node-pacientes",
            "node-citas",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-doctores-citas",
            "node-doctores",
            "node-citas",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-departamentos-habitaciones",
            "node-departamentos",
            "node-habitaciones",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-habitaciones-ingresos",
            "node-habitaciones",
            "node-ingresos",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-pacientes-ingresos",
            "node-pacientes",
            "node-ingresos",
            source_mult="1",
            target_mult="*",
        ),
        build_edge(
            "edge-citas-tratamientos",
            "node-citas",
            "node-tratamientos",
            source_mult="1",
            target_mult="*",
        ),
    ]

    return {"nodes": nodes, "edges": edges}


def default_diagram(text: str) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    if "usuario" in text:
        nodes.append(
            build_node(
                "node-usuario-ai",
                "Usuario",
                [
                    {"id": "u-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                    {"id": "u-nombre", "name": "nombre", "type": "VARCHAR(100)", "nullable": False},
                    {"id": "u-email", "name": "email", "type": "VARCHAR(150)", "nullable": False},
                ],
                x=200,
                y=140,
            )
        )

    if "post" in text or "publicacion" in text:
        nodes.append(
            build_node(
                "node-post-ai",
                "Post",
                [
                    {"id": "p-id", "name": "id", "type": "INT", "pk": True, "nullable": False},
                    {"id": "p-user", "name": "user_id", "type": "INT", "nullable": False},
                    {"id": "p-title", "name": "titulo", "type": "VARCHAR(200)", "nullable": False},
                ],
                x=520,
                y=200,
            )
        )

    has_user = any(node["id"] == "node-usuario-ai" for node in nodes)
    has_post = any(node["id"] == "node-post-ai" for node in nodes)
    if has_user and has_post and any(
        keyword in text for keyword in ["relacion", "1:n", "uno a muchos", "uno muchos"]
    ):
        edges.append(
            build_edge(
                "edge-usuario-post-ai",
                "node-usuario-ai",
                "node-post-ai",
                source_mult="1",
                target_mult="*",
                label="Usuario crea Post",
            )
        )

    return {"nodes": nodes, "edges": edges}



@router.get("/history", response_model=list[schemas.PromptHistoryRead])
def get_history(
    limit: int = 30,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> list[schemas.PromptHistoryRead]:
    user = require_current_user(authorization, db)
    safe_limit = max(1, min(limit, 100))
    return crud.list_prompt_history(db, user_id=user.id, limit=safe_limit)


@router.delete("/history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history_entry(
    history_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> None:
    user = require_current_user(authorization, db)
    deleted = crud.delete_prompt_history(db, user_id=user.id, history_id=history_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Entrada no encontrada")


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> None:
    user = require_current_user(authorization, db)
    crud.clear_prompt_history(db, user_id=user.id)


@router.post("/generate")
def generate(
    payload: PromptRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    user = require_current_user(authorization, db)
    result: Dict[str, Any] | None = None

    if payload.graph and payload.graph.nodes:
        incremental = apply_incremental_updates(payload.prompt, payload.graph)
        if incremental:
            result = incremental

    if result is None:
        text = payload.prompt.lower()
        if "supermercado" in text or "supermarket" in text:
            result = supermarket_diagram()
        elif any(keyword in text for keyword in ("universidad", "universitario", "campus")):
            result = university_diagram()
        elif any(keyword in text for keyword in ("hospital", "clinica", "salud")):
            result = hospital_diagram()
        elif any(keyword in text for keyword in ("veterinaria", "veterinario", "mascota", "pet")):
            result = veterinary_diagram()
        else:
            relation_first = build_relation_first_diagram(payload.prompt)
            if relation_first:
                result = relation_first
            else:
                dynamic = generate_dynamic_diagram(payload.prompt)
                result = dynamic if dynamic else default_diagram(text)

    history_payload = schemas.PromptHistoryCreate(prompt=payload.prompt, graph=result)
    if payload.history_id is not None:
        updated = crud.update_prompt_history(
            db,
            user_id=user.id,
            history_id=payload.history_id,
            data=history_payload,
        )
        if updated is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversacion no encontrada")
    else:
        crud.create_prompt_history(
            db,
            user_id=user.id,
            data=history_payload,
        )
    return result


@router.post("/vision")
async def generate_from_image(
    image: UploadFile = File(...),
    prompt: str | None = Form(default=None),
    history_id: int | None = Form(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    user = require_current_user(authorization, db)

    content = await image.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="La imagen no contiene datos.")
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="La imagen supera el limite permitido de 8MB.",
        )

    try:
        graph = await anyio.to_thread.run_sync(
            process_image_to_graph,
            content,
            image.content_type,
            prompt,
        )
    except OpenAIError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo interpretar la imagen con el proveedor de IA: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected failure
        logger.exception("Unhandled error while processing UML image")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ocurrio un error al procesar la imagen: {exc}",
        ) from exc

    prompt_text = (prompt or "").strip()
    if not prompt_text:
        filename = (image.filename or "imagen").split("/")[-1]
        prompt_text = f"Diagrama generado desde imagen {filename}"

    history_payload = schemas.PromptHistoryCreate(prompt=prompt_text, graph=graph)
    if history_id is not None:
        entry = crud.update_prompt_history(db, user.id, history_id, history_payload)
        if entry is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversacion no encontrada.")
    else:
        entry = crud.create_prompt_history(db, user.id, history_payload)

    return {
        "graph": graph,
        "history_id": entry.id,
        "prompt": prompt_text,
    }


def process_image_to_graph(
    image_bytes: bytes,
    content_type: str | None,
    user_prompt: str | None,
) -> Dict[str, Any]:
    payload = _call_openai_vision(image_bytes, content_type, user_prompt)
    return _build_graph_from_vision_payload(payload)


def _call_openai_vision(
    image_bytes: bytes,
    content_type: str | None,
    user_prompt: str | None,
) -> Dict[str, Any]:
    client = _get_openai_client()
    data_uri = _encode_image_to_data_uri(image_bytes, content_type)
    instructions = (
        "Analiza el diagrama UML/ER de la imagen y extrae todas las entidades "
        "(tablas o clases) con sus atributos, identificando claves primarias y "
        "si los campos pueden ser nulos. Identifica tambien las relaciones entre "
        "las entidades y especifica la cardinalidad desde el origen hacia el destino "
        "usando solo los valores: '1', '0..1', '0..*', '1..*' o '*'. "
        "Si detectas claves foraneas, incluye esa informacion en la relacion. "
        "Devuelve un JSON que siga estrictamente el esquema proporcionado."
    )
    if user_prompt:
        instructions += f" Notas del usuario: {user_prompt.strip()}."

    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "uml_graph",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "displayName": {"type": "string"},
                                "columns": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "name": {"type": "string"},
                                            "type": {"type": "string"},
                                            "primaryKey": {"type": "boolean"},
                                            "nullable": {"type": "boolean"},
                                        },
                                        "required": ["name"],
                                    },
                                },
                            },
                            "required": ["name", "columns"],
                        },
                    },
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                                "fromCardinality": {"type": "string"},
                                "toCardinality": {"type": "string"},
                            },
                            "required": ["from", "to"],
                        },
                    },
                },
                "required": ["entities"],
            },
        },
    }

    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": "Eres un asistente que extrae diagramas de datos estructurados en JSON."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instructions},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
        response_format=schema,
        max_tokens=2048,
    )
    raw_output = ""
    if response.choices:
        raw_output = response.choices[0].message.content or ""
    if not raw_output:
        raise ValueError("La IA no devolvio informacion interpretable.")
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ValueError("La respuesta del modelo no es un JSON valido.") from exc


def _encode_image_to_data_uri(image_bytes: bytes, content_type: str | None) -> str:
    mime = content_type if content_type and content_type.startswith("image/") else "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@lru_cache(maxsize=1)
def _get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta la variable de entorno OPENAI_API_KEY. "
            "Configura la clave antes de usar las funciones de vision."
        )
    return OpenAI(api_key=api_key)


def _cardinality_to_mult(value: str | None, default: str) -> str:
    if not value:
        return default
    normalized = value.strip().lower()
    replacements = {
        "one": "1",
        "1": "1",
        "1..1": "1",
        "exactly_one": "1",
        "single": "1",
        "only_one": "1",
        "0..1": "0..1",
        "zero_or_one": "0..1",
        "optional": "0..1",
        "one_to_many": "1..*",
        "1..*": "1..*",
        "zero_to_many": "0..*",
        "0..*": "0..*",
        "many": "*",
        "many_to_many": "*",
        "*": "*",
    }
    for key, mapped in replacements.items():
        if key in normalized:
            return mapped
    return default


def _ensure_unique(base: str, used: set[str]) -> str:
    slug = base
    suffix = 2
    while slug in used:
        slug = f"{base}-{suffix}"
        suffix += 1
    used.add(slug)
    return slug


def _build_graph_from_vision_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    entities = payload.get("entities") or []
    if not isinstance(entities, list) or not entities:
        raise ValueError("La IA no detecto entidades en la imagen.")

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    used_node_slugs: set[str] = set()
    node_lookup: Dict[str, str] = {}

    for idx, entity in enumerate(entities):
        raw_name = str(entity.get("displayName") or entity.get("name") or f"Entidad {idx + 1}")
        base_slug = slugify(raw_name) or f"entidad-{idx + 1}"
        node_slug = _ensure_unique(base_slug, used_node_slugs)
        node_id = f"node-{node_slug}"

        columns_raw = entity.get("columns") or []
        columns: List[Dict[str, Any]] = []
        used_column_slugs: set[str] = set()
        for col_idx, column in enumerate(columns_raw):
            col_name = str(column.get("name") or column.get("label") or f"columna_{col_idx + 1}")
            col_type = str(column.get("type") or column.get("datatype") or "STRING")
            is_pk = bool(column.get("primaryKey") or column.get("pk") or column.get("isPrimary"))
            nullable = column.get("nullable")
            if nullable is None:
                nullable = not is_pk

            col_base_slug = slugify(col_name) or f"columna-{col_idx + 1}"
            col_slug = _ensure_unique(col_base_slug, used_column_slugs)
            columns.append(
                {
                    "id": f"{node_id}-{col_slug}",
                    "name": col_name,
                    "type": col_type,
                    "pk": is_pk,
                    "nullable": bool(nullable),
                }
            )

        if not columns:
            columns.append(
                {
                    "id": f"{node_id}-id",
                    "name": "id",
                    "type": "INT",
                    "pk": True,
                    "nullable": False,
                }
            )

        position = {
            "x": 180 + (idx % 3) * 280,
            "y": 160 + (idx // 3) * 220,
        }
        nodes.append(
            {
                "id": node_id,
                "type": "databaseNode",
                "position": position,
                "data": {
                    "label": raw_name,
                    "columns": columns,
                },
            }
        )

        key_variants = {
            normalize_token(raw_name),
            slugify(raw_name),
            node_slug,
        }
        for variant in key_variants:
            if variant:
                node_lookup[variant] = node_id

    relationships = payload.get("relationships") or []
    used_edge_ids: set[str] = set()
    for rel in relationships:
        raw_from = str(rel.get("from") or rel.get("source") or "")
        raw_to = str(rel.get("to") or rel.get("target") or "")
        if not raw_from or not raw_to:
            continue

        source_id = node_lookup.get(normalize_token(raw_from)) or node_lookup.get(slugify(raw_from))
        target_id = node_lookup.get(normalize_token(raw_to)) or node_lookup.get(slugify(raw_to))
        if not source_id or not target_id:
            continue

        source_slug = source_id.replace("node-", "", 1)
        target_slug = target_id.replace("node-", "", 1)
        edge_base = f"edge-{source_slug}-{target_slug}"
        edge_id = _ensure_unique(edge_base, used_edge_ids)

        label = str(rel.get("label") or rel.get("description") or "")
        source_mult = _cardinality_to_mult(rel.get("fromCardinality"), "1")
        target_mult = _cardinality_to_mult(rel.get("toCardinality"), "*")

        edges.append(
            {
                "id": edge_id,
                "source": source_id,
                "target": target_id,
                "label": label or None,
                "data": {
                    "id": edge_id,
                    "source": source_id,
                    "target": target_id,
                    "kind": "simple",
                    "sourceMult": source_mult,
                    "targetMult": target_mult,
                    "label": label or "",
                },
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
    }

