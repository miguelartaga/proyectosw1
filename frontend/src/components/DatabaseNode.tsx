import { Handle, Position, type NodeProps } from "@xyflow/react";
import React, { useState } from "react";
import type { DatabaseNodeData } from "../types";

type DatabaseNodeProps = NodeProps & {
    data: DatabaseNodeData;
    onEdit?: (nodeId: string) => void;
    onDelete?: (nodeId: string) => void;
};

const iconButtonStyle: React.CSSProperties = {
    width: 24,
    height: 24,
    borderRadius: "50%",
    color: "white",
    border: "none",
    cursor: "pointer",
    fontSize: 11,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
};

function DatabaseNode({ data, id, onEdit, onDelete }: DatabaseNodeProps) {
    const [isHovered, setIsHovered] = useState(false);

    const nodeId = String(id);
    const isJoin = Boolean(data.isJoin);

    const handleEdit = (event: React.MouseEvent<HTMLButtonElement>) => {
        event.stopPropagation();
        onEdit?.(nodeId);
    };

    const handleDelete = (event: React.MouseEvent<HTMLButtonElement>) => {
        event.stopPropagation();
        onDelete?.(nodeId);
    };

    const containerStyle: React.CSSProperties = {
        border: "1px solid #222222",
        borderRadius: 6,
        padding: 6,
        background: "white",
        minWidth: 180,
        boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        position: "relative",
    };

    if (isJoin) {
        containerStyle.minWidth = 220;
        containerStyle.paddingTop = 18;
        containerStyle.background = "#f5f8ff";
        containerStyle.border = "1px solid #3f51b5";
    }

    return (
        <div
            style={containerStyle}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            {isJoin && (
                <div
                    style={{
                        position: "absolute",
                        top: -12,
                        left: -12,
                        right: -12,
                        height: 10,
                        background: "#3f51b5",
                        borderRadius: 6,
                    }}
                />
            )}

            {isHovered && (
                <div
                    style={{
                        position: "absolute",
                        top: -8,
                        right: -8,
                        display: "flex",
                        gap: 6,
                    }}
                >
                    <button
                        type="button"
                        onClick={handleEdit}
                        style={{ ...iconButtonStyle, background: "#2196f3" }}
                        title="Editar tabla"
                    >
                        Edit
                    </button>
                    <button
                        type="button"
                        onClick={handleDelete}
                        style={{ ...iconButtonStyle, background: "#f44336" }}
                        title="Eliminar tabla"
                    >
                        Del
                    </button>
                </div>
            )}

            <div
                style={{
                    fontWeight: "bold",
                    marginBottom: 8,
                    padding: "4px 8px",
                    background: isJoin ? "#e8ecff" : "#f0f0f0",
                    borderRadius: 4,
                    fontSize: 14,
                    textAlign: "center",
                }}
            >
                {isJoin && data.joinOf ? `${data.joinOf[0]} / ${data.joinOf[1]}` : data.label || "Tabla"}
            </div>

            <div style={{ padding: "0 4px" }}>
                {data.columns.map((column) => (
                    <div
                        key={column.id}
                        style={{
                            fontSize: 12,
                            marginBottom: 4,
                            padding: "2px 4px",
                            background: column.pk ? "#e3f2fd" : "transparent",
                            borderRadius: 2,
                            borderLeft: column.pk ? "3px solid #2196f3" : "none",
                            textAlign: isJoin ? "center" : "left",
                        }}
                    >
                        <span style={{ fontWeight: column.pk ? "bold" : "normal" }}>
                            {column.pk ? "PK " : ""}
                            {column.name}
                        </span>
                        <span style={{ color: "#666666", marginLeft: 8 }}>{column.type}</span>
                        {column.nullable === false && (
                            <span style={{ color: "#f44336", marginLeft: 4 }}>*</span>
                        )}
                    </div>
                ))}
            </div>

            <Handle type="target" position={Position.Top} />
            <Handle type="source" position={Position.Bottom} />
        </div>
    );
}

export default DatabaseNode;

