from __future__ import annotations

import io
import json
import re
import textwrap
import zipfile
from dataclasses import dataclass
from typing import Any, Iterable

JAVA_TYPE_FALLBACK = "String"

JAVA_TYPE_MAP = (
    (re.compile(r"bigint", re.I), "Long"),
    (re.compile(r"int", re.I), "Integer"),
    (re.compile(r"smallint", re.I), "Integer"),
    (re.compile(r"tinyint\(1\)", re.I), "Boolean"),
    (re.compile(r"tinyint", re.I), "Integer"),
    (re.compile(r"decimal|numeric", re.I), "java.math.BigDecimal"),
    (re.compile(r"double", re.I), "Double"),
    (re.compile(r"float", re.I), "Double"),
    (re.compile(r"real", re.I), "Double"),
    (re.compile(r"boolean", re.I), "Boolean"),
    (re.compile(r"bit", re.I), "Boolean"),
    (re.compile(r"datetime|timestamp", re.I), "java.time.LocalDateTime"),
    (re.compile(r"date", re.I), "java.time.LocalDate"),
    (re.compile(r"time", re.I), "java.time.LocalTime"),
    (re.compile(r"char|text|uuid", re.I), "String"),
)

RESERVED_JAVA_KEYWORDS = {
    "abstract",
    "assert",
    "boolean",
    "break",
    "byte",
    "case",
    "catch",
    "char",
    "class",
    "const",
    "continue",
    "default",
    "do",
    "double",
    "else",
    "enum",
    "extends",
    "final",
    "finally",
    "float",
    "for",
    "goto",
    "if",
    "implements",
    "import",
    "instanceof",
    "int",
    "interface",
    "long",
    "native",
    "new",
    "package",
    "private",
    "protected",
    "public",
    "return",
    "short",
    "static",
    "strictfp",
    "super",
    "switch",
    "synchronized",
    "this",
    "throw",
    "throws",
    "transient",
    "try",
    "void",
    "volatile",
    "while",
}


@dataclass
class ColumnSpec:
    field_name: str
    column_name: str
    java_type: str
    is_primary_key: bool
    nullable: bool
    is_generated: bool


@dataclass
class EntitySpec:
    node_id: str
    class_name: str
    table_name: str
    display_name: str
    fields: list[ColumnSpec]
    id_field: ColumnSpec
    path_slug: str


@dataclass
class RelationSpec:
    source: str
    target: str
    label: str
    source_mult: str
    target_mult: str


def slugify(value: str, *, separator: str = "-") -> str:
    value = re.sub(r"[^0-9A-Za-z]+", separator, value.strip().lower())
    value = re.sub(rf"{separator}{{2,}}", separator, value)
    value = value.strip(separator)
    return value or "app"


def camel_case(value: str) -> str:
    parts = [part for part in re.split(r"[^0-9A-Za-z]", value) if part]
    if not parts:
        return "value"
    first, *rest = parts
    first = first.lower()
    rest = [p.capitalize() for p in rest]
    candidate = first + "".join(rest)
    if candidate in RESERVED_JAVA_KEYWORDS:
        candidate += "Value"
    return candidate


def pascal_case(value: str) -> str:
    parts = [part.capitalize() for part in re.split(r"[^0-9A-Za-z]", value) if part]
    if not parts:
        return "Entity"
    candidate = "".join(parts)
    if candidate and candidate[0].isdigit():
        candidate = f"N{candidate}"
    return candidate


def humanize_label(value: str) -> str:
    parts = [part for part in re.split(r"[^0-9A-Za-z]", value) if part]
    if not parts:
        return "Elemento"
    return " ".join(part.capitalize() for part in parts)


def safe_package_segment(value: str) -> str:
    segment = re.sub(r"[^0-9A-Za-z_]", "", (value or "").lower())
    if not segment:
        segment = "app"
    if segment[0].isdigit():
        segment = f"app{segment}"
    if segment in RESERVED_JAVA_KEYWORDS:
        segment = f"{segment}app"
    return segment


def java_field_type(raw: str | None) -> str:
    if not raw:
        return JAVA_TYPE_FALLBACK
    for pattern, mapped in JAVA_TYPE_MAP:
        if pattern.search(raw):
            return mapped
    return JAVA_TYPE_FALLBACK


def split_package_and_simple(java_type: str) -> tuple[str, str]:
    if "." in java_type:
        package, _, simple = java_type.rpartition(".")
        return package, simple
    return "", java_type


def normalise_java_type(java_type: str) -> tuple[str, str]:
    package, simple = split_package_and_simple(java_type)
    if package:
        return package, simple
    return "", java_type


def setter_suffix(field_name: str) -> str:
    if not field_name:
        return "Value"
    return field_name[0].upper() + field_name[1:]


def collect_entity_specs(graph: dict[str, Any]) -> list[EntitySpec]:
    nodes = graph.get("nodes", []) or []
    entities: list[EntitySpec] = []
    for index, node in enumerate(nodes, start=1):
        node_id = str(node.get("id") or f"node_{index}")
        data = node.get("data", {}) or {}
        label = data.get("label") or data.get("title") or f"Table{index}"
        table_slug = slugify(label, separator="_") or f"table_{index}"
        class_name = pascal_case(label)
        path_slug = slugify(label)
        columns = data.get("columns", []) or []
        column_specs: list[ColumnSpec] = []
        id_field: ColumnSpec | None = None
        if not columns:
            columns = [
                {
                    "id": f"{table_slug}_id",
                    "name": "id",
                    "type": "BIGINT",
                    "pk": True,
                    "nullable": False,
                }
            ]
        for col_index, column in enumerate(columns, start=1):
            column_name = column.get("name") or f"col_{col_index}"
            field_name = camel_case(column_name)
            package_name, simple_type = normalise_java_type(java_field_type(column.get("type")))
            full_type = simple_type if not package_name else f"{package_name}.{simple_type}"
            nullable = column.get("nullable", True)
            is_pk = bool(column.get("pk"))
            is_generated = is_pk and simple_type in {"Long", "Integer"}
            spec = ColumnSpec(
                field_name=field_name,
                column_name=column_name,
                java_type=full_type,
                is_primary_key=is_pk,
                nullable=nullable,
                is_generated=is_generated,
            )
            column_specs.append(spec)
            if is_pk and not id_field:
                id_field = spec
        if not id_field:
            fallback = ColumnSpec(
                field_name="id",
                column_name="id",
                java_type="Long",
                is_primary_key=True,
                nullable=False,
                is_generated=True,
            )
            column_specs.insert(0, fallback)
            id_field = fallback
        entities.append(
            EntitySpec(
                node_id=node_id,
                class_name=class_name,
                table_name=table_slug,
                display_name=label,
                fields=column_specs,
                id_field=id_field,
                path_slug=path_slug,
            )
        )
    return entities


def collect_relations(graph: dict[str, Any]) -> list[RelationSpec]:
    relations: list[RelationSpec] = []
    for edge in graph.get("edges", []) or []:
        source = edge.get("source") or ""
        target = edge.get("target") or ""
        if not source or not target:
            continue
        data = edge.get("data", {}) or {}
        relations.append(
            RelationSpec(
                source=source,
                target=target,
                label=(data.get("label") or edge.get("label") or ""),
                source_mult=str(data.get("sourceMult") or ""),
                target_mult=str(data.get("targetMult") or ""),
            )
        )
    return relations


