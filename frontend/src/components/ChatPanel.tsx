import React, { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { isAxiosError } from "axios";
import { api } from "../api";
import "./ChatPanel.css";
import { useDiagramStore } from "../store/diagramStore";
import type {
    DiagramEdge,
    DiagramGraph,
    DiagramNode,
    Multiplicity,
    RelationshipData,
    RelationshipKind,
    PromptHistoryEntry,
} from "../types";

const DEFAULT_PROMPT =
    "Crea tablas Usuario(id, nombre, email) y Post(id, user_id, titulo). Relacion 1:N";

const HISTORY_LIMIT = 20;
const DICTATION_LANG = "es-ES";

type ApiHistoryItem = {
    id: number;
    user_id: number;
    prompt: string;
    graph: DiagramGraph;
    created_at: string;
};

type VisionResponse = {
    graph: DiagramGraph;
    history_id: number;
    prompt: string;
};

const ChatPanel: React.FC = () => {
    const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isListening, setIsListening] = useState(false);
    const [history, setHistory] = useState<PromptHistoryEntry[]>([]);
    const [isHistoryLoading, setIsHistoryLoading] = useState(false);
    const [historyError, setHistoryError] = useState<string | null>(null);
    const [deletingId, setDeletingId] = useState<number | null>(null);
    const [isClearingHistory, setIsClearingHistory] = useState(false);
    const [activeHistoryId, setActiveHistoryId] = useState<number | null>(null);

    const setGraph = useDiagramStore((state) => state.setGraph);
    const nodes = useDiagramStore((state) => state.nodes);
    const edges = useDiagramStore((state) => state.edges);
    const activeHistoryIdRef = useRef<number | null>(null);
    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const recognitionRef = useRef<any>(null);
    const listeningRef = useRef(false);

    const applyGraphToCanvas = useCallback(
        (graph: DiagramGraph) => {
            const safeNodes: DiagramNode[] = Array.isArray(graph.nodes) ? graph.nodes : [];
            const safeEdges: DiagramEdge[] = Array.isArray(graph.edges) ? graph.edges : [];

            const sanitizedEdges: DiagramEdge[] = safeEdges.map((edge) => {
                const baseData = (edge.data ?? {}) as Partial<RelationshipData>;
                return {
                    ...edge,
                    data: {
                        ...(edge.data ?? {}),
                        id: baseData.id ?? edge.id ?? `edge-${Math.random().toString(36).slice(2)}`,
                        source: baseData.source ?? edge.source,
                        target: baseData.target ?? edge.target,
                        kind: baseData.kind ?? "simple",
                        sourceMult: baseData.sourceMult ?? "1",
                        targetMult: baseData.targetMult ?? "*",
                        label: baseData.label ?? "",
                    },
                } as DiagramEdge;
            });

            setGraph({ nodes: safeNodes, edges: sanitizedEdges });
        },
        [setGraph]
    );

    useEffect(() => {
        activeHistoryIdRef.current = activeHistoryId;
    }, [activeHistoryId]);

    useEffect(() => {
        listeningRef.current = isListening;
    }, [isListening]);

    useEffect(() => {
        const SpeechRecognitionCtor =
            typeof window !== "undefined"
                ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
                : null;
        if (!SpeechRecognitionCtor) {
            recognitionRef.current = null;
            return;
        }

        const recognition = new SpeechRecognitionCtor();
        recognition.lang = DICTATION_LANG;
        recognition.interimResults = false;
        recognition.continuous = true;

        recognition.onresult = (event: any) => {
            let finalText = "";
            for (let i = event.resultIndex; i < event.results.length; i += 1) {
                const result = event.results[i];
                if (result.isFinal) {
                    finalText += result[0]?.transcript ?? "";
                }
            }
            const trimmed = finalText.trim();
            if (!trimmed) {
                return;
            }
            setPrompt((prev) => {
                const base = prev.trim();
                return base ? `${base} ${trimmed}` : trimmed;
            });
        };

        recognition.onerror = () => {
            setError("No se pudo usar el dictado por voz. Revisa permisos del microfono.");
            setIsListening(false);
        };

        recognition.onend = () => {
            if (listeningRef.current) {
                setIsListening(false);
            }
        };

        recognitionRef.current = recognition;

        return () => {
            recognition.stop?.();
        };
    }, []);

    const handleToggleDictation = useCallback(() => {
        const recognition = recognitionRef.current;
        if (!recognition) {
            setError("Tu navegador no soporta dictado por voz.");
            return;
        }
        if (isListening) {
            recognition.stop?.();
            setIsListening(false);
            return;
        }
        setError(null);
        try {
            recognition.start?.();
            setIsListening(true);
        } catch (err) {
            setError("No se pudo iniciar el dictado por voz.");
            setIsListening(false);
        }
    }, [isListening]);

    type LoadHistoryOptions = {
        preserveNullSelection?: boolean;
    };

    const loadHistory = useCallback(
        async (options: LoadHistoryOptions = {}): Promise<PromptHistoryEntry[]> => {
            setIsHistoryLoading(true);
            setHistoryError(null);
            let mapped: PromptHistoryEntry[] = [];
            try {
                const response = await api.get<ApiHistoryItem[]>("/ai/history", {
                    params: { limit: HISTORY_LIMIT },
                });
                const records = Array.isArray(response.data) ? response.data : [];
                mapped = records.map((item) => ({
                    id: item.id,
                    userId: item.user_id,
                    prompt: item.prompt,
                    graph: item.graph,
                    createdAt: item.created_at,
                }));
                setHistory(mapped);

                const currentActive = activeHistoryIdRef.current;
                const exists =
                    currentActive !== null && mapped.some((entry) => entry.id === currentActive);
                let nextActive: number | null;
                if (exists) {
                    nextActive = currentActive;
                } else if (options.preserveNullSelection && currentActive === null) {
                    nextActive = null;
                } else {
                    nextActive = mapped.length > 0 ? mapped[0].id : null;
                }
                setActiveHistoryId(nextActive);
                activeHistoryIdRef.current = nextActive;
            } catch (err) {
                console.error("Error loading history", err);
                setHistoryError("No se pudo cargar el historial.");
                mapped = [];
            } finally {
                setIsHistoryLoading(false);
            }
            return mapped;
        },
        []
    );

    useEffect(() => {
        void loadHistory();
    }, [loadHistory]);

    const handleHistorySelect = useCallback(
        (entry: PromptHistoryEntry) => {
            applyGraphToCanvas(entry.graph);
            setPrompt(entry.prompt);
            setError(null);
            setActiveHistoryId(entry.id);
        },
        [applyGraphToCanvas]
    );

    const handleDeleteEntry = useCallback(
        async (historyId: number) => {
            if (isClearingHistory) {
                return;
            }

            if (typeof window !== "undefined" && !window.confirm("¿Eliminar este prompt del historial?")) {
                return;
            }

            setDeletingId(historyId);
            setHistoryError(null);
            try {
                await api.delete(`/ai/history/${historyId}`);
                await loadHistory({ preserveNullSelection: true });
            } catch (err) {
                console.error("Error deleting history entry", err);
                setHistoryError("No se pudo eliminar la entrada.");
            } finally {
                setDeletingId(null);
            }
        },
        [isClearingHistory, loadHistory]
    );

    const handleClearHistory = useCallback(async () => {
        if (history.length === 0) {
            return;
        }

        if (typeof window !== "undefined" && !window.confirm("¿Eliminar todo el historial?")) {
            return;
        }

        setIsClearingHistory(true);
        setHistoryError(null);
        try {
            await api.delete('/ai/history');
            setHistory([]);
            setActiveHistoryId(null);
            activeHistoryIdRef.current = null;
            setPrompt(DEFAULT_PROMPT);
        } catch (err) {
            console.error("Error clearing history", err);
            setHistoryError("No se pudo limpiar el historial.");
        } finally {
            setIsClearingHistory(false);
            setDeletingId(null);
        }
    }, [history.length]);

    const handleNewConversation = useCallback(() => {
        setPrompt("");
        setError(null);
        setActiveHistoryId(null);
        activeHistoryIdRef.current = null;
    }, []);

    const handleProcessImage = useCallback(
        async (file: File) => {
            if (!file) {
                return;
            }
            if (!file.type.startsWith("image/")) {
                setError("Selecciona un archivo de imagen (png, jpg, svg, etc.).");
                return;
            }

            const trimmedPrompt = prompt.trim();
            const continuingConversation = activeHistoryId !== null;

            setIsLoading(true);
            setError(null);
            try {
                const formData = new FormData();
                formData.append("image", file);
                if (trimmedPrompt) {
                    formData.append("prompt", trimmedPrompt);
                }
                if (continuingConversation && activeHistoryId !== null) {
                    formData.append("history_id", String(activeHistoryId));
                }

                const response = await api.post<VisionResponse>("/ai/vision", formData, {
                    headers: { "Content-Type": "multipart/form-data" },
                });
                const graph = response.data.graph;
                const historyIdFromResponse = response.data.history_id;
                const promptFromResponse = response.data.prompt ?? trimmedPrompt;

                applyGraphToCanvas(graph);
                setPrompt(promptFromResponse || trimmedPrompt);
                setError(null);

                if (
                    continuingConversation &&
                    activeHistoryId !== null &&
                    historyIdFromResponse === activeHistoryId
                ) {
                    setHistory((prev) =>
                        prev.map((entry) =>
                            entry.id === activeHistoryId
                                ? { ...entry, prompt: promptFromResponse || entry.prompt, graph }
                                : entry
                        )
                    );
                } else {
                    await loadHistory({ preserveNullSelection: false });
                }

                if (historyIdFromResponse) {
                    setActiveHistoryId(historyIdFromResponse);
                    activeHistoryIdRef.current = historyIdFromResponse;
                }
            } catch (err: unknown) {
                console.error("Error processing UML image", err);
                let message = "No se pudo interpretar la imagen.";
                const maybeResponse = (err as any)?.response?.data?.detail;
                if (maybeResponse) {
                    message = String(maybeResponse);
                } else if (err instanceof Error) {
                    message = err.message;
                }
                setError(message);
            } finally {
                setIsLoading(false);
            }
        },
        [activeHistoryId, applyGraphToCanvas, loadHistory, prompt]
    );

    const handleImageInputChange = useCallback(
        (event: ChangeEvent<HTMLInputElement>) => {
            const file = event.target.files?.[0];
            if (file) {
                void handleProcessImage(file);
            }
            event.target.value = "";
        },
        [handleProcessImage]
    );

    const handleOpenImagePicker = useCallback(() => {
        if (isLoading) {
            return;
        }
        fileInputRef.current?.click();
    }, [isLoading]);

    const handleGenerate = useCallback(async () => {
        const trimmed = prompt.trim();
        if (!trimmed) {
            setError("Escribe un prompt para generar el diagrama.");
            return;
        }

        const continuingConversation = activeHistoryId !== null;

        setIsLoading(true);
        setError(null);

        try {
            const graphPayload = {
                nodes: nodes.map((node) => ({
                    id: node.id,
                    type: node.type,
                    position: node.position,
                    data: node.data,
                })),
                edges: edges.map((edge) => ({
                    id: edge.id,
                    source: edge.source,
                    target: edge.target,
                    label: edge.label,
                    data: edge.data,
                })),
            };

            const payload: {
                prompt: string;
                graph: typeof graphPayload;
                history_id?: number;
            } = {
                prompt: trimmed,
                graph: graphPayload,
            };
            if (continuingConversation && activeHistoryId !== null) {
                payload.history_id = activeHistoryId;
            }

            const response = await api.post<DiagramGraph>("/ai/generate", payload);
            const graph: DiagramGraph = {
                nodes: Array.isArray(response.data?.nodes) ? response.data.nodes : [],
                edges: Array.isArray(response.data?.edges) ? response.data.edges : [],
            };

            if (graph.nodes.length === 0 && graph.edges.length === 0) {
                setError("La respuesta no contiene nodos ni relaciones.");
                return;
            }

            applyGraphToCanvas(graph);
            setError(null);

            if (continuingConversation && activeHistoryId !== null) {
                setHistory((prev) =>
                    prev.map((entry) =>
                        entry.id === activeHistoryId
                            ? { ...entry, prompt: trimmed, graph }
                            : entry
                    )
                );
            } else {
                await loadHistory({ preserveNullSelection: false });
            }
        } catch (err: unknown) {
            console.error("Error generating diagram", err);
            if (isAxiosError(err)) {
                const detail = err.response?.data?.detail;
                if (detail) {
                    setError(String(detail));
                    return;
                }
            }
            const fallback = buildFallbackDiagram(trimmed);
            if (fallback) {
                applyGraphToCanvas(fallback);
                setError("Backend no disponible; se genero un diseno local.");
            } else {
                const message =
                    typeof err === "object" && err !== null && "message" in err
                        ? String((err as { message?: unknown }).message)
                        : "No fue posible generar el diagrama.";
                setError(message);
            }
        } finally {
            setIsLoading(false);
        }
    }, [prompt, applyGraphToCanvas, loadHistory, nodes, edges, activeHistoryId]);

    const handleKeyPress = useCallback(
        (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                void handleGenerate();
            }
        },
        [handleGenerate]
    );

    return (
        <div className="chat-panel">
            <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="chat-panel__file-input"
                onChange={handleImageInputChange}
            />
            <div className="chat-panel__header">
                <h3>Chat IA</h3>
                <p>Describe las tablas que quieres crear y sus relaciones.</p>
            </div>

            <div className="chat-panel__body">
                <section className="chat-panel__card chat-panel__history-card">
                    <div className="chat-panel__card-header">
                        <strong>Historial</strong>
                        <div className="chat-panel__actions">
                            <button
                                type="button"
                                className="chat-panel__button chat-panel__button--primary"
                                onClick={handleNewConversation}
                            >
                                Nueva conversacion
                            </button>
                            <button
                                type="button"
                                className="chat-panel__button chat-panel__button--success"
                                onClick={handleOpenImagePicker}
                                disabled={isLoading}
                            >
                                Subir diagrama
                            </button>
                            <button
                                type="button"
                                className="chat-panel__button chat-panel__button--ghost"
                                onClick={() => {
                                    void loadHistory({ preserveNullSelection: activeHistoryId === null });
                                }}
                                disabled={isHistoryLoading}
                            >
                                {isHistoryLoading ? "Actualizando..." : "Actualizar"}
                            </button>
                            <button
                                type="button"
                                className="chat-panel__button chat-panel__button--danger"
                                onClick={() => {
                                    void handleClearHistory();
                                }}
                                disabled={isClearingHistory || history.length === 0}
                            >
                                {isClearingHistory ? "Borrando..." : "Borrar todo"}
                            </button>
                        </div>
                    </div>
                    {historyError && (
                        <div role="status" className="chat-panel__alert chat-panel__alert--error">
                            {historyError}
                        </div>
                    )}
                    <div className="chat-panel__history">
                        {isHistoryLoading && history.length === 0 ? (
                            <div className="chat-panel__placeholder">Cargando historial...</div>
                        ) : history.length === 0 ? (
                            <div className="chat-panel__placeholder">
                                Aun no hay entradas en el historial. Genera un prompt para comenzar.
                            </div>
                        ) : (
                            history.map((entry) => {
                                const parsedDate = new Date(entry.createdAt);
                                const formattedDate = Number.isNaN(parsedDate.getTime())
                                    ? entry.createdAt
                                    : parsedDate.toLocaleString();
                                const truncatedPrompt =
                                    entry.prompt.length > 160
                                        ? `${entry.prompt.slice(0, 157)}...`
                                        : entry.prompt;
                                const isDeletingEntry = deletingId === entry.id;
                                const disableDelete = isDeletingEntry || isClearingHistory;
                                const isActive = activeHistoryId === entry.id;

                                return (
                                    <div
                                        key={entry.id}
                                        className={`chat-panel__history-item${isActive ? ' chat-panel__history-item--active' : ''}`}
                                    >
                                        <button
                                            type="button"
                                            className="chat-panel__history-select"
                                            onClick={() => handleHistorySelect(entry)}
                                        >
                                            <span className="chat-panel__history-title">{truncatedPrompt}</span>
                                            <span className="chat-panel__history-date">{formattedDate}</span>
                                        </button>
                                        <button
                                            type="button"
                                            className="chat-panel__button chat-panel__button--danger chat-panel__history-delete"
                                            onClick={() => {
                                                void handleDeleteEntry(entry.id);
                                            }}
                                            disabled={disableDelete}
                                        >
                                            {isDeletingEntry ? "Eliminando..." : "Eliminar"}
                                        </button>
                                    </div>
                                );
                            })
                        )}
                    </div>
                </section>

                <section className="chat-panel__card chat-panel__composer">
                    {error && (
                        <div role="alert" className="chat-panel__alert chat-panel__alert--error">
                            {error}
                        </div>
                    )}
                    <label className="chat-panel__label" htmlFor="chat-prompt">
                        Instrucciones
                    </label>
                    <textarea
                        id="chat-prompt"
                        className="chat-panel__textarea"
                        placeholder="Describe el diagrama que quieres generar..."
                        value={prompt}
                        onChange={(event) => setPrompt(event.target.value)}
                        onKeyDown={handleKeyPress}
                        rows={6}
                    />
                    <div className="chat-panel__footer">
                        <span className="chat-panel__helper">Ctrl/Cmd + Enter para enviar</span>
                        <div className="chat-panel__actions">
                            <button
                                type="button"
                                className={`chat-panel__button chat-panel__button--ghost${
                                    isListening ? " chat-panel__button--listening" : ""
                                }`}
                                onClick={handleToggleDictation}
                                disabled={isLoading}
                            >
                                {isListening ? "Escuchando..." : "Dictado por voz"}
                            </button>
                            <button
                                type="button"
                                className="chat-panel__button chat-panel__button--primary"
                                onClick={() => {
                                    void handleGenerate();
                                }}
                                disabled={isLoading}
                            >
                                {isLoading ? "Generando..." : "Enviar al lienzo"}
                            </button>
                        </div>
                    </div>
                </section>
            </div>
        </div>
    );

};
export default ChatPanel;


