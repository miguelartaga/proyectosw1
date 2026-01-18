import {

    Background,

    Controls,

    MiniMap,

    ReactFlow,

    applyEdgeChanges,

    applyNodeChanges,

    type Connection,

    type EdgeChange,

    type EdgeProps,

    type EdgeTypes,

    type NodeChange,

    type NodeProps,

    type NodeTypes,

} from "@xyflow/react";

import React, { useCallback, useEffect, useMemo, useState } from "react";



import "@xyflow/react/dist/style.css";

import { useDiagramStore } from "../store/diagramStore";
import { api } from "../api";

import type {

    Column,

    DatabaseNodeData,

    DiagramEdge,

    DiagramGraph,

    DiagramNode,

    Multiplicity,

    RelationshipData,

    RelationshipKind,

} from "../types";

import DatabaseNode from "./DatabaseNode";

import RelationshipEdge from "./RelationshipEdge";

import RelationshipEditor from "./RelationshipEditor";

import TableEditor from "./TableEditor";



type RelationshipEvent = CustomEvent<{ edgeId: string }>;



const SAMPLE_NODES: DiagramNode[] = [

    {

        id: "node-pacientes",

        type: "databaseNode",

        position: { x: 80, y: 160 },

        data: {

            label: "Pacientes",

            columns: [

                { id: "pac-id", name: "id", type: "INT", pk: true, nullable: false },

                { id: "pac-nombre", name: "nombre", type: "VARCHAR(150)", nullable: false },

                { id: "pac-fecha", name: "fecha_nacimiento", type: "DATE", nullable: false },

                { id: "pac-telefono", name: "telefono", type: "VARCHAR(40)", nullable: true },

            ],

        },

    },

    {

        id: "node-doctores",

        type: "databaseNode",

        position: { x: 420, y: 80 },

        data: {

            label: "Doctores",

            columns: [

                { id: "doc-id", name: "id", type: "INT", pk: true, nullable: false },

                { id: "doc-nombre", name: "nombre", type: "VARCHAR(150)", nullable: false },

                { id: "doc-especialidad", name: "especialidad", type: "VARCHAR(120)", nullable: false },

                { id: "doc-telefono", name: "telefono", type: "VARCHAR(40)", nullable: true },

            ],

        },

    },

    {

        id: "node-citas",

        type: "databaseNode",

        position: { x: 420, y: 260 },

        data: {

            label: "Citas",

            columns: [

                { id: "cit-id", name: "id", type: "INT", pk: true, nullable: false },

                { id: "cit-paciente", name: "paciente_id", type: "INT", nullable: false },

                { id: "cit-doctor", name: "doctor_id", type: "INT", nullable: false },

                { id: "cit-fecha", name: "fecha", type: "DATETIME", nullable: false },

                { id: "cit-motivo", name: "motivo", type: "VARCHAR(200)", nullable: true },

            ],

        },

    },

    {

        id: "node-historial",

        type: "databaseNode",

        position: { x: 760, y: 220 },

        data: {

            label: "HistorialMedico",

            columns: [

                { id: "hist-id", name: "id", type: "INT", pk: true, nullable: false },

                { id: "hist-cita", name: "cita_id", type: "INT", nullable: false },

                { id: "hist-diagnostico", name: "diagnostico", type: "TEXT", nullable: false },

                { id: "hist-tratamiento", name: "tratamiento", type: "TEXT", nullable: true },

            ],

        },

    },

];