def pom_xml(package: str, artifact_id: str, project_name: str) -> str:
    return textwrap.dedent(
        f"""
        <?xml version="1.0" encoding="UTF-8"?>
        <project xmlns="http://maven.apache.org/POM/4.0.0"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
            <modelVersion>4.0.0</modelVersion>
            <groupId>{package}</groupId>
            <artifactId>{artifact_id}</artifactId>
            <version>0.0.1-SNAPSHOT</version>
            <name>{project_name}</name>
            <description>Generated from UML/ER diagram</description>
            <properties>
                <java.version>17</java.version>
                <spring.boot.version>3.3.4</spring.boot.version>
            </properties>
            <dependencyManagement>
                <dependencies>
                    <dependency>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-dependencies</artifactId>
                        <version>${{spring.boot.version}}</version>
                        <type>pom</type>
                        <scope>import</scope>
                    </dependency>
                </dependencies>
            </dependencyManagement>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-web</artifactId>
                </dependency>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-data-jpa</artifactId>
                </dependency>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-validation</artifactId>
                </dependency>
                <dependency>
                    <groupId>com.mysql</groupId>
                    <artifactId>mysql-connector-j</artifactId>
                    <scope>runtime</scope>
                </dependency>
                <dependency>
                    <groupId>org.projectlombok</groupId>
                    <artifactId>lombok</artifactId>
                    <version>1.18.34</version>
                    <scope>provided</scope>
                </dependency>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-test</artifactId>
                    <scope>test</scope>
                </dependency>
            </dependencies>
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-maven-plugin</artifactId>
                    </plugin>
                </plugins>
            </build>
        </project>
        """
    ).strip() + "\n"


def application_class(package: str, app_class: str) -> str:
    return textwrap.dedent(
        f"""
        package {package};

        import org.springframework.boot.SpringApplication;
        import org.springframework.boot.autoconfigure.SpringBootApplication;

        @SpringBootApplication
        public class {app_class} {{

            public static void main(String[] args) {{
                SpringApplication.run({app_class}.class, args);
            }}
        }}
        """
    ).strip() + "\n"


def application_properties() -> str:
    return textwrap.dedent(
        """
        spring.datasource.url=jdbc:mysql://localhost:3306/app_db
        spring.datasource.username=root
        spring.datasource.password=changeme
        spring.jpa.hibernate.ddl-auto=update
        spring.jpa.show-sql=true
        server.port=8080
        """
    ).strip() + "\n"


def repository_class(package: str, entity: EntitySpec) -> str:
    id_type = entity.id_field.java_type.split('.')[-1]
    return textwrap.dedent(
        f"""
        package {package}.repository;

        import {package}.domain.{entity.class_name};
        import org.springframework.data.jpa.repository.JpaRepository;
        import org.springframework.stereotype.Repository;

        @Repository
        public interface {entity.class_name}Repository extends JpaRepository<{entity.class_name}, {id_type}> {{
        }}
        """
    ).strip() + "\n"


def controller_class(package: str, entity: EntitySpec) -> str:
    id_type = entity.id_field.java_type.split('.')[-1]
    endpoint = entity.path_slug or entity.class_name.lower()
    setter = setter_suffix(entity.id_field.field_name)
    entity_name = entity.class_name
    return textwrap.dedent(
        f"""
        package {package}.controller;

        import {package}.domain.{entity_name};
        import {package}.repository.{entity_name}Repository;
        import jakarta.validation.Valid;
        import org.springframework.http.ResponseEntity;
        import org.springframework.web.bind.annotation.*;

        import java.util.List;

        @RestController
        @CrossOrigin(origins = {{"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8081", "http://127.0.0.1:8081"}}, allowedHeaders = "*")
        @RequestMapping("/api/{endpoint}")
        public class {entity_name}Controller {{

            private final {entity_name}Repository repository;

            public {entity_name}Controller({entity_name}Repository repository) {{
                this.repository = repository;
            }}

            @GetMapping
            public List<{entity_name}> findAll() {{
                return repository.findAll();
            }}

            @GetMapping("/{{id}}")
            public ResponseEntity<{entity_name}> findById(@PathVariable {id_type} id) {{
                return repository.findById(id)
                        .map(ResponseEntity::ok)
                        .orElse(ResponseEntity.notFound().build());
            }}

            @PostMapping
            public {entity_name} create(@RequestBody @Valid {entity_name} request) {{
                return repository.save(request);
            }}

            @PutMapping("/{{id}}")
            public ResponseEntity<{entity_name}> update(@PathVariable {id_type} id, @RequestBody @Valid {entity_name} request) {{
                return repository.findById(id)
                        .map(existing -> {{
                            request.set{setter}(id);
                            return ResponseEntity.ok(repository.save(request));
                        }})
                        .orElse(ResponseEntity.notFound().build());
            }}

            @DeleteMapping("/{{id}}")
            public ResponseEntity<Void> delete(@PathVariable {id_type} id) {{
                if (!repository.existsById(id)) {{
                    return ResponseEntity.notFound().build();
                }}
                repository.deleteById(id);
                return ResponseEntity.noContent().build();
            }}
        }}
        """
    ).strip() + "\n"


def entity_class(package: str, entity: EntitySpec) -> str:
    imports: set[str] = {
        "jakarta.persistence.Column",
        "jakarta.persistence.Entity",
        "jakarta.persistence.GeneratedValue",
        "jakarta.persistence.GenerationType",
        "jakarta.persistence.Id",
        "jakarta.persistence.Table",
        "lombok.Getter",
        "lombok.NoArgsConstructor",
        "lombok.Setter",
    }
    for field in entity.fields:
        package_name, simple = split_package_and_simple(field.java_type)
        if package_name.startswith("java."):
            imports.add(f"{package_name}.{simple}")
    import_lines = "\n".join(f"import {line};" for line in sorted(imports))
    field_chunks: list[str] = []
    for field in entity.fields:
        annotations: list[str] = []
        if field.is_primary_key:
            annotations.append("    @Id")
            if field.is_generated:
                annotations.append("    @GeneratedValue(strategy = GenerationType.IDENTITY)")
        annotations.append(
            f"    @Column(name = \"{field.column_name}\", nullable = {'false' if not field.nullable else 'true'})"
        )
        simple_type = split_package_and_simple(field.java_type)[1]
        annotations.append(f"    private {simple_type} {field.field_name};")
        field_chunks.append("\n".join(annotations))
    fields_block = "\n\n".join(field_chunks)
    return textwrap.dedent(
        f"""
        package {package}.domain;

        {import_lines}

        @Getter
        @Setter
        @NoArgsConstructor
        @Entity
        @Table(name = "{entity.table_name}")
        public class {entity.class_name} {{

        {textwrap.indent(fields_block, '    ')}
        }}
        """
    ).strip() + "\n"


def build_readme(project_name: str, relations: Iterable[RelationSpec]) -> str:
    relation_lines = []
    for relation in relations:
        relation_lines.append(
            f"- {relation.source} -> {relation.target} ({relation.source_mult or '?'}:{relation.target_mult or '?'}) {relation.label}"
        )
    relations_block = "\n".join(relation_lines) if relation_lines else "- No se detectaron relaciones en el grafo."
    return textwrap.dedent(
        f"""
        # {project_name}

        Proyecto Spring Boot generado automaticamente a partir del diagrama UML/ER.

        ## Instrucciones rapidas

        1. Instala Java 17+ y Maven.
        2. Configura la cadena de conexion en `src/main/resources/application.properties`.
        3. Ejecuta:

           ```bash
           mvn spring-boot:run
           ```

        El paquete base es `com.example`. Las entidades, repositorios y controladores se generan de forma basica para que puedas iterar rapidamente.

        ## Frontend generado

        - `frontend_dart/`: cliente web en Dart (usa `dart pub get` y `dart pub global run webdev serve web:8080`).

        ## Relaciones detectadas

        {relations_block}
        """
    ).strip() + "\\n"