// -----------------------------------------------------------------------------
// Fallback generator (cuando el backend no responde)
// -----------------------------------------------------------------------------

type Position = { x: number; y: number };

const buildNode = (
    id: string,
    label: string,
    columns: DiagramNode["data"]["columns"],
    position: Position,
    extra: Partial<DiagramNode["data"]> = {}
): DiagramNode => ({
    id,
    type: "databaseNode",
    position,
    data: {
        label,
        columns,
        ...extra,
    },
});

const buildEdge = (
    id: string,
    source: string,
    target: string,
    sourceMult: Multiplicity,
    targetMult: Multiplicity,
    kind: RelationshipKind = "simple",
    label = ""
): DiagramEdge => ({
    id,
    source,
    target,
    label,
    data: {
        id,
        source,
        target,
        kind,
        sourceMult,
        targetMult,
        label,
    },
});

const buildSupermarketDiagram = (): DiagramGraph => {
    const nodes: DiagramNode[] = [
        buildNode(
            "node-productos",
            "Productos",
            [
                { id: "prod-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "prod-nombre", name: "nombre", type: "VARCHAR(120)", nullable: false },
                { id: "prod-precio", name: "precio", type: "DECIMAL(10,2)", nullable: false },
                { id: "prod-stock", name: "stock", type: "INT", nullable: false },
            ],
            { x: 460, y: 140 }
        ),
        buildNode(
            "node-categorias",
            "Categorias",
            [
                { id: "cat-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "cat-nombre", name: "nombre", type: "VARCHAR(120)", nullable: false },
                { id: "cat-descripcion", name: "descripcion", type: "TEXT", nullable: true },
            ],
            { x: 180, y: 80 }
        ),
        buildNode(
            "node-proveedores",
            "Proveedores",
            [
                { id: "prov-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "prov-nombre", name: "nombre", type: "VARCHAR(150)", nullable: false },
                { id: "prov-telefono", name: "telefono", type: "VARCHAR(50)", nullable: true },
                { id: "prov-email", name: "email", type: "VARCHAR(120)", nullable: true },
            ],
            { x: 760, y: 80 }
        ),
        buildNode(
            "node-clientes",
            "Clientes",
            [
                { id: "cli-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "cli-nombre", name: "nombre", type: "VARCHAR(150)", nullable: false },
                { id: "cli-email", name: "email", type: "VARCHAR(150)", nullable: true },
                { id: "cli-telefono", name: "telefono", type: "VARCHAR(50)", nullable: true },
            ],
            { x: 180, y: 360 }
        ),
        buildNode(
            "node-empleados",
            "Empleados",
            [
                { id: "emp-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "emp-nombre", name: "nombre", type: "VARCHAR(150)", nullable: false },
                { id: "emp-rol", name: "rol", type: "VARCHAR(80)", nullable: false },
            ],
            { x: 760, y: 360 }
        ),
        buildNode(
            "node-ventas",
            "Ventas",
            [
                { id: "ven-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "ven-fecha", name: "fecha", type: "DATETIME", nullable: false },
                { id: "ven-total", name: "total", type: "DECIMAL(10,2)", nullable: false },
                { id: "ven-cliente", name: "cliente_id", type: "INT", nullable: false },
                { id: "ven-empleado", name: "empleado_id", type: "INT", nullable: false },
            ],
            { x: 460, y: 360 }
        ),
        buildNode(
            "node-detalle-venta",
            "DetalleVenta",
            [
                { id: "det-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "det-venta", name: "venta_id", type: "INT", nullable: false },
                { id: "det-producto", name: "producto_id", type: "INT", nullable: false },
                { id: "det-cantidad", name: "cantidad", type: "INT", nullable: false },
                { id: "det-precio", name: "precio_unitario", type: "DECIMAL(10,2)", nullable: false },
            ],
            { x: 460, y: 560 },
            { isJoin: true, joinOf: ["Ventas", "Productos"] }
        ),
        buildNode(
            "node-inventario",
            "Inventario",
            [
                { id: "inv-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "inv-producto", name: "producto_id", type: "INT", nullable: false },
                { id: "inv-sucursal", name: "sucursal", type: "VARCHAR(80)", nullable: false },
                { id: "inv-stock", name: "stock_actual", type: "INT", nullable: false },
            ],
            { x: 900, y: 360 }
        ),
    ];

    const edges: DiagramEdge[] = [
        buildEdge("edge-cat-productos", "node-categorias", "node-productos", "1", "*"),
        buildEdge("edge-prov-productos", "node-proveedores", "node-productos", "1", "*"),
        buildEdge("edge-productos-inventario", "node-productos", "node-inventario", "1", "*"),
        buildEdge("edge-clientes-ventas", "node-clientes", "node-ventas", "1", "*"),
        buildEdge("edge-empleados-ventas", "node-empleados", "node-ventas", "1", "*"),
        buildEdge("edge-ventas-detalle", "node-ventas", "node-detalle-venta", "1", "*"),
        buildEdge("edge-productos-detalle", "node-productos", "node-detalle-venta", "1", "*"),
    ];

    return { nodes, edges };
};

const buildDefaultDiagram = (): DiagramGraph => {
    const nodes: DiagramNode[] = [
        buildNode(
            "node-usuario-ai",
            "Usuario",
            [
                { id: "u-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "u-nombre", name: "nombre", type: "VARCHAR(100)", nullable: false },
                { id: "u-email", name: "email", type: "VARCHAR(150)", nullable: false },
            ],
            { x: 200, y: 140 }
        ),
        buildNode(
            "node-post-ai",
            "Post",
            [
                { id: "p-id", name: "id", type: "INT", pk: true, nullable: false },
                { id: "p-user", name: "user_id", type: "INT", nullable: false },
                { id: "p-title", name: "titulo", type: "VARCHAR(200)", nullable: false },
            ],
            { x: 520, y: 200 }
        ),
    ];

    const edges: DiagramEdge[] = [
        buildEdge(
            "edge-usuario-post-ai",
            "node-usuario-ai",
            "node-post-ai",
            "1",
            "*",
            "simple",
            "Usuario crea Post"
        ),
    ];

    return { nodes, edges };
};

const buildFallbackDiagram = (prompt: string): DiagramGraph | null => {
    const text = prompt.toLowerCase();
    if (text.includes("supermercado") || text.includes("supermarket")) {
        return buildSupermarketDiagram();
    }
    if (text.includes("usuario") || text.includes("post")) {
        return buildDefaultDiagram();
    }
    return null;
};