const SAMPLE_EDGES: DiagramEdge[] = [

    {

        id: "edge-pacientes-citas",

        source: "node-pacientes",

        target: "node-citas",

        label: "Paciente agenda Cita",

        data: {

            id: "edge-pacientes-citas",

            source: "node-pacientes",

            target: "node-citas",

            kind: "simple",

            sourceMult: "1",

            targetMult: "*",

            label: "Paciente agenda Cita",

        },

    },

    {

        id: "edge-doctores-citas",

        source: "node-doctores",

        target: "node-citas",

        label: "Doctor atiende Citas",

        data: {

            id: "edge-doctores-citas",

            source: "node-doctores",

            target: "node-citas",

            kind: "simple",

            sourceMult: "1",

            targetMult: "*",

            label: "Doctor atiende Citas",

        },

    },

    {

        id: "edge-citas-historial",

        source: "node-citas",

        target: "node-historial",

        label: "Cita genera Historial",

        data: {

            id: "edge-citas-historial",

            source: "node-citas",

            target: "node-historial",

            kind: "simple",

            sourceMult: "1",

            targetMult: "1",

            label: "Cita genera Historial",

        },

    },

];

const buildSampleGraph = (): DiagramGraph => ({

    nodes: SAMPLE_NODES.map((node) => ({

        ...node,

        position: { ...node.position },

        data: {

            ...node.data,

            columns: node.data.columns.map((column) => ({ ...column })),

        },

    })),

    edges: SAMPLE_EDGES.map((edge) => ({

        ...edge,

        data: edge.data ? { ...edge.data } : undefined,

    })),

});



const slugifyName = (value: string): string => {
    return value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
};

