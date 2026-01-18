import React, { useEffect, useMemo, useState } from "react";
import type { Column } from "../types";

interface TableEditorProps {
    isOpen: boolean;
    onClose: () => void;
    tableName: string;
    columns: Column[];
    onSave: (tableName: string, columns: Column[]) => void;
}

const DATA_TYPES = [
    "INT",
    "BIGINT",
    "VARCHAR(255)",
    "VARCHAR(100)",
    "TEXT",
    "DATE",
    "DATETIME",
    "BOOLEAN",
    "DECIMAL(10,2)",
];

const TableEditor: React.FC<TableEditorProps> = ({
    isOpen,
    onClose,
    tableName: initialTableName,
    columns: initialColumns,
    onSave,
}) => {
    const [tableName, setTableName] = useState(initialTableName);
    const [columns, setColumns] = useState<Column[]>(initialColumns);

    useEffect(() => {
        setTableName(initialTableName);
        setColumns(initialColumns);
    }, [initialColumns, initialTableName]);

    const handleAddColumn = () => {
        const newColumn: Column = {
            id: `column-${Date.now()}`,
            name: `col_${columns.length + 1}`,
            type: "VARCHAR(255)",
            pk: false,
            nullable: true,
        };
        setColumns((current) => [...current, newColumn]);
    };

    const handleRemoveColumn = (columnId: string) => {
        setColumns((current) => current.filter((column) => column.id !== columnId));
    };

    const handleUpdateColumn = (columnId: string, updates: Partial<Column>) => {
        setColumns((current) =>
            current.map((column) => (column.id === columnId ? { ...column, ...updates } : column))
        );
    };

    const handleSave = () => {
        onSave(tableName.trim() || "Tabla", columns);
        onClose();
    };

    const hasPrimaryKey = useMemo(() => columns.some((column) => column.pk), [columns]);

    if (!isOpen) {
        return null;
    }

    return (
        <div
            style={{
                position: "fixed",
                inset: 0,
                background: "rgba(0,0,0,0.5)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 1000,
            }}
        >
            <div
                style={{
                    background: "white",
                    padding: "2rem",
                    borderRadius: 8,
                    width: 600,
                    maxHeight: "80vh",
                    overflow: "auto",
                    boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
                }}
            >
                <h2 style={{ margin: "0 0 1rem", color: "#333333" }}>Editar tabla</h2>

                <div style={{ marginBottom: "1.5rem" }}>
                    <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: 500 }}>
                        Nombre de la tabla
                    </label>
                    <input
                        type="text"
                        value={tableName}
                        onChange={(event) => setTableName(event.target.value)}
                        style={{
                            width: "100%",
                            padding: "0.75rem",
                            border: "1px solid #dddddd",
                            borderRadius: 4,
                            fontSize: 16,
                        }}
                        placeholder="Nombre de la tabla"
                    />
                </div>

                <div style={{ marginBottom: "1.5rem" }}>
                    <div
                        style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: "1rem",
                        }}
                    >
                        <h3 style={{ margin: 0, color: "#333333" }}>Columnas</h3>
                        <button
                            type="button"
                            onClick={handleAddColumn}
                            style={{
                                padding: "0.5rem 1rem",
                                background: "#2196f3",
                                color: "white",
                                border: "none",
                                borderRadius: 4,
                                cursor: "pointer",
                                fontSize: 14,
                            }}
                        >
                            + Agregar columna
                        </button>
                    </div>

                    <div style={{ maxHeight: 300, overflow: "auto" }}>
                        {columns.map((column) => (
                            <div
                                key={column.id}
                                style={{
                                    display: "flex",
                                    gap: "0.5rem",
                                    alignItems: "center",
                                    padding: "0.75rem",
                                    border: "1px solid #eeeeee",
                                    borderRadius: 4,
                                    marginBottom: "0.5rem",
                                    background: "#f9f9f9",
                                }}
                            >
                                <input
                                    type="text"
                                    value={column.name}
                                    onChange={(event) =>
                                        handleUpdateColumn(column.id, { name: event.target.value })
                                    }
                                    style={{
                                        flex: 1,
                                        padding: "0.5rem",
                                        border: "1px solid #dddddd",
                                        borderRadius: 4,
                                        fontSize: 14,
                                    }}
                                    placeholder="Nombre del atributo"
                                />

                                <select
                                    value={column.type}
                                    onChange={(event) =>
                                        handleUpdateColumn(column.id, { type: event.target.value })
                                    }
                                    style={{
                                        padding: "0.5rem",
                                        border: "1px solid #dddddd",
                                        borderRadius: 4,
                                        fontSize: 14,
                                        minWidth: 140,
                                    }}
                                >
                                    {DATA_TYPES.map((type) => (
                                        <option key={type} value={type}>
                                            {type}
                                        </option>
                                    ))}
                                </select>

                                <label
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "0.25rem",
                                        fontSize: 12,
                                    }}
                                >
                                    <input
                                        type="checkbox"
                                        checked={Boolean(column.pk)}
                                        onChange={(event) =>
                                            handleUpdateColumn(column.id, { pk: event.target.checked })
                                        }
                                    />
                                    PK
                                </label>

                                <label
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "0.25rem",
                                        fontSize: 12,
                                    }}
                                >
                                    <input
                                        type="checkbox"
                                        checked={column.nullable !== false}
                                        onChange={(event) =>
                                            handleUpdateColumn(column.id, {
                                                nullable: event.target.checked,
                                            })
                                        }
                                    />
                                    Null
                                </label>

                                <button
                                    type="button"
                                    onClick={() => handleRemoveColumn(column.id)}
                                    style={{
                                        padding: "0.5rem",
                                        background: "#f44336",
                                        color: "white",
                                        border: "none",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                        fontSize: 12,
                                    }}
                                >
                                    Eliminar
                                </button>
                            </div>
                        ))}
                    </div>

                    {!hasPrimaryKey && (
                        <div
                            style={{
                                marginTop: "0.75rem",
                                fontSize: 12,
                                color: "#c62828",
                            }}
                        >
                            Define al menos una columna como PK para evitar problemas de integridad.
                        </div>
                    )}
                </div>

                <div style={{ display: "flex", gap: "1rem", justifyContent: "flex-end" }}>
                    <button
                        type="button"
                        onClick={onClose}
                        style={{
                            padding: "0.75rem 1.5rem",
                            background: "#cccccc",
                            color: "#333333",
                            border: "none",
                            borderRadius: 4,
                            cursor: "pointer",
                            fontSize: 14,
                        }}
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        onClick={handleSave}
                        style={{
                            padding: "0.75rem 1.5rem",
                            background: "#4caf50",
                            color: "white",
                            border: "none",
                            borderRadius: 4,
                            cursor: "pointer",
                            fontSize: 14,
                        }}
                    >
                        Guardar
                    </button>
                </div>
            </div>
        </div>
    );
};

export default TableEditor;

