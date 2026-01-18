import { create } from "zustand";
import { persist } from "zustand/middleware";

import { api, setAuthToken } from "../api";
import type { LoginPayload, RawAuthResponse, RegisterPayload, User } from "../types";

type AuthResponse =
    | RawAuthResponse
    | {
          token?: string;
          access_token?: string;
          token_type?: string;
          user?: RawAuthResponse["user"] | null;
      };

interface AuthState {
    token: string | null;
    user: User | null;
    isAuthenticated: boolean;
    login: (payload: LoginPayload) => Promise<void>;
    register: (payload: RegisterPayload) => Promise<void>;
    logout: () => void;
    setFromResponse: (response: AuthResponse) => void;
}

const STORAGE_KEY = "uml-editor-auth";
const STORAGE_VERSION = 1;

const mapUser = (raw?: RawAuthResponse["user"] | null): User | null => {
    if (!raw) return null;
    return {
        id: raw.id,
        email: raw.email,
        createdAt: raw.created_at ?? "",
    };
};

export const useAuthStore = create<AuthState>()(
    persist(
        (set, get) => ({
            token: null,
            user: null,
            isAuthenticated: false,
            async login(payload) {
                const form = new URLSearchParams();
                form.append("username", payload.email);
                form.append("password", payload.password);

                const { data } = await api.post<AuthResponse>("/auth/login", form, {
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                });
                get().setFromResponse(data);
            },
            async register(payload) {
                const { data } = await api.post<AuthResponse>("/auth/register", payload);
                get().setFromResponse(data);
            },
            logout() {
                set({ token: null, user: null, isAuthenticated: false });
                setAuthToken(null);
            },
            setFromResponse(response) {
                let token: string | null = null;
                if ("token" in response && response.token) {
                    token = response.token;
                } else if ("access_token" in response && response.access_token) {
                    token = response.access_token;
                }
                const user = mapUser(response.user);

                if (!token) {
                    throw new Error("La respuesta de autenticación no contiene un token.");
                }

                setAuthToken(token);
                set({
                    token,
                    user,
                    isAuthenticated: true,
                });
            },
        }),
        {
            name: STORAGE_KEY,
            version: STORAGE_VERSION,
            partialize: (state) => ({
                token: state.token,
                user: state.user,
                isAuthenticated: state.isAuthenticated,
            }),
            onRehydrateStorage: () => (state) => {
                if (state?.token) {
                    setAuthToken(state.token);
                }
            },
        }
    )
);