const DiagramCanvas: React.FC = () => {

    const {

        nodes,

        edges,

        setGraph,

        resetGraph,

        addNodes,

        addEdges,

        setNodes,

        setEdges,

        updateNodeData,

        removeNode,

        removeEdge,

        updateEdge,

        updateEdgeData,

        selectedRelationshipKind,

        selectedSourceMult,

        selectedTargetMult,

        setSelectedRelationshipKind,

        setSelectedSourceMult,

        setSelectedTargetMult,

    } = useDiagramStore();



    const [editingNode, setEditingNode] = useState<DiagramNode | null>(null);

    const [isEditorOpen, setIsEditorOpen] = useState(false);

    const [editingEdge, setEditingEdge] = useState<DiagramEdge | null>(null);

    const [isRelationshipEditorOpen, setIsRelationshipEditorOpen] = useState(false);
    const [isExportingSpring, setIsExportingSpring] = useState(false);



    const isEmpty = nodes.length === 0 && edges.length === 0;

    const handleLoadSample = useCallback(() => {
        setGraph(buildSampleGraph());
        setEditingNode(null);
        setIsEditorOpen(false);
        setEditingEdge(null);
        setIsRelationshipEditorOpen(false);
    }, [setGraph]);

    const handleClearDiagram = useCallback(() => {
        resetGraph();
        setEditingNode(null);
        setIsEditorOpen(false);
        setEditingEdge(null);
        setIsRelationshipEditorOpen(false);
    }, [resetGraph]);


    const handleExportSpringBoot = useCallback(async () => {
        if (nodes.length === 0) {
            window.alert("Necesitas al menos una tabla para exportar el backend.");
            return;
        }
        const defaultName = nodes[0]?.data?.label ?? "generated-backend";
        const projectName = typeof window !== "undefined"
            ? window.prompt("Nombre del proyecto Spring Boot", defaultName)
            : defaultName;
        const trimmed = (projectName ?? "").trim();
        if (!trimmed) {
            return;
        }

        setIsExportingSpring(true);
        const payload = {
            name: trimmed,
            graph: {
                nodes,
                edges,
            },
        };

        try {
            const response = await api.post<Blob>(
                "/diagrams/export/spring",
                payload,
                { responseType: "blob" }
            );
            const blob = new Blob([response.data], { type: "application/zip" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            const downloadName = slugifyName(trimmed) || "spring-export";
            link.download = `${downloadName}.zip`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error("Error exporting Spring Boot project", error);
            window.alert("No se pudo generar el proyecto Spring Boot.");
        } finally {
            setIsExportingSpring(false);
        }
    }, [edges, nodes]);



    useEffect(() => {

        const handleEditRelationship = (event: Event) => {

            const detail = (event as RelationshipEvent).detail;

            if (!detail) {

                return;

            }



            const edge = edges.find((item) => item.id === detail.edgeId);

            if (edge) {

                setEditingEdge(edge);

                setIsRelationshipEditorOpen(true);

            }

        };



        const handleDeleteRelationship = (event: Event) => {

            const detail = (event as RelationshipEvent).detail;

            if (detail) {

                removeEdge(detail.edgeId);

            }

        };



        window.addEventListener("edit-relationship", handleEditRelationship as EventListener);

        window.addEventListener(

            "delete-relationship",

            handleDeleteRelationship as EventListener

        );



        return () => {

            window.removeEventListener(

                "edit-relationship",

                handleEditRelationship as EventListener

            );

            window.removeEventListener(

                "delete-relationship",

                handleDeleteRelationship as EventListener

            );

        };

    }, [edges, removeEdge]);



    const handleEditNode = useCallback((nodeId: string) => {

        const node = nodes.find((item) => item.id === nodeId) ?? null;

        setEditingNode(node);

        setIsEditorOpen(Boolean(node));

    }, [nodes]);



    const handleDeleteNode = useCallback(

        (nodeId: string) => {

            removeNode(nodeId);

            if (editingNode?.id === nodeId) {

                setEditingNode(null);

                setIsEditorOpen(false);

            }

        },

        [editingNode?.id, removeNode]

    );



    const handleSaveTable = useCallback(

        (tableName: string, columns: Column[]) => {

            if (!editingNode) {

                return;

            }



            const payload: DatabaseNodeData = {

                label: tableName,

                columns,

            };



            const exists = nodes.some((node) => node.id === editingNode.id);

            if (exists) {

                updateNodeData(editingNode.id, payload);

            } else {

                addNodes([

                    {

                        ...editingNode,

                        data: payload,

                    },

                ]);

            }



            setIsEditorOpen(false);

            setEditingNode(null);

        },

        [addNodes, editingNode, nodes, updateNodeData]

    );



    const handleCloseEditor = useCallback(() => {

        setIsEditorOpen(false);

        setEditingNode(null);

    }, []);



    const handleCreateNewTable = useCallback(() => {

        const id = `node-${Date.now()}`;

        const newNode: DiagramNode = {

            id,

            type: "databaseNode",

            position: {

                x: 120 + Math.random() * 320,

                y: 120 + Math.random() * 220,

            },

            data: {

                label: "NuevaTabla",

                columns: [

                    { id: `${id}-id`, name: "id", type: "INT", pk: true, nullable: false },

                ],

            },

        };



        setEditingNode(newNode);

        setIsEditorOpen(true);

    }, []);



    const handleSaveRelationship = useCallback(

        (relationship: RelationshipData) => {

            updateEdge(relationship.id, {

                label: relationship.label ?? "",

            });

            updateEdgeData(relationship.id, {

                kind: relationship.kind,

                sourceMult: relationship.sourceMult,

                targetMult: relationship.targetMult,

                label: relationship.label ?? "",

            });



            setIsRelationshipEditorOpen(false);

            setEditingEdge(null);

        },

        [updateEdge, updateEdgeData]

    );



    const handleCloseRelationshipEditor = useCallback(() => {

        setIsRelationshipEditorOpen(false);

        setEditingEdge(null);

    }, []);



    const onNodesChange = useCallback(

        (changes: NodeChange<DiagramNode>[]) => {

            setNodes(applyNodeChanges(changes, nodes));

        },

        [nodes, setNodes]

    );



    const onEdgesChange = useCallback(

        (changes: EdgeChange<DiagramEdge>[]) => {

            setEdges(applyEdgeChanges(changes, edges));

        },

        [edges, setEdges]

    );



    const onConnect = useCallback(

        (connection: Connection) => {

            if (!connection.source || !connection.target) {

                return;

            }



            const isManyToMany =

                selectedRelationshipKind === "segmentada" &&

                selectedSourceMult === "*" &&

                selectedTargetMult === "*";



            if (isManyToMany) {

                const sourceNode = nodes.find((node) => node.id === connection.source);

                const targetNode = nodes.find((node) => node.id === connection.target);



                const sourceLabel = sourceNode?.data.label ?? connection.source;

                const targetLabel = targetNode?.data.label ?? connection.target;



                const toIdentifier = (value: string) =>

                    value

                        .trim()

                        .toLowerCase()

                        .replace(/\s+/g, "_")

                        .replace(/[^a-z0-9_]/g, "") || "relacion";



                const joinId = `join-${connection.source}-${connection.target}-${Date.now()}`;

                const joinLabel = `${sourceLabel}_${targetLabel}`;



                const sourcePosition = sourceNode?.position ?? { x: 100, y: 100 };

                const targetPosition = targetNode?.position ?? { x: sourcePosition.x + 200, y: sourcePosition.y };

                const joinPosition = {

                    x: (sourcePosition.x + targetPosition.x) / 2,

                    y: Math.max(sourcePosition.y, targetPosition.y) + 200,

                };



                const joinColumns: Column[] = [

                    { id: `${joinId}-id`, name: "id", type: "INT", pk: true, nullable: false },

                    {

                        id: `${joinId}-${connection.source}`,

                        name: `${toIdentifier(sourceLabel)}_id`,

                        type: "INT",

                        nullable: false,

                    },

                    {

                        id: `${joinId}-${connection.target}`,

                        name: `${toIdentifier(targetLabel)}_id`,

                        type: "INT",

                        nullable: false,

                    },

                ];



                addNodes([

                    {

                        id: joinId,

                        type: "databaseNode",

                        position: joinPosition,

                        data: {

                            label: joinLabel,

                            columns: joinColumns,

                            isJoin: true,

                            joinOf: [sourceLabel, targetLabel],

                        },

                    },

                ]);



                const timestamp = Date.now();

                const leftEdgeId = `edge-${connection.source}-${joinId}-${timestamp}`;

                const rightEdgeId = `edge-${joinId}-${connection.target}-${timestamp}`;



                addEdges([

                    {

                        id: leftEdgeId,

                        source: connection.source,

                        target: joinId,

                        label: "",

                        data: {

                            id: leftEdgeId,

                            source: connection.source,

                            target: joinId,

                            kind: "simple",

                            sourceMult: selectedSourceMult,

                            targetMult: "1",

                            label: "",

                        },

                    },

                    {

                        id: rightEdgeId,

                        source: joinId,

                        target: connection.target,

                        label: "",

                        data: {

                            id: rightEdgeId,

                            source: joinId,

                            target: connection.target,

                            kind: "simple",

                            sourceMult: "1",

                            targetMult: selectedTargetMult,

                            label: "",

                        },

                    },

                ]);



                return;

            }



            const id = `edge-${connection.source}-${connection.target}-${Date.now()}`;

            const newEdge: DiagramEdge = {

                id,

                source: connection.source,

                target: connection.target,

                sourceHandle: connection.sourceHandle,

                targetHandle: connection.targetHandle,

                label: "",

                data: {

                    id,

                    source: connection.source,

                    target: connection.target,

                    kind: selectedRelationshipKind,

                    sourceMult: selectedSourceMult,

                    targetMult: selectedTargetMult,

                    label: "",

                },

            };



            addEdges([newEdge]);

        },

        [

            addEdges,

            addNodes,

            nodes,

            selectedRelationshipKind,

            selectedSourceMult,

            selectedTargetMult,

        ]

    );



    const nodeTypes = useMemo<NodeTypes>(

        () => ({

            databaseNode: (props) => {

                const casted = props as NodeProps & { data: DatabaseNodeData };

                return (

                    <DatabaseNode

                        {...casted}

                        data={casted.data}

                        onEdit={handleEditNode}

                        onDelete={handleDeleteNode}

                    />

                );

            },

        }),

        [handleDeleteNode, handleEditNode]

    );



    const edgeTypes = useMemo<EdgeTypes>(

        () => ({

            default: (props) => {

                const casted = props as EdgeProps<RelationshipData>;

                return <RelationshipEdge {...casted} />;

            },

        }),

        []

    );



    type RelationshipKindOption = {

        value: RelationshipKind;

        icon: React.ReactElement;

    };



    const relationshipKinds = useMemo<RelationshipKindOption[]>(

        () => [

            {

                value: "simple",

                icon: (

                    <svg width="40" height="20">

                        <line x1="2" y1="10" x2="38" y2="10" stroke="black" strokeWidth="2" />

                    </svg>

                ),

            },

            {

                value: "flechaBlanca",

                icon: (

                    <svg width="40" height="20">

                        <line x1="2" y1="10" x2="30" y2="10" stroke="black" strokeWidth="2" />

                        <polygon points="30,5 38,10 30,15" fill="white" stroke="black" />

                    </svg>

                ),

            },

            {

                value: "flechaNegra",

                icon: (

                    <svg width="40" height="20">

                        <line x1="2" y1="10" x2="30" y2="10" stroke="black" strokeWidth="2" />

                        <polygon points="30,5 38,10 30,15" fill="black" stroke="black" />

                    </svg>

                ),

            },

            {

                value: "segmentada",

                icon: (

                    <svg width="40" height="20">

                        <line

                            x1="2"

                            y1="10"

                            x2="38"

                            y2="10"

                            stroke="black"

                            strokeWidth="2"

                            strokeDasharray="6 4"

                        />

                    </svg>

                ),

            },

        ],

        []

    );



    const multiplicities = useMemo<ReadonlyArray<Multiplicity>>(

        () => ["1", "0..1", "*", "1..*", "0..*"],

        []

    );



    return (

        <div style={{ height: "100vh", width: "100%", position: "relative" }}>

            <ReactFlow

                nodes={nodes}

                edges={edges}

                nodeTypes={nodeTypes}

                edgeTypes={edgeTypes}

                onNodesChange={onNodesChange}

                onEdgesChange={onEdgesChange}

                onConnect={onConnect}

                fitView

                deleteKeyCode="Delete"

            >

                <Background />

                <MiniMap />

                <Controls />

            </ReactFlow>



            <div
                style={{
                    position: "absolute",
                    top: 20,
                    right: 20,
                    display: "flex",
                    gap: 12,
                    zIndex: 100,
                }}
            >
                <button
                    type="button"
                    onClick={handleCreateNewTable}
                    style={{
                        padding: "12px 16px",
                        background: "#4caf50",
                        color: "white",
                        border: "none",
                        borderRadius: 8,
                        cursor: "pointer",
                        fontSize: 14,
                        fontWeight: 600,
                        boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
                    }}
                >
                    + Nueva tabla
                </button>
                <button
                    type="button"
                    onClick={handleLoadSample}
                    style={{
                        padding: "12px 16px",
                        background: "#2196f3",
                        color: "white",
                        border: "none",
                        borderRadius: 8,
                        cursor: "pointer",
                        fontSize: 14,
                        fontWeight: 500,
                        boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
                    }}
                >
                    Cargar ejemplo
                </button>
                <button
                    type="button"
                    onClick={handleExportSpringBoot}
                    disabled={isExportingSpring || isEmpty}
                    style={{
                        padding: "12px 16px",
                        background: isExportingSpring ? "#b39ddb" : "#673ab7",
                        color: "white",
                        border: "none",
                        borderRadius: 8,
                        cursor: isExportingSpring || isEmpty ? "not-allowed" : "pointer",
                        fontSize: 14,
                        fontWeight: 500,
                        boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
                        opacity: isExportingSpring ? 0.8 : 1,
                    }}
                >
                    {isExportingSpring ? "Exportando..." : "Exportar Spring Boot"}
                </button>
                <button
                    type="button"
                    onClick={handleClearDiagram}
                    disabled={isEmpty}
                    style={{
                        padding: "12px 16px",
                        background: isEmpty ? "#f0f0f0" : "#ffffff",
                        color: isEmpty ? "#888888" : "#333333",
                        border: "1px solid #cccccc",
                        borderRadius: 8,
                        cursor: isEmpty ? "not-allowed" : "pointer",
                        fontSize: 14,
                        fontWeight: 500,
                        boxShadow: "0 1px 4px rgba(0,0,0,0.1)",
                    }}
                >
                    Lienzo vacio
                </button>
            </div>



            <div

                style={{

                    position: "absolute",

                    top: 80,

                    right: 20,

                    background: "white",

                    border: "1px solid #dddddd",

                    borderRadius: 8,

                    padding: 10,

                    display: "flex",

                    flexDirection: "column",

                    gap: 10,

                    zIndex: 200,

                    boxShadow: "0 2px 6px rgba(0,0,0,0.15)",

                    minWidth: 260,

                }}

            >

                <div

                    style={{

                        display: "grid",

                        gridTemplateColumns: "repeat(4, 1fr)",

                        gap: 6,

                    }}

                >

                    {relationshipKinds.map(({ value, icon }) => (

                        <button

                            key={value}

                            type="button"

                            onClick={() => setSelectedRelationshipKind(value)}

                            style={{

                                background:

                                    selectedRelationshipKind === value ? "#2196f3" : "#eeeeee",

                                border: "none",

                                borderRadius: 6,

                                padding: 4,

                                cursor: "pointer",

                            }}

                            title={value}

                        >

                            {icon}

                        </button>

                    ))}

                </div>



                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>

                    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>

                        Source mult

                        <select

                            value={selectedSourceMult}

                            onChange={(event) =>

                                setSelectedSourceMult(event.target.value as Multiplicity)

                            }

                            style={{

                                padding: 6,

                                borderRadius: 6,

                                border: "none",

                                fontSize: 12,

                            }}

                        >

                            {multiplicities.map((option) => (

                                <option key={option} value={option}>

                                    {option}

                                </option>

                            ))}

                        </select>

                    </label>

                    <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>

                        Target mult

                        <select

                            value={selectedTargetMult}

                            onChange={(event) =>

                                setSelectedTargetMult(event.target.value as Multiplicity)

                            }

                            style={{

                                padding: 6,

                                borderRadius: 6,

                                border: "none",

                                fontSize: 12,

                            }}

                        >

                            {multiplicities.map((option) => (

                                <option key={option} value={option}>

                                    {option}

                                </option>

                            ))}

                        </select>

                    </label>

                </div>

            </div>



            {editingNode && (

                <TableEditor

                    isOpen={isEditorOpen}

                    onClose={handleCloseEditor}

                    tableName={editingNode.data.label}

                    columns={editingNode.data.columns}

                    onSave={handleSaveTable}

                />

            )}



            {editingEdge && (

                <RelationshipEditor

                    isOpen={isRelationshipEditorOpen}

                    onClose={handleCloseRelationshipEditor}

                    relationship={{

                        id: editingEdge.id,

                        source: editingEdge.source,

                        target: editingEdge.target,

                        kind: editingEdge.data?.kind ?? "simple",

                        sourceMult: editingEdge.data?.sourceMult ?? "1",

                        targetMult: editingEdge.data?.targetMult ?? "*",

                        label: (() => {

                            const rawLabel = editingEdge.data?.label ?? editingEdge.label ?? "";

                            return typeof rawLabel === "string" ? rawLabel : String(rawLabel);

                        })(),

                    }}

                    sourceTableName={

                        nodes.find((node) => node.id === editingEdge.source)?.data.label ||

                        "Tabla origen"

                    }

                    targetTableName={

                        nodes.find((node) => node.id === editingEdge.target)?.data.label ||

                        "Tabla destino"

                    }

                    onSave={handleSaveRelationship}

                />

            )}

        </div>

    );

};



export default DiagramCanvas;



