def _prepare_frontend_dataset(
    entities: list[EntitySpec],
    relations: list[RelationSpec],
) -> list[dict[str, Any]]:
    def is_many(value: str) -> bool:
        normalized = (value or "").strip().lower()
        return normalized in {"*", "0..*", "1..*", "many", "n"}

    def token_variants(raw: str) -> set[str]:
        tokens: set[str] = set()
        if not raw:
            return tokens
        value = raw.strip().lower()
        for candidate in {value, value.replace("_", "")}:
            if not candidate:
                continue
            tokens.add(candidate)
            if candidate.endswith("s"):
                tokens.add(candidate[:-1])
                tokens.add(candidate[:-1].replace("_", ""))
            else:
                tokens.add(candidate + "s")
                tokens.add((candidate + "s").replace("_", ""))
        return {token for token in tokens if token}

    def find_fk_field(child: EntitySpec, parent: EntitySpec) -> ColumnSpec | None:
        reference_tokens: set[str] = set()
        for value in {parent.class_name, parent.table_name, parent.path_slug, parent.display_name}:
            reference_tokens.update(token_variants(value))
        for field in child.fields:
            candidates = {field.field_name.lower(), field.column_name.lower()}
            for candidate in candidates:
                if not candidate.endswith("id"):
                    continue
                base = candidate[:-2].rstrip("_")
                flat = base.replace("_", "")
                if base in reference_tokens or flat in reference_tokens:
                    return field
        return None

    entity_by_node = {entity.node_id: entity for entity in entities}
    relations_by_entity: dict[str, list[dict[str, Any]]] = {}

    for relation in relations:
        source_entity = entity_by_node.get(relation.source)
        target_entity = entity_by_node.get(relation.target)
        if not source_entity or not target_entity:
            continue

        source_many = is_many(relation.source_mult)
        target_many = is_many(relation.target_mult)

        if source_many == target_many:
            continue

        if source_many and not target_many:
            child_entity, parent_entity = source_entity, target_entity
        else:
            child_entity, parent_entity = target_entity, source_entity

        fk_field = find_fk_field(child_entity, parent_entity)
        if not fk_field:
            continue

        display_field = next(
            (field.field_name for field in parent_entity.fields if not field.is_primary_key),
            parent_entity.id_field.field_name,
        )

        relations_by_entity.setdefault(child_entity.class_name, []).append(
            {
                "fieldName": fk_field.field_name,
                "targetEndpoint": parent_entity.path_slug,
                "targetEntity": parent_entity.display_name or parent_entity.class_name,
                "targetIdField": parent_entity.id_field.field_name,
                "targetLabelField": display_field,
                "required": not fk_field.nullable,
            }
        )

    dataset: list[dict[str, Any]] = []
    for entity in entities:
        fields = [
            {
                "fieldName": field.field_name,
                "label": humanize_label(field.field_name),
                "javaType": field.java_type,
                "nullable": field.nullable,
                "isPrimaryKey": field.is_primary_key,
                "isGenerated": field.is_generated,
            }
            for field in entity.fields
        ]
        dataset.append(
            {
                "name": entity.class_name,
                "displayName": humanize_label(entity.display_name),
                "endpoint": entity.path_slug or entity.class_name.lower(),
                "idField": entity.id_field.field_name,
                "fields": fields,
                "relations": relations_by_entity.get(entity.class_name, []),
            }
        )
    return dataset


