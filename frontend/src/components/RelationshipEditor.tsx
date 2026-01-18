import React, { useEffect, useMemo, useState } from "react";
import type { Multiplicity, RelationshipData, RelationshipKind } from "../types";

interface RelationshipEditorProps {
    isOpen: boolean;
    onClose: () => void;
    relationship: RelationshipData | null;
    sourceTableName: string;
    targetTableName: string;
    onSave: (relationship: RelationshipData) => void;
}

const multiplicities: Multiplicity[] = ["1", "0..1", "*", "1..*", "0..*"];

const kindOptions: { value: RelationshipKind; icon: React.ReactElement }[] = [
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
];

const RelationshipEditor: React.FC<RelationshipEditorProps> = ({
    isOpen,
    onClose,
    relationship,
    sourceTableName,
    targetTableName,
    onSave,
}) => {
    const [kind, setKind] = useState<RelationshipKind>("simple");
    const [sourceMult, setSourceMult] = useState<Multiplicity>("1");
    const [targetMult, setTargetMult] = useState<Multiplicity>("*");
    const [label, setLabel] = useState("");

    useEffect(() => {
        if (!relationship) {
            return;
        }

        setKind(relationship.kind);
        setSourceMult(relationship.sourceMult);
        setTargetMult(relationship.targetMult);
        setLabel(relationship.label ?? "");
    }, [relationship]);

    const header = useMemo(
        () => `${sourceTableName} -> ${targetTableName}`,
        [sourceTableName, targetTableName]
    );

    if (!isOpen || !relationship) {
        return null;
    }

    const handleSave = () => {
        onSave({
            ...relationship,
            kind,
            sourceMult,
            targetMult,
            label,
        });
    };

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
                    padding: 20,
                    borderRadius: 8,
                    width: 460,
                    boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
                }}
            >
                <h3 style={{ margin: 0 }}>Editar relacion</h3>
                <p style={{ marginTop: 4, marginBottom: 20 }}>{header}</p>

                <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>Tipo UML</div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
                        {kindOptions.map(({ value, icon }) => (
                            <button
                                key={value}
                                type="button"
                                onClick={() => setKind(value)}
                                style={{
                                    background: kind === value ? "#2196f3" : "#eeeeee",
                                    border: "none",
                                    borderRadius: 6,
                                    padding: 6,
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                }}
                                title={value}
                            >
                                {icon}
                            </button>
                        ))}
                    </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontWeight: 600 }}>Source</span>
                        <select
                            value={sourceMult}
                            onChange={(event) => setSourceMult(event.target.value as Multiplicity)}
                            style={{
                                width: "100%",
                                padding: 8,
                                borderRadius: 6,
                                border: "1px solid #cccccc",
                            }}
                        >
                            {multiplicities.map((item) => (
                                <option key={item} value={item}>
                                    {item}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontWeight: 600 }}>Target</span>
                        <select
                            value={targetMult}
                            onChange={(event) => setTargetMult(event.target.value as Multiplicity)}
                            style={{
                                width: "100%",
                                padding: 8,
                                borderRadius: 6,
                                border: "1px solid #cccccc",
                            }}
                        >
                            {multiplicities.map((item) => (
                                <option key={item} value={item}>
                                    {item}
                                </option>
                            ))}
                        </select>
                    </label>
                </div>

                <div style={{ marginTop: 16 }}>
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>Etiqueta</div>
                    <input
                        type="text"
                        value={label}
                        onChange={(event) => setLabel(event.target.value)}
                        placeholder="Nombre de la relacion"
                        style={{
                            width: "100%",
                            padding: 8,
                            borderRadius: 6,
                            border: "1px solid #cccccc",
                        }}
                    />
                </div>

                <div
                    style={{
                        display: "flex",
                        justifyContent: "flex-end",
                        gap: 10,
                        marginTop: 20,
                    }}
                >
                    <button
                        type="button"
                        onClick={onClose}
                        style={{
                            padding: "8px 12px",
                            border: "1px solid #cccccc",
                            borderRadius: 6,
                            background: "#f5f5f5",
                            cursor: "pointer",
                        }}
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        onClick={handleSave}
                        style={{
                            padding: "8px 14px",
                            borderRadius: 6,
                            border: "none",
                            background: "#2196f3",
                            color: "white",
                            cursor: "pointer",
                        }}
                    >
                        Guardar
                    </button>
                </div>
            </div>
        </div>
    );
};

export default RelationshipEditor;
