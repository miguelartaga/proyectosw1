import type { Edge, Node } from "@xyflow/react";

export type Column = {
    id: string;
    name: string;
    type: string;
    pk?: boolean;
    nullable?: boolean;
};

export type DatabaseNodeData = {
    label: string;
    columns: Column[];
    isJoin?: boolean;
    joinOf?: [string, string];
};

export type RelationshipKind =
    | "simple"
    | "flechaBlanca"
    | "flechaNegra"
    | "segmentada";

export type Multiplicity = "0..1" | "1" | "0..*" | "1..*" | "*";

export type RelationshipData = {
    id: string;
    source: string;
    target: string;
    kind: RelationshipKind;
    sourceMult: Multiplicity;
    targetMult: Multiplicity;
    label?: string;
};

export type DiagramNode = Node<DatabaseNodeData>;
export type DiagramEdge = Edge<RelationshipData>;

export type DiagramGraph = {
    nodes: DiagramNode[];
    edges: DiagramEdge[];
};

export type PromptHistoryEntry = {
    id: number;
    userId: number;
    prompt: string;
    graph: DiagramGraph;
    createdAt: string;
};

export type User = {
    id: number;
    email: string;
    createdAt: string;
};

export type RawAuthResponse = {
    token: string;
    user: {
        id: number;
        email: string;
        created_at: string;
    };
};

export type LoginPayload = {
    email: string;
    password: string;
};

export type RegisterPayload = LoginPayload;