def build_frontend_index(
    project_name: str,
    entities: list[EntitySpec],
    relations: list[RelationSpec],
) -> str:
    dataset = _prepare_frontend_dataset(entities, relations)
    entities_json = json.dumps(dataset, ensure_ascii=False)
    title = project_name or "Aplicacion"

    template = textwrap.dedent(
        r"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>__TITLE__ demo frontend</title>
          <style>
            body { font-family: "Segoe UI", Arial, sans-serif; margin: 0; padding: 1.5rem; background: #f5f6f9; color: #1f2933; }
            h1 { margin-top: 0; }
            section { margin-top: 1.5rem; padding: 1rem; background: #ffffff; border: 1px solid #dce1ed; border-radius: 8px; box-shadow: 0 4px 12px rgba(15,23,42,0.08); }
            table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
            th, td { border: 1px solid #d0d6e2; padding: 0.45rem 0.6rem; text-align: left; font-size: 0.9rem; }
            button { cursor: pointer; border: none; border-radius: 5px; padding: 0.45rem 0.75rem; font-size: 0.85rem; color: #ffffff; background: #2563eb; margin-right: 0.35rem; }
            button.secondary { background: #475569; }
            button.danger { background: #dc2626; }
            label { display: block; margin-top: 0.6rem; font-size: 0.85rem; }
            input, textarea, select { width: 100%; margin-top: 0.25rem; padding: 0.45rem 0.55rem; border: 1px solid #cbd5f5; border-radius: 5px; font-family: inherit; }
            textarea { min-height: 70px; resize: vertical; }
            small { color: #64748b; display: block; margin-top: 0.3rem; }
            .muted { color: #94a3b8; }
            .status { margin-top: 0.6rem; font-size: 0.85rem; }
            .status-idle { color: #475569; }
            .status-ok { color: #047857; }
            .status-error { color: #b91c1c; }
            .status-info { color: #2563eb; }
          </style>
        </head>
        <body>
          <h1>__TITLE__</h1>
          <p>Este panel permite probar rapidamente los endpoints REST generados.</p>
          <div id="app"></div>
          <script>
            const ENTITIES = __ENTITIES__;
            const API_BASE = '/api';
            const relationCache = Object.create(null);

            function createEl(tag, className) {
              const el = document.createElement(tag);
              if (className) { el.className = className; }
              return el;
            }

            function textLabel(value) {
              return (value || "").replace(/_/g, " ").replace(/\b\w/g, chr => chr.toUpperCase());
            }

            function inputType(field) {
              const type = String(field.javaType || "").toLowerCase();
              if (type.includes("boolean")) { return "checkbox"; }
              if (type.includes("localdatetime")) { return "datetime-local"; }
              if (type.includes("localdate")) { return "date"; }
              if (type.includes("localtime")) { return "time"; }
              if (type.includes("int") || type.includes("long") || type.includes("double") || type.includes("decimal")) { return "number"; }
              if (type.includes("text")) { return "textarea"; }
              return "text";
            }

            function relationForField(entity, fieldName) {
              if (!entity.relations || !entity.relations.length) { return null; }
              return entity.relations.find((relation) => relation.fieldName === fieldName) || null;
            }

            function setStatus(el, message, tone) {
              el.textContent = message;
              el.className = "status status-" + tone;
            }

            function request(url, options = {}, expectJson = true) {
              const config = Object.assign({ method: "GET" }, options || {});
              config.headers = Object.assign({ Accept: "application/json" }, config.headers || {});
              if (config.body && !config.headers["Content-Type"]) {
                config.headers["Content-Type"] = "application/json";
              }

              return fetch(url, config).then(response => {
                if (!response.ok) {
                  return response.text().then(text => {
                    throw new Error(text || response.statusText || "Error");
                  });
                }
                if (!expectJson || response.status === 204) { return null; }
                const contentType = response.headers.get("Content-Type") || "";
                if (!contentType.includes("application/json")) { return null; }
                return response.json();
              });
            }

            function ensureRelationOptions(relation) {
              const endpoint = relation.targetEndpoint;
              if (!endpoint) { return Promise.resolve([]); }
              if (relationCache[endpoint]) { return Promise.resolve(relationCache[endpoint]); }
              return request(`${API_BASE}/${endpoint}`).then(rows => {
                const list = Array.isArray(rows) ? rows : [];
                relationCache[endpoint] = list;
                return list;
              }).catch(() => {
                relationCache[endpoint] = [];
                return [];
              });
            }

            function ensureEntityRelations(entity) {
              const relations = entity.relations || [];
              if (!relations.length) { return Promise.resolve(); }
              return Promise.all(relations.map(ensureRelationOptions)).then(() => undefined);
            }

            function populateRelationSelect(select, relation, options) {
              select.innerHTML = "";
              const placeholder = document.createElement("option");
              placeholder.value = "";
              placeholder.textContent = relation.required ? "Seleccione una opcion" : "Sin asignar";
              placeholder.selected = true;
              if (relation.required) { placeholder.disabled = true; }
              select.appendChild(placeholder);
              options.forEach(item => {
                if (!item || !Object.prototype.hasOwnProperty.call(item, relation.targetIdField)) { return; }
                const rawValue = item[relation.targetIdField];
                if (rawValue === undefined || rawValue === null) { return; }
                const option = document.createElement("option");
                option.value = String(rawValue);
                const labelValue = item[relation.targetLabelField];
                option.textContent = labelValue === undefined || labelValue === null ? option.value : String(labelValue);
                select.appendChild(option);
              });
            }

            function renderRows(entity, rows, tbody, refresh) {
              tbody.innerHTML = "";
              if (!rows.length) {
                const tr = document.createElement("tr");
                const td = document.createElement("td");
                td.colSpan = entity.fields.length + 1;
                td.className = "muted";
                td.textContent = "No hay registros disponibles.";
                tr.appendChild(td);
                tbody.appendChild(tr);
                return;
              }

              rows.forEach(row => {
                const tr = document.createElement("tr");
                entity.fields.forEach(field => {
                  const td = document.createElement("td");
                  let value = row[field.fieldName];
                  if (value === null || value === undefined) {
                    value = "";
                  } else if (typeof value === "boolean") {
                    value = value ? "Si" : "No";
                  } else {
                    const relation = relationForField(entity, field.fieldName);
                    if (relation) {
                      const options = relationCache[relation.targetEndpoint] || [];
                      const match = options.find(item => {
                        const candidate = item && item[relation.targetIdField];
                        return candidate !== undefined && candidate !== null && String(candidate) === String(value);
                      });
                      if (match) {
                        const labelValue = match[relation.targetLabelField];
                        value = labelValue === undefined || labelValue === null ? match[relation.targetIdField] : labelValue;
                      }
                    }
                  }
                  td.textContent = value;
                  tr.appendChild(td);
                });

                const actions = document.createElement("td");
                const idValue = row[entity.idField];
                if (idValue !== undefined && idValue !== null) {
                  const delBtn = createEl("button", "danger");
                  delBtn.type = "button";
                  delBtn.textContent = "Eliminar";
                  delBtn.addEventListener("click", () => {
                    if (!confirm("Eliminar este registro?")) { return; }
                    request(`${API_BASE}/${entity.endpoint}/${encodeURIComponent(idValue)}`, { method: "DELETE" }, false)
                      .then(refresh)
                      .catch(error => { alert(error.message); });
                  });
                  actions.appendChild(delBtn);
                } else {
                  actions.textContent = "-";
                }
                tr.appendChild(actions);
                tbody.appendChild(tr);
              });
            }

            function refreshRows(entity, statusEl, tbody) {
              setStatus(statusEl, "Consultando registros...", "info");
              Promise.all([ensureEntityRelations(entity), request(`${API_BASE}/${entity.endpoint}`)])
                .then(([, rows]) => {
                  const list = Array.isArray(rows) ? rows : [];
                  renderRows(entity, list, tbody, () => refreshRows(entity, statusEl, tbody));
                  setStatus(statusEl, "Se cargaron " + list.length + " registros.", "ok");
                })
                .catch(error => {
                  setStatus(statusEl, error.message, "error");
                  tbody.innerHTML = "";
                });
            }

            function gatherFormData(form, entity) {
              const data = {};
              Array.from(form.querySelectorAll("[data-field]")).forEach(control => {
                const fieldName = control.dataset.field;
                const field = entity.fields.find(item => item.fieldName === fieldName);
                if (!field) { return; }
                const relation = relationForField(entity, fieldName);

                if (control.type === "checkbox") {
                  data[fieldName] = control.checked;
                  return;
                }

                const raw = String(control.value ?? "").trim();
                if (!raw) {
                  if (field.nullable) {
                    data[fieldName] = null;
                    return;
                  }
                  throw new Error("El campo " + textLabel(field.label || field.fieldName) + " es obligatorio.");
                }

                const typeHint = inputType(field);
                if (typeHint === "number") {
                  const numeric = Number(raw);
                  if (Number.isNaN(numeric)) {
                    throw new Error("El campo " + textLabel(field.label || field.fieldName) + " debe ser numerico.");
                  }
                  data[fieldName] = numeric;
                } else {
                  data[fieldName] = raw;
                }
              });
              return data;
            }

            function buildForm(entity, statusEl, refresh) {
              const form = document.createElement("form");
              const editable = entity.fields.filter(field => !(field.isPrimaryKey && field.isGenerated));
              if (!editable.length) {
                const note = document.createElement("small");
                note.className = "muted";
                note.textContent = "No hay campos editables para crear registros.";
                form.appendChild(note);
                return form;
              }

              editable.forEach(field => {
                const label = document.createElement("label");
                label.textContent = textLabel(field.label || field.fieldName);
                const relation = relationForField(entity, field.fieldName);
                if (relation) {
                  const select = document.createElement("select");
                  select.dataset.field = field.fieldName;
                  if (!field.nullable) { select.required = true; }
                  select.disabled = true;
                  label.appendChild(select);
                  ensureRelationOptions(relation)
                    .then(options => {
                      populateRelationSelect(select, relation, options);
                      select.disabled = false;
                    })
                    .catch(() => {
                      select.innerHTML = "";
                      const opt = document.createElement("option");
                      opt.value = "";
                      opt.textContent = "No se pudo cargar opciones";
                      opt.disabled = true;
                      opt.selected = true;
                      select.appendChild(opt);
                      select.disabled = true;
                    });
                  form.appendChild(label);
                  return;
                }

                const type = inputType(field);
                let input;
                if (type === "textarea") {
                  input = document.createElement("textarea");
                } else {
                  input = document.createElement("input");
                  input.type = type;
                }
                input.dataset.field = field.fieldName;
                if (!field.nullable) { input.required = true; }
                if (type === "checkbox") { input.checked = false; }
                label.appendChild(input);
                form.appendChild(label);
              });

              const submit = createEl("button", "primary");
              submit.type = "submit";
              submit.textContent = "Crear registro";
              form.appendChild(submit);

              form.addEventListener("submit", event => {
                event.preventDefault();
                try {
                  setStatus(statusEl, "Guardando registro...", "info");
                  const payload = gatherFormData(form, entity);
                  request(`${API_BASE}/${entity.endpoint}`, { method: "POST", body: JSON.stringify(payload) })
                    .then(() => {
                      form.reset();
                      setStatus(statusEl, "Registro creado correctamente.", "ok");
                      return refresh();
                    })
                    .catch(error => {
                      setStatus(statusEl, error.message, "error");
                    });
                } catch (error) {
                  setStatus(statusEl, error.message, "error");
                }
              });

              return form;
            }

            function buildTable(entity) {
              const wrapper = createEl("div", "table-wrapper");
              const table = createEl("table", "entity-table");
              const thead = document.createElement("thead");
              const headerRow = document.createElement("tr");
              entity.fields.forEach(field => {
                const th = document.createElement("th");
                th.textContent = textLabel(field.label || field.fieldName);
                headerRow.appendChild(th);
              });
              const actionsTh = document.createElement("th");
              actionsTh.textContent = "Acciones";
              headerRow.appendChild(actionsTh);
              thead.appendChild(headerRow);
              table.appendChild(thead);
              const tbody = document.createElement("tbody");
              table.appendChild(tbody);
              wrapper.appendChild(table);
              return { container: wrapper, tbody };
            }

            function buildSection(entity) {
              const section = document.createElement("section");
              const titleEl = document.createElement("h2");
              titleEl.textContent = entity.displayName || entity.name;
              section.appendChild(titleEl);

              const info = document.createElement("small");
              info.textContent = "Endpoint: /api/" + entity.endpoint;
              section.appendChild(info);

              const statusEl = createEl("div", "status status-idle");
              statusEl.textContent = "Listo para usar.";
              section.appendChild(statusEl);

              const refreshBtn = createEl("button", "secondary");
              refreshBtn.type = "button";
              refreshBtn.textContent = "Recargar";
              section.appendChild(refreshBtn);

              const table = buildTable(entity);
              const form = buildForm(entity, statusEl, () => refreshRows(entity, statusEl, table.tbody));
              section.appendChild(form);
              section.appendChild(table.container);

              refreshBtn.addEventListener("click", () => refreshRows(entity, statusEl, table.tbody));
              refreshRows(entity, statusEl, table.tbody);
              return section;
            }

            document.addEventListener("DOMContentLoaded", () => {
              const mount = document.getElementById("app");
              if (!ENTITIES.length) {
                const empty = document.createElement("section");
                const msg = document.createElement("p");
                msg.className = "muted";
                msg.textContent = "No se detectaron entidades en el diagrama.";
                empty.appendChild(msg);
                mount.appendChild(empty);
                return;
              }

              ENTITIES.forEach(entity => {
                mount.appendChild(buildSection(entity));
              });
            });
          </script>
        </body>
        </html>
        """
    )

    return template.replace("__TITLE__", title).replace("__ENTITIES__", entities_json).strip() + "\n"


def build_dart_frontend(
    project_name: str,
    entities: list[EntitySpec],
    relations: list[RelationSpec],
) -> dict[str, str]:
    dataset = _prepare_frontend_dataset(entities, relations)
    metadata_json = json.dumps(dataset, ensure_ascii=False, indent=2)
    package_slug = slugify(project_name or "generated", separator="_") or "generated"
    if package_slug[0].isdigit():
        package_slug = f"app_{package_slug}"
    package_name = f"{package_slug}_frontend"
    app_title = humanize_label(project_name or "Aplicacion")

    pubspec_yaml = textwrap.dedent(
        f"""
        name: {package_name}
        description: Frontend web en Dart para {app_title}
        publish_to: "none"
        version: 0.1.0+1

        environment:
          sdk: ">=3.4.0 <4.0.0"

        dev_dependencies:
          build_runner: ^2.4.9
          build_web_compilers: ^4.0.9
        """
    ).strip() + "\n"

    analysis_options = textwrap.dedent(
        """
        include: package:lints/recommended.yaml
        """
    ).strip() + "\n"

    main_template = textwrap.dedent(
        """

        import 'dart:convert';
        import 'dart:html';

        const String kApiBase = 'http://127.0.0.1:8080/api';
        const String kMetadataJson = r'''__METADATA_JSON__''';

        final List<EntityMetadata> kEntities = _loadEntities();
        final Map<String, List<RelationOption>> _relationCache = <String, List<RelationOption>>{};

        List<EntityMetadata> _loadEntities() {
          final dynamic decoded = jsonDecode(kMetadataJson);
          if (decoded is! List) {
            return <EntityMetadata>[];
          }
          final List<EntityMetadata> entities = <EntityMetadata>[];
          for (final dynamic item in decoded) {
            if (item is Map) {
              entities.add(
                EntityMetadata.fromJson(
                  Map<String, dynamic>.from(item as Map<dynamic, dynamic>),
                ),
              );
            }
          }
          return entities;
        }

        void main() {
          final Element? mount = document.getElementById('app');
          if (mount == null) {
            window.console.error('No se encontro el contenedor #app.');
            return;
          }
          if (kEntities.isEmpty) {
            final ParagraphElement empty = ParagraphElement()
              ..classes.add('muted')
              ..text = 'No se detectaron entidades en el diagrama.';
            mount.append(empty);
            return;
          }
          for (final EntityMetadata entity in kEntities) {
            mount.append(buildEntitySection(entity));
          }
        }

        DivElement buildEntitySection(EntityMetadata entity) {
          final DivElement section = DivElement()..classes.add('entity-section');
          final Map<String, List<RelationOption>> relationOptions = <String, List<RelationOption>>{};
          final Map<String, SelectElement> relationSelects = <String, SelectElement>{};

          final HeadingElement title = HeadingElement.h2()..text = entity.displayName;
          section.append(title);

          final ParagraphElement info = ParagraphElement()
            ..classes.add('muted')
            ..text = 'Endpoint: /api/${entity.endpoint}';
          section.append(info);

          final DivElement status = DivElement()
            ..classes.addAll(<String>['status', 'status-idle'])
            ..text = 'Listo para usar.';
          section.append(status);

          final ButtonElement refreshButton = ButtonElement()
            ..classes.add('secondary')
            ..text = 'Recargar';
          section.append(refreshButton);

          final TableElements tableElements = buildTable(entity);
          final FormElement form = buildForm(
            entity,
            status,
            relationOptions,
            relationSelects,
            () => refreshRows(entity, status, tableElements.tbody, relationOptions, relationSelects),
          );
          section
            ..append(form)
            ..append(tableElements.container);

          refreshButton.onClick.listen((_) {
            refreshRows(entity, status, tableElements.tbody, relationOptions, relationSelects);
          });

          refreshRows(entity, status, tableElements.tbody, relationOptions, relationSelects);

          return section;
        }

        Future<void> refreshRows(
          EntityMetadata entity,
          DivElement status,
          TableSectionElement tbody,
          Map<String, List<RelationOption>> relationOptions,
          Map<String, SelectElement> relationSelects,
        ) async {
          setStatus(status, 'Consultando registros...', 'info');
          try {
            if (entity.relations.isNotEmpty) {
              await Future.wait(
                entity.relations.map((RelationMetadata relation) async {
                  final List<RelationOption> options = await ensureRelationOptions(relation);
                  relationOptions[relation.fieldName] = options;
                  final SelectElement? select = relationSelects[relation.fieldName];
                  if (select != null) {
                    populateRelationSelect(select, relation, options);
                  }
                }),
              );
            }
            final List<Map<String, dynamic>> rows = await fetchRows(entity.endpoint);
            renderRows(
              entity,
              rows,
              tbody,
              relationOptions,
              status,
              () => refreshRows(entity, status, tbody, relationOptions, relationSelects),
            );
            setStatus(status, 'Se cargaron ${rows.length} registros.', 'ok');
          } on ApiException catch (error) {
            setStatus(status, error.message, 'error');
            tbody.children.clear();
          } catch (error) {
            setStatus(status, error.toString(), 'error');
            tbody.children.clear();
          }
        }

        Future<List<RelationOption>> ensureRelationOptions(RelationMetadata relation) async {
          final String endpoint = relation.targetEndpoint;
          if (endpoint.isEmpty) {
            return <RelationOption>[];
          }
          if (_relationCache.containsKey(endpoint)) {
            return _relationCache[endpoint]!;
          }
          final List<Map<String, dynamic>> rows = await fetchRows(endpoint);
          final List<RelationOption> options = <RelationOption>[];
          for (final Map<String, dynamic> row in rows) {
            final dynamic idValue = row[relation.targetIdField];
            if (idValue == null) {
              continue;
            }
            final dynamic labelValue = row[relation.targetLabelField];
            options.add(
              RelationOption(
                id: idValue.toString(),
                label: labelValue == null ? idValue.toString() : labelValue.toString(),
                rawValue: idValue,
              ),
            );
          }
          _relationCache[endpoint] = options;
          return options;
        }

        Future<List<Map<String, dynamic>>> fetchRows(String endpoint) async {
          final dynamic payload = await request(endpoint);
          if (payload is List) {
            final List<Map<String, dynamic>> rows = <Map<String, dynamic>>[];
            for (final dynamic item in payload) {
              if (item is Map) {
                rows.add(Map<String, dynamic>.from(item as Map<dynamic, dynamic>));
              }
            }
            return rows;
          }
          return <Map<String, dynamic>>[];
        }

        Future<dynamic> request(
          String endpoint, {
          String method = 'GET',
          String? body,
          bool expectJson = true,
        }) async {
          final String clean = endpoint.startsWith('/')
              ? endpoint.substring(1)
              : endpoint;
          final String base = kApiBase.endsWith('/')
              ? kApiBase.substring(0, kApiBase.length - 1)
              : kApiBase;
          final String url = base + '/' + clean;
          final Map<String, String> headers = <String, String>{
            'Accept': 'application/json',
          };
          if (body != null) {
            headers['Content-Type'] = 'application/json';
          }
          final HttpRequest response = await HttpRequest.request(
            url,
            method: method,
            requestHeaders: headers,
            sendData: body,
          );
          final int status = response.status ?? 0;
          if (status < 200 || status >= 300) {
            throw ApiException('Error ' + status.toString() + ' al contactar ' + url);
          }
          final String text = response.responseText ?? '';
          if (!expectJson || text.isEmpty) {
            return null;
          }
          return jsonDecode(text);
        }

        void renderRows(
          EntityMetadata entity,
          List<Map<String, dynamic>> rows,
          TableSectionElement tbody,
          Map<String, List<RelationOption>> relationOptions,
          DivElement status,
          Future<void> Function() refresh,
        ) {
          tbody.children.clear();
          if (rows.isEmpty) {
            final TableRowElement emptyRow = TableRowElement();
            final TableCellElement cell = TableCellElement()
              ..colSpan = entity.fields.length + 1
              ..classes.add('muted')
              ..text = 'No hay registros disponibles.';
            emptyRow.append(cell);
            tbody.append(emptyRow);
            return;
          }
          for (final Map<String, dynamic> row in rows) {
            final TableRowElement tr = TableRowElement();
            for (final FieldMetadata field in entity.fields) {
              final TableCellElement td = TableCellElement();
              final dynamic value = row[field.fieldName];
              td.text = formatDisplayValue(entity, field, value, relationOptions);
              tr.append(td);
            }
            final dynamic idValue = row[entity.idField];
            final TableCellElement actions = TableCellElement();
            if (idValue != null) {
              final ButtonElement deleteButton = ButtonElement()
                ..classes.add('danger')
                ..text = 'Eliminar';
              deleteButton.onClick.listen((_) async {
                final bool confirmed = window.confirm('Eliminar este registro?');
                if (!confirmed) {
                  return;
                }
                try {
                  await request(
                    entity.endpoint + '/' + Uri.encodeComponent(idValue.toString()),
                    method: 'DELETE',
                    expectJson: false,
                  );
                  setStatus(status, 'Registro eliminado.', 'ok');
                  await refresh();
                } on ApiException catch (error) {
                  setStatus(status, error.message, 'error');
                } catch (error) {
                  setStatus(status, error.toString(), 'error');
                }
              });
              actions.append(deleteButton);
            } else {
              actions.text = '-';
            }
            tr.append(actions);
            tbody.append(tr);
          }
        }

        String formatDisplayValue(
          EntityMetadata entity,
          FieldMetadata field,
          dynamic value,
          Map<String, List<RelationOption>> relationOptions,
        ) {
          if (value == null) {
            return '';
          }
          final RelationMetadata? relation = entity.relationFor(field.fieldName);
          if (relation != null) {
            final List<RelationOption>? options =
                relationOptions[field.fieldName] ?? _relationCache[relation.targetEndpoint];
            if (options != null) {
              for (final RelationOption option in options) {
                if (_valuesEqual(option.rawValue, value)) {
                  return option.label;
                }
              }
            }
          }
          if (value is bool) {
            return value ? 'Si' : 'No';
          }
          return value.toString();
        }

        bool _valuesEqual(dynamic a, dynamic b) {
          if (a == null || b == null) {
            return a == b;
          }
          if (a is num && b is num) {
            return a == b;
          }
          return a.toString() == b.toString();
        }

        FormElement buildForm(
          EntityMetadata entity,
          DivElement status,
          Map<String, List<RelationOption>> relationOptions,
          Map<String, SelectElement> relationSelects,
          Future<void> Function() refresh,
        ) {
          final FormElement form = FormElement();
          final List<FieldMetadata> editable = entity.editableFields;
          if (editable.isEmpty) {
            final ParagraphElement note = ParagraphElement()
              ..classes.add('muted')
              ..text = 'No hay campos editables para crear registros.';
            form.append(note);
            return form;
          }
          for (final FieldMetadata field in editable) {
            final RelationMetadata? relation = entity.relationFor(field.fieldName);
            final String inputId = '${entity.name}-${field.fieldName}';
            if (relation != null) {
              final LabelElement label = LabelElement()
                ..text = textLabel(field.label)
                ..htmlFor = inputId;
              final SelectElement select = SelectElement()
                ..id = inputId
                ..dataset['field'] = field.fieldName
                ..disabled = true;
              if (!field.nullable) {
                select.required = true;
              }
              relationSelects[field.fieldName] = select;
              populateRelationSelect(select, relation, relationOptions[field.fieldName] ?? <RelationOption>[]);
              label.append(select);
              form.append(label);
              continue;
            }
            final String kind = inputType(field);
            if (kind == 'checkbox') {
              final CheckboxInputElement checkbox = CheckboxInputElement()
                ..id = inputId
                ..dataset['field'] = field.fieldName
                ..checked = false;
              final LabelElement wrapper = LabelElement()..htmlFor = inputId;
              wrapper
                ..append(checkbox)
                ..appendText(' ' + textLabel(field.label));
              form.append(wrapper);
              continue;
            }
            final LabelElement label = LabelElement()
              ..text = textLabel(field.label)
              ..htmlFor = inputId;
            if (kind == 'textarea') {
              final TextAreaElement textarea = TextAreaElement()
                ..id = inputId
                ..dataset['field'] = field.fieldName;
              if (!field.nullable) {
                textarea.required = true;
              }
              label.append(textarea);
            } else {
              final InputElement input = InputElement()
                ..id = inputId
                ..dataset['field'] = field.fieldName
                ..type = kind;
              if (!field.nullable) {
                input.required = true;
              }
              label.append(input);
            }
            form.append(label);
          }
          final ButtonElement submit = ButtonElement()
            ..classes.add('primary')
            ..type = 'submit'
            ..text = 'Crear registro';
          form.append(submit);

          form.onSubmit.listen((Event event) async {
            event.preventDefault();
            try {
              setStatus(status, 'Guardando registro...', 'info');
              final Map<String, dynamic> payload = gatherFormData(form, entity, relationOptions);
              await request(
                entity.endpoint,
                method: 'POST',
                body: jsonEncode(payload),
              );
              form.reset();
              relationSelects.forEach((String _, SelectElement select) {
                select.value = '';
              });
              setStatus(status, 'Registro creado correctamente.', 'ok');
              await refresh();
            } on ApiException catch (error) {
              setStatus(status, error.message, 'error');
            } catch (error) {
              setStatus(status, error.toString(), 'error');
            }
          });

          return form;
        }

        Map<String, dynamic> gatherFormData(
          FormElement form,
          EntityMetadata entity,
          Map<String, List<RelationOption>> relationOptions,
        ) {
          final Map<String, dynamic> data = <String, dynamic>{};
          for (final Element element in form.querySelectorAll('[data-field]')) {
            final String fieldName = element.dataset['field'] ?? '';
            final FieldMetadata? field = entity.fieldByName(fieldName);
            if (field == null) {
              continue;
            }
            final RelationMetadata? relation = entity.relationFor(fieldName);
    if (relation != null) {
      final SelectElement select = element as SelectElement;
      final String selected = select.value?.trim() ?? '';
      if (selected.isEmpty) {
        if (field.nullable) {
          data[fieldName] = null;
          continue;
        }
        throw ApiException('Selecciona un valor para ' + textLabel(field.label) + '.');
      }
      final List<RelationOption>? options =
          relationOptions[fieldName] ?? _relationCache[relation.targetEndpoint];
      final RelationOption? match = options?.firstWhere(
        (RelationOption option) => option.id == selected,
        orElse: () => RelationOption(id: selected, label: selected, rawValue: selected),
      );
      data[fieldName] = match?.rawValue ?? selected;
      continue;
    }
    final String kind = inputType(field);
    if (kind == 'checkbox') {
      final CheckboxInputElement checkbox = element as CheckboxInputElement;
      data[fieldName] = checkbox.checked ?? false;
      continue;
    }
    String raw = '';
    if (kind == 'textarea') {
      final TextAreaElement textarea = element as TextAreaElement;
      raw = textarea.value?.trim() ?? '';
    } else {
      final InputElement input = element as InputElement;
      raw = input.value?.trim() ?? '';
    }
    if (raw.isEmpty) {
      if (field.nullable) {
        data[fieldName] = null;
      } else {
                throw ApiException('El campo ' + textLabel(field.label) + ' es obligatorio.');
              }
              continue;
            }
            if (field.isNumeric) {
              if (field.javaTypeLower.contains('int') || field.javaTypeLower.contains('long')) {
                final int? parsed = int.tryParse(raw);
                if (parsed == null) {
                  throw ApiException('El campo ' + textLabel(field.label) + ' debe ser numerico.');
                }
                data[fieldName] = parsed;
              } else {
                final double? parsed = double.tryParse(raw);
                if (parsed == null) {
                  throw ApiException('El campo ' + textLabel(field.label) + ' debe ser numerico.');
                }
                data[fieldName] = parsed;
              }
            } else {
              data[fieldName] = raw;
            }
          }
          return data;
        }

        void populateRelationSelect(
          SelectElement select,
          RelationMetadata relation,
          List<RelationOption> options,
        ) {
          select.children.clear();
          final OptionElement placeholder = OptionElement()
            ..value = ''
            ..text = options.isEmpty
                ? 'Sin datos disponibles'
                : (relation.required ? 'Seleccione una opcion' : 'Sin asignar')
            ..selected = true;
          if (relation.required && options.isNotEmpty) {
            placeholder.disabled = true;
          }
          select.append(placeholder);
          for (final RelationOption option in options) {
            select.append(OptionElement()
              ..value = option.id
              ..text = option.label);
          }
          select.disabled = options.isEmpty;
        }

        TableElements buildTable(EntityMetadata entity) {
          final DivElement wrapper = DivElement()..classes.add('table-wrapper');
          final TableElement table = TableElement()..classes.add('entity-table');
          final TableSectionElement thead = table.createTHead();
          final TableRowElement headerRow = TableRowElement();
          for (final FieldMetadata field in entity.fields) {
            final TableCellElement headerCell = document.createElement('th') as TableCellElement
              ..text = textLabel(field.label);
            headerRow.append(headerCell);
          }
          final TableCellElement actionsHeader = document.createElement('th') as TableCellElement
            ..text = 'Acciones';
          headerRow.append(actionsHeader);
          thead.append(headerRow);
          final TableSectionElement tbody = table.createTBody();
          wrapper.append(table);
          return TableElements(container: wrapper, tbody: tbody);
        }

        String inputType(FieldMetadata field) {
          final String lower = field.javaTypeLower;
          if (lower.contains('boolean')) {
            return 'checkbox';
          }
          if (lower.contains('localdatetime')) {
            return 'datetime-local';
          }
          if (lower.contains('localdate')) {
            return 'date';
          }
          if (lower.contains('localtime')) {
            return 'time';
          }
          if (lower.contains('int') || lower.contains('long') || lower.contains('double') || lower.contains('decimal')) {
            return 'number';
          }
          if (lower.contains('text')) {
            return 'textarea';
          }
          return 'text';
        }

        String textLabel(String value) {
          return value.replaceAll('_', ' ').split(' ').map((String part) {
            if (part.isEmpty) {
              return part;
            }
            return part[0].toUpperCase() + part.substring(1);
          }).join(' ');
        }

        void setStatus(DivElement element, String message, String tone) {
          element
            ..text = message
            ..className = 'status status-' + tone;
        }

        class TableElements {
          TableElements({required this.container, required this.tbody});
          final DivElement container;
          final TableSectionElement tbody;
        }

        class EntityMetadata {
          EntityMetadata({
            required this.name,
            required this.displayName,
            required this.endpoint,
            required this.idField,
            required this.fields,
            required this.relations,
          });

          final String name;
          final String displayName;
          final String endpoint;
          final String idField;
          final List<FieldMetadata> fields;
          final List<RelationMetadata> relations;

          List<FieldMetadata> get editableFields =>
              fields.where((FieldMetadata field) => !(field.isPrimaryKey && field.isGenerated)).toList(growable: false);

          FieldMetadata? fieldByName(String fieldName) {
            for (final FieldMetadata field in fields) {
              if (field.fieldName == fieldName) {
                return field;
              }
            }
            return null;
          }

          RelationMetadata? relationFor(String fieldName) {
            for (final RelationMetadata relation in relations) {
              if (relation.fieldName == fieldName) {
                return relation;
              }
            }
            return null;
          }

          factory EntityMetadata.fromJson(Map<String, dynamic> json) {
            final List<dynamic> fieldList = json['fields'] as List<dynamic>? ?? const <dynamic>[];
            final List<dynamic> relationList = json['relations'] as List<dynamic>? ?? const <dynamic>[];
            return EntityMetadata(
              name: json['name'] as String? ?? 'Entity',
              displayName: json['displayName'] as String? ?? (json['name'] as String? ?? 'Entity'),
              endpoint: json['endpoint'] as String? ?? '',
              idField: json['idField'] as String? ?? 'id',
              fields: fieldList
                  .whereType<Map>()
                  .map(
                    (dynamic item) => FieldMetadata.fromJson(
                      Map<String, dynamic>.from(item as Map<dynamic, dynamic>),
                    ),
                  )
                  .toList(growable: false),
              relations: relationList
                  .whereType<Map>()
                  .map(
                    (dynamic item) => RelationMetadata.fromJson(
                      Map<String, dynamic>.from(item as Map<dynamic, dynamic>),
                    ),
                  )
                  .toList(growable: false),
            );
          }
        }

          class FieldMetadata {
          FieldMetadata({
            required this.fieldName,
            required this.label,
            required this.javaType,
            required this.nullable,
            required this.isPrimaryKey,
            required this.isGenerated,
          });

          final String fieldName;
          final String label;
          final String javaType;
          final bool nullable;
          final bool isPrimaryKey;
          final bool isGenerated;

          factory FieldMetadata.fromJson(Map<String, dynamic> json) {
            return FieldMetadata(
              fieldName: json['fieldName'] as String? ?? 'field',
              label: json['label'] as String? ?? (json['fieldName'] as String? ?? 'field'),
              javaType: json['javaType'] as String? ?? 'String',
              nullable: json['nullable'] as bool? ?? true,
              isPrimaryKey: json['isPrimaryKey'] as bool? ?? false,
              isGenerated: json['isGenerated'] as bool? ?? false,
            );
          }

          String get javaTypeLower => javaType.toLowerCase();
          bool get isNumeric =>
              javaTypeLower.contains('int') ||
              javaTypeLower.contains('long') ||
              javaTypeLower.contains('double') ||
              javaTypeLower.contains('decimal') ||
              javaTypeLower.contains('float');
        }

        class RelationMetadata {
          RelationMetadata({
            required this.fieldName,
            required this.targetEndpoint,
            required this.targetEntity,
            required this.targetIdField,
            required this.targetLabelField,
            required this.required,
          });

          final String fieldName;
          final String targetEndpoint;
          final String targetEntity;
          final String targetIdField;
          final String targetLabelField;
          final bool required;

          factory RelationMetadata.fromJson(Map<String, dynamic> json) {
            return RelationMetadata(
              fieldName: json['fieldName'] as String? ?? 'id',
              targetEndpoint: json['targetEndpoint'] as String? ?? '',
              targetEntity: json['targetEntity'] as String? ?? '',
              targetIdField: json['targetIdField'] as String? ?? 'id',
              targetLabelField: json['targetLabelField'] as String? ?? 'id',
              required: json['required'] as bool? ?? false,
            );
          }
        }

        class RelationOption {
          RelationOption({
            required this.id,
            required this.label,
            required this.rawValue,
          });

          final String id;
          final String label;
          final dynamic rawValue;
        }

        class ApiException implements Exception {
          ApiException(this.message);
          final String message;
          @override
          String toString() => message;
        }
        """
    ).strip() + "\n"

    index_html = textwrap.dedent(
        """
        <!DOCTYPE html>
        <html lang="es">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>__APP_TITLE__ (Dart)</title>
          <link rel="stylesheet" href="styles.css" />
          <script defer src="main.dart.js"></script>
        </head>
        <body>
          <h1>__APP_TITLE__</h1>
          <p>Panel basico en Dart para interactuar con los endpoints REST generados.</p>
          <div id="app"></div>
        </body>
        </html>
        """
    ).strip().replace("__APP_TITLE__", app_title) + "\n"

    styles_css = textwrap.dedent(
        """
body {
  font-family: Arial, sans-serif;
  margin: 0;
  padding: 1.5rem;
  background: #f5f6f9;
  color: #1f2933;
}
h1 {
  margin-top: 0;
}
.entity-section {
  margin-top: 1.5rem;
  padding: 1rem;
  background: #ffffff;
  border: 1px solid #dce1ed;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}
.muted {
  color: #64748b;
  font-size: 0.9rem;
}
.status {
  margin: 0.75rem 0;
  font-size: 0.9rem;
}
.status-info {
  color: #2563eb;
}
.status-ok {
  color: #047857;
}
.status-error {
  color: #b91c1c;
}
.table-wrapper {
  margin-top: 1rem;
  overflow-x: auto;
}
.entity-table {
  width: 100%;
  border-collapse: collapse;
}
.entity-table th,
.entity-table td {
  border: 1px solid #d0d6e2;
  padding: 0.45rem 0.6rem;
  text-align: left;
  font-size: 0.9rem;
}
button {
  cursor: pointer;
  border: none;
  border-radius: 5px;
  padding: 0.45rem 0.75rem;
  font-size: 0.85rem;
  color: #ffffff;
  background: #2563eb;
  margin-top: 0.6rem;
  margin-right: 0.35rem;
}
button.secondary {
  background: #475569;
}
button.danger {
  background: #dc2626;
}
label {
  display: block;
  margin-top: 0.6rem;
  font-size: 0.85rem;
}
input,
textarea,
select {
  width: 100%;
  margin-top: 0.25rem;
  padding: 0.45rem 0.55rem;
  border: 1px solid #cbd5f5;
  border-radius: 5px;
  font-family: inherit;
}
textarea {
  min-height: 70px;
  resize: vertical;
}
"""
    ).strip() + "\n"


    main_dart = main_template.replace("__METADATA_JSON__", metadata_json).strip() + "\n"

    readme_md = textwrap.dedent(
        f"""
        # Frontend web en Dart

        Este directorio contiene un cliente web basico escrito en Dart/HTML para interactuar con los
        endpoints REST expuestos por el backend generado.

        ## Requisitos

        - Dart SDK 3.4 o superior
        - Herramienta `webdev` instalada (`dart pub global activate webdev`)

        ## Ejecucion

        1. Arranca el backend Spring Boot:

           ```bash
           mvn spring-boot:run
           ```

        2. En este directorio instala dependencias y levanta el frontend en un puerto libre (8081):

           ```bash
           dart pub get
           dart pub global run webdev serve web:8081
           ```

        El panel consumira el backend en `http://127.0.0.1:8080/api`. Si tu backend esta en otra URL o puerto, ajusta la constante `kApiBase` en `web/main.dart`.

        Para generar la version compilada para despliegue:

        ```bash
        dart pub global run webdev build
        ```
        """
    ).strip() + "\n"

    gitignore = textwrap.dedent(
        """
        .dart_tool/
        build/
        .packages
        web/main.dart.js
        web/main.dart.js.deps
        web/main.dart.js.map
        """
    ).strip() + "\n"

    return {
        "frontend_dart/pubspec.yaml": pubspec_yaml,
        "frontend_dart/analysis_options.yaml": analysis_options,
        "frontend_dart/web/main.dart": main_dart,
        "frontend_dart/web/index.html": index_html,
        "frontend_dart/web/styles.css": styles_css,
        "frontend_dart/README.md": readme_md,
        "frontend_dart/.gitignore": gitignore,
    }


def generate_spring_boot_zip(project_name: str, graph: dict[str, Any]) -> tuple[str, io.BytesIO]:
    project_slug = slugify(project_name or "generated")
    artifact_id = project_slug
    package_suffix = safe_package_segment(project_slug.replace("-", ""))
    package = f"com.example.{package_suffix}"
    package_path = package.replace('.', '/')
    app_class = pascal_case(project_name or "Generated") + "Application"
    base_dir = f"{project_slug}-spring"

    entities = collect_entity_specs(graph)
    if not entities:
        raise ValueError("El grafo no contiene nodos para exportar.")
    relations = collect_relations(graph)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"{base_dir}/pom.xml",
            pom_xml(package, artifact_id, project_name or "Generated project"),
        )
        zf.writestr(
            f"{base_dir}/src/main/java/{package_path}/{app_class}.java",
            application_class(package, app_class),
        )
        zf.writestr(
            f"{base_dir}/src/main/resources/application.properties",
            application_properties(),
        )
        zf.writestr(
            f"{base_dir}/README.md",
            build_readme(project_name or base_dir, relations),
        )
        dart_files = build_dart_frontend(project_name or base_dir, entities, relations)
        for relative_path, content in dart_files.items():
            zf.writestr(f"{base_dir}/{relative_path}", content)
        for entity in entities:
            zf.writestr(
                f"{base_dir}/src/main/java/{package_path}/domain/{entity.class_name}.java",
                entity_class(package, entity),
            )
            zf.writestr(
                f"{base_dir}/src/main/java/{package_path}/repository/{entity.class_name}Repository.java",
                repository_class(package, entity),
            )
            zf.writestr(
                f"{base_dir}/src/main/java/{package_path}/controller/{entity.class_name}Controller.java",
                controller_class(package, entity),
            )
    buffer.seek(0)
    filename = f"{base_dir}.zip"
    return filename, buffer
