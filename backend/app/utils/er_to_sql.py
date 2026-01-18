from __future__ import annotations

import re
from typing import Dict, List


def _coerce_string(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_identifier(raw: object, fallback: str) -> str:
    candidate = _coerce_string(raw)
    if not candidate:
        candidate = fallback
    candidate = candidate.replace("`", "")
    candidate = re.sub(r"\s+", "_", candidate)
    candidate = re.sub(r"[^0-9A-Za-z_]+", "_", candidate)
    candidate = re.sub(r"_+", "_", candidate).strip("_")
    if not candidate:
        candidate = fallback
    if candidate[0].isdigit():
        candidate = f"t_{candidate}"
    return candidate


def _ensure_unique_identifier(name: str, used: set[str]) -> str:
    candidate = name
    suffix = 2
    while candidate in used:
        candidate = f"{name}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def to_sql(graph: Dict) -> str:
    """Convierte un grafo (React Flow) a sentencias SQL DDL (MySQL)."""

    nodes = graph.get("nodes", []) or []
    table_sql: List[str] = []
    used_tables: set[str] = set()

    for idx, node in enumerate(nodes, start=1):
        data = node.get("data", {}) or {}
        label_sources = (
            data.get("label"),
            data.get("title"),
            data.get("name"),
            node.get("id"),
            f"table_{idx}",
        )
        display_name = next((value for value in label_sources if _coerce_string(value)), f"table_{idx}")
        table_name = _normalize_identifier(display_name, f"table_{idx}")
        table_name = _ensure_unique_identifier(table_name, used_tables)

        columns = data.get("columns", []) or []
        column_sql: List[str] = []
        primary_keys: List[str] = []
        used_columns: set[str] = set()

        for col_idx, column in enumerate(columns, start=1):
            column_name = _normalize_identifier(column.get("name"), f"col_{col_idx}")
            column_name = _ensure_unique_identifier(column_name, used_columns)
            column_type = _coerce_string(column.get("type")) or "VARCHAR(255)"
            is_pk = bool(column.get("pk"))
            nullable_flag = column.get("nullable")
            null_clause = "" if is_pk else (" NOT NULL" if nullable_flag is False else "")
            column_sql.append(f"  `{column_name}` {column_type}{null_clause}")
            if is_pk:
                primary_keys.append(f"`{column_name}`")

        if not column_sql:
            column_sql.append("  `id` INT NOT NULL")
            primary_keys.append("`id`")

        if primary_keys:
            column_sql.append(f"  PRIMARY KEY ({', '.join(primary_keys)})")

        comment = "" if display_name == table_name else f"-- Tabla: {display_name}\n"
        columns_block = ",\n".join(column_sql)
        table_definition = f"CREATE TABLE `{table_name}` (\n{columns_block}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        table_sql.append(f"{comment}{table_definition}")

    return "\n\n".join(table_sql)
