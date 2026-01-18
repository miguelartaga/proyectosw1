import {
    BaseEdge,
    EdgeLabelRenderer,
    getSmoothStepPath,
    type EdgeProps,
} from "@xyflow/react";
import React, { useMemo, useState } from "react";
import type { RelationshipData } from "../types";

const RelationshipEdge: React.FC<EdgeProps<RelationshipData>> = ({
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    style,
    data,
}) => {
    const [isHovered, setIsHovered] = useState(false);
    const relationship = (data ?? {}) as Partial<RelationshipData>;
    const kind = relationship.kind ?? "simple";
    const sourceMult = relationship.sourceMult ?? "";
    const targetMult = relationship.targetMult ?? "";
    const label = relationship.label ?? "";

    const [edgePath, labelX, labelY] = getSmoothStepPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
        offset: 40,
        borderRadius: 24,
    });

    const { markerStartId, markerEndId, strokeDasharray } = useMemo(() => {
        switch (kind) {
            case "flechaBlanca":
                return {
                    markerStartId: undefined,
                    markerEndId: "url(#triangle-white)",
                    strokeDasharray: undefined,
                };
            case "flechaNegra":
                return {
                    markerStartId: undefined,
                    markerEndId: "url(#triangle-black)",
                    strokeDasharray: undefined,
                };
            case "segmentada":
                return {
                    markerStartId: undefined,
                    markerEndId: undefined,
                    strokeDasharray: "6 4",
                };
            default:
                return { markerStartId: undefined, markerEndId: undefined, strokeDasharray: undefined };
        }
    }, [kind]);

    return (
        <>
            <svg style={{ height: 0, width: 0 }}>
                <defs>
                    <marker
                        id="triangle-white"
                        viewBox="0 0 10 10"
                        refX="10"
                        refY="5"
                        markerWidth="12"
                        markerHeight="12"
                        orient="auto-start-reverse"
                    >
                        <path d="M 0 0 L 10 5 L 0 10 Z" fill="white" stroke="black" />
                    </marker>
                    <marker
                        id="triangle-black"
                        viewBox="0 0 10 10"
                        refX="10"
                        refY="5"
                        markerWidth="12"
                        markerHeight="12"
                        orient="auto-start-reverse"
                    >
                        <path d="M 0 0 L 10 5 L 0 10 Z" fill="black" stroke="black" />
                    </marker>
                </defs>
            </svg>

            <BaseEdge
                id={id}
                path={edgePath}
                style={{
                    ...(style ?? {}),
                    stroke: isHovered ? "#2196f3" : "#333333",
                    strokeWidth: isHovered ? 3 : 2,
                    strokeDasharray,
                }}
                markerStart={markerStartId}
                markerEnd={markerEndId}
                onMouseEnter={() => setIsHovered(true)}
                onMouseLeave={() => setIsHovered(false)}
            />

            <EdgeLabelRenderer>
                {sourceMult && (
                    <div
                        style={{
                            position: "absolute",
                            transform: `translate(-50%, -50%) translate(${sourceX}px,${sourceY}px)`,
                            background: "white",
                            border: "1px solid #dddddd",
                            borderRadius: 4,
                            padding: "1px 4px",
                            fontSize: 11,
                            pointerEvents: "none",
                        }}
                    >
                        {sourceMult}
                    </div>
                )}

                {targetMult && (
                    <div
                        style={{
                            position: "absolute",
                            transform: `translate(-50%, -50%) translate(${targetX}px,${targetY}px)`,
                            background: "white",
                            border: "1px solid #dddddd",
                            borderRadius: 4,
                            padding: "1px 4px",
                            fontSize: 11,
                            pointerEvents: "none",
                        }}
                    >
                        {targetMult}
                    </div>
                )}

                {label && (
                    <div
                        style={{
                            position: "absolute",
                            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY - 12}px)`,
                            background: "white",
                            border: "1px solid #dddddd",
                            borderRadius: 4,
                            padding: "2px 6px",
                            fontSize: 11,
                            fontStyle: "italic",
                            pointerEvents: "none",
                        }}
                    >
                        {label}
                    </div>
                )}

                <div
                    style={{
                        position: "absolute",
                        transform: `translate(-50%, -50%) translate(${labelX + 20}px,${labelY + 12}px)`,
                        background: "transparent",
                        pointerEvents: "all",
                        zIndex: 10,
                    }}
                >
                    <button
                        type="button"
                        onClick={(event) => {
                            event.stopPropagation();
                            window.dispatchEvent(
                                new CustomEvent("edit-relationship", {
                                    detail: { edgeId: id },
                                })
                            );
                        }}
                        style={{
                            background: "white",
                            border: "1px solid #cccccc",
                            borderRadius: 4,
                            padding: "0 6px",
                            marginRight: 6,
                            fontSize: 10,
                            cursor: "pointer",
                            color: "#333333",
                            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
                        }}
                        title="Editar relacion"
                    >
                        Editar
                    </button>
                    <button
                        type="button"
                        onClick={(event) => {
                            event.stopPropagation();
                            window.dispatchEvent(
                                new CustomEvent("delete-relationship", {
                                    detail: { edgeId: id },
                                })
                            );
                        }}
                        style={{
                            background: "white",
                            border: "1px solid #cccccc",
                            borderRadius: "50%",
                            width: 18,
                            height: 18,
                            fontSize: 10,
                            cursor: "pointer",
                            color: "#c62828",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
                        }}
                        title="Eliminar relacion"
                    >
                        X
                    </button>
                </div>
            </EdgeLabelRenderer>
        </>
    );
};

export default RelationshipEdge;
