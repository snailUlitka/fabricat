"use client";

const DEFAULT_BASE_URL = "http://localhost:8000";

const normalizeBase = (value) => {
  if (!value) {
    return DEFAULT_BASE_URL;
  }
  return value.endsWith("/") ? value.slice(0, -1) : value;
};

export const API_BASE =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
    ? normalizeBase(process.env.NEXT_PUBLIC_API_BASE)
    : DEFAULT_BASE_URL;

export const WS_BASE = API_BASE.replace(/^http/, "ws");

async function request(path, { method = "GET", body, token } = {}) {
  const headers = new Headers();
  headers.set("Accept", "application/json");
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") {
        message = payload.detail;
      } else if (payload?.detail?.message) {
        message = payload.detail.message;
      }
    } catch {
      // Ignore JSON parse errors.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export async function registerUser(payload) {
  return request("/auth/register", { method: "POST", body: payload });
}

export async function loginUser(payload) {
  return request("/auth/login", { method: "POST", body: payload });
}
