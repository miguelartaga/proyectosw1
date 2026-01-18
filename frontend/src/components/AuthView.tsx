import React, { useState } from "react";
import { isAxiosError } from "axios";

import { useAuthStore } from "../store/authStore";

const cardStyle: React.CSSProperties = {
    width: "360px",
    padding: "2rem",
    borderRadius: "8px",
    background: "#ffffff",
    boxShadow: "0 12px 32px rgba(0,0,0,0.1)",
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
};

const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "0.75rem",
    borderRadius: "6px",
    border: "1px solid #cccccc",
    fontSize: "14px",
};

const submitStyle: React.CSSProperties = {
    padding: "0.75rem",
    background: "#2196f3",
    color: "#ffffff",
    border: "none",
    borderRadius: "6px",
    fontSize: "15px",
    fontWeight: 600,
    cursor: "pointer",
};

const secondaryBtnStyle: React.CSSProperties = {
    padding: "0.5rem 0.75rem",
    border: "1px solid #d0d0d0",
    borderRadius: "6px",
    fontSize: "13px",
    background: "#f5f6f8",
    cursor: "pointer",
};

type Mode = "login" | "register";

const AuthView: React.FC = () => {
    const login = useAuthStore((state) => state.login);
    const register = useAuthStore((state) => state.register);

    const [mode, setMode] = useState<Mode>("login");
    const [email, setEmail] = useState("admin@gmail.com");
    const [password, setPassword] = useState("123");
    const [confirmPassword, setConfirmPassword] = useState("123");
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError(null);

        if (mode === "register" && password !== confirmPassword) {
            setError("Las contrasenas no coinciden.");
            return;
        }

        try {
            setIsLoading(true);
            if (mode === "login") {
                await login({ email, password });
            } else {
                await register({ email, password });
            }
        } catch (err: unknown) {
            if (isAxiosError(err)) {
                const detail = err.response?.data?.detail;
                if (detail) {
                    setError(String(detail));
                } else {
                    setError("No se pudo completar la solicitud.");
                }
            } else {
                setError("No se pudo completar la solicitud.");
            }
        } finally {
            setIsLoading(false);
        }
    };

    const toggleMode = () => {
        setMode((prev) => (prev === "login" ? "register" : "login"));
        setError(null);
    };

    return (
        <div
            style={{
                height: "100vh",
                width: "100vw",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "linear-gradient(135deg, #e3f2fd, #bbdefb)",
                padding: "1rem",
            }}
        >
            <div style={cardStyle}>
                <div>
                    <h2 style={{ margin: 0, color: "#0d47a1" }}>
                        {mode === "login" ? "Iniciar sesion" : "Crear cuenta"}
                    </h2>
                    <p style={{ margin: "0.25rem 0 0", color: "#555555", fontSize: "0.9rem" }}>
                        Usa el demo admin o registra un correo nuevo.
                    </p>
                </div>

                <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    <label style={{ fontSize: "0.9rem", color: "#333333" }}>
                        Correo electronico
                        <input
                            style={{ ...inputStyle, marginTop: "0.35rem" }}
                            type="email"
                            autoComplete="email"
                            value={email}
                            onChange={(event) => setEmail(event.target.value)}
                            required
                        />
                    </label>

                    <label style={{ fontSize: "0.9rem", color: "#333333" }}>
                        Contrasena
                        <input
                            style={{ ...inputStyle, marginTop: "0.35rem" }}
                            type="password"
                            autoComplete={mode === "login" ? "current-password" : "new-password"}
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            required
                        />
                    </label>

                    {mode === "register" && (
                        <label style={{ fontSize: "0.9rem", color: "#333333" }}>
                            Confirmar contrasena
                            <input
                                style={{ ...inputStyle, marginTop: "0.35rem" }}
                                type="password"
                                autoComplete="new-password"
                                value={confirmPassword}
                                onChange={(event) => setConfirmPassword(event.target.value)}
                                required
                            />
                        </label>
                    )}

                    {error && (
                        <div
                            role="alert"
                            style={{
                                padding: "0.75rem",
                                background: "#ffebee",
                                color: "#c62828",
                                border: "1px solid #ef9a9a",
                                borderRadius: "6px",
                                fontSize: "0.9rem",
                            }}
                        >
                            {error}
                        </div>
                    )}

                    <button type="submit" style={submitStyle} disabled={isLoading}>
                        {isLoading
                            ? "Procesando..."
                            : mode === "login"
                            ? "Entrar"
                            : "Registrarme"}
                    </button>
                </form>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <button
                        type="button"
                        style={secondaryBtnStyle}
                        onClick={() => {
                            setEmail("admin@gmail.com");
                            setPassword("123");
                            setConfirmPassword("123");
                            setError(null);
                        }}
                    >
                        Usar credenciales de prueba
                    </button>
                    <button type="button" style={secondaryBtnStyle} onClick={toggleMode}>
                        {mode === "login" ? "Crear una cuenta" : "Ya tengo una cuenta"}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default AuthView;
