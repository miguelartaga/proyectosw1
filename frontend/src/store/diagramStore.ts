import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
    DatabaseNodeData,
    DiagramEdge,
    DiagramGraph,
    DiagramNode,
    Multiplicity,
    RelationshipData,
    RelationshipKind,
} from "../types";

interface DiagramState {
    nodes: DiagramNode[];
    edges: DiagramEdge[];

    setGraph: (graph: DiagramGraph) => void;
    resetGraph: () => void;

    setNodes: (nodes: DiagramNode[]) => void;
    setEdges: (edges: DiagramEdge[]) => void;
    addNodes: (nodes: DiagramNode[]) => void;
    addEdges: (edges: DiagramEdge[]) => void;

    updateNode: (nodeId: string, updates: Partial<DiagramNode>) => void;
    updateNodeData: (nodeId: string, data: DatabaseNodeData) => void;
    removeNode: (nodeId: string) => void;

    updateEdge: (edgeId: string, updates: Partial<DiagramEdge>) => void;
    updateEdgeData: (edgeId: string, data: Partial<RelationshipData>) => void;
    removeEdge: (edgeId: string) => void;

    selectedRelationshipKind: RelationshipKind;
    selectedSourceMult: Multiplicity;
    selectedTargetMult: Multiplicity;
    setSelectedRelationshipKind: (kind: RelationshipKind) => void;
    setSelectedSourceMult: (mult: Multiplicity) => void;
    setSelectedTargetMult: (mult: Multiplicity) => void;
}

const STORAGE_VERSION = 1;

const KIND_FALLBACK: RelationshipKind = "simple";

const isRelationshipKind = (value: unknown): value is RelationshipKind =>
    value === "simple" || value === "flechaBlanca" || value === "flechaNegra" || value === "segmentada";

const normalizeEdge = (edge: DiagramEdge): DiagramEdge => {
    const data = edge.data ?? ({} as RelationshipData);
    const kind = isRelationshipKind(data.kind) ? data.kind : KIND_FALLBACK;
    return {
        ...edge,
        data: {
            ...data,
            id: data.id ?? edge.id,
            source: data.source ?? edge.source,
            target: data.target ?? edge.target,
            kind,
            sourceMult: data.sourceMult ?? "1",
            targetMult: data.targetMult ?? "*",
            label: data.label ?? "",
        },
    };
};

export const useDiagramStore = create<DiagramState>()(
    persist(
        (set, _get) => ({
            nodes: [],
            edges: [],

            setGraph: (graph) =>
                set({
                    nodes: graph.nodes,
                    edges: graph.edges.map(normalizeEdge),
                }),
            resetGraph: () => set({ nodes: [], edges: [] }),

            setNodes: (nodes) => set({ nodes }),
            setEdges: (edges) => set({ edges: edges.map(normalizeEdge) }),

            addNodes: (incoming) =>
                set((state) => {
                    const next = new Map<string, DiagramNode>();
                    for (const node of state.nodes) {
                        next.set(node.id, node);
                    }
                    for (const node of incoming) {
                        next.set(node.id, { ...next.get(node.id), ...node });
                    }
                    return { nodes: Array.from(next.values()) };
                }),

            addEdges: (incoming) =>
                set((state) => {
                    const next = new Map<string, DiagramEdge>();
                    for (const edge of state.edges) {
                        next.set(edge.id, edge);
                    }
                    for (const edge of incoming) {
                        const existing = next.get(edge.id);
                        next.set(edge.id, existing ? { ...existing, ...edge } : edge);
                    }
                    return { edges: Array.from(next.values()).map(normalizeEdge) };
                }),

            updateNode: (nodeId, updates) =>
                set((state) => ({
                    nodes: state.nodes.map((node) =>
                        node.id === nodeId ? { ...node, ...updates } : node
                    ),
                })),

            updateNodeData: (nodeId, data) =>
                set((state) => ({
                    nodes: state.nodes.map((node) =>
                        node.id === nodeId ? { ...node, data } : node
                    ),
                })),

            removeNode: (nodeId) =>
                set((state) => ({
                    nodes: state.nodes.filter((node) => node.id !== nodeId),
                    edges: state.edges.filter(
                        (edge) => edge.source !== nodeId && edge.target !== nodeId
                    ),
                })),

            updateEdge: (edgeId, updates) =>
                set((state) => ({
                    edges: state.edges.map((edge) =>
                        edge.id === edgeId ? normalizeEdge({ ...edge, ...updates }) : edge
                    ),
                })),

            updateEdgeData: (edgeId, data) =>
                set((state) => ({
                    edges: state.edges.map((edge) =>
                        edge.id === edgeId
                            ? normalizeEdge({
                                  ...edge,
                                  data: { ...edge.data, ...data } as RelationshipData,
                              })
                            : edge
                    ),
                })),

            removeEdge: (edgeId) =>
                set((state) => ({
                    edges: state.edges.filter((edge) => edge.id !== edgeId),
                })),

            selectedRelationshipKind: "simple",
            selectedSourceMult: "1",
            selectedTargetMult: "*",

            setSelectedRelationshipKind: (kind) => set({ selectedRelationshipKind: kind }),
            setSelectedSourceMult: (mult) => set({ selectedSourceMult: mult }),
            setSelectedTargetMult: (mult) => set({ selectedTargetMult: mult }),
        }),
        {
            name: "uml-editor-diagram",
            version: STORAGE_VERSION,
            partialize: ({ nodes, edges }) => ({ nodes, edges }),
        }
    )
);
