import axios from "axios";

const baseURL = (() => {
  const envUrl = import.meta.env.VITE_API_URL as string | undefined;
  if (envUrl && envUrl.trim().length > 0) {
    // Elimina la barra final si la hubiera
    return envUrl.replace(/\/$/, "");
  }

  if (import.meta.env.DEV) {
    return "/api"; // Proxy local durante el desarrollo
  }

  return "https://api.multicargas.com.bo/api"; // Fallback seguro en despliegues
})();

export const api = axios.create({
  baseURL,
  timeout: 15000,
});

export const setAuthToken = (token: string | null): void => {
  if (token) {
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common["Authorization"];
  }
};
