"use client";

import { useCallback, useEffect, useState } from "react";
import AuthPanel from "@/components/auth/AuthPanel";
import GameConsole from "@/components/game/GameConsole";
import { loginUser, registerUser } from "@/lib/apiClient";
import { readJson, removeKey, writeJson } from "@/lib/storage";

const AUTH_STORAGE_KEY = "fabricat-auth";

const INITIAL_AUTH_STATE = {
  status: "checking",
  user: null,
  token: null,
};

export default function HomePage() {
  const [authState, setAuthState] = useState(INITIAL_AUTH_STATE);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");

  const isChecking = authState.status === "checking";
  const isAuthenticated = authState.status === "authenticated";

  useEffect(() => {
    const stored = readJson(AUTH_STORAGE_KEY, null);
    if (stored?.user && stored?.token) {
      setAuthState({
        status: "authenticated",
        user: stored.user,
        token: stored.token,
      });
    } else {
      setAuthState({ status: "unauthenticated", user: null, token: null });
    }
  }, []);

  const persistAuth = useCallback((payload) => {
    writeJson(AUTH_STORAGE_KEY, payload);
    setAuthState({
      status: "authenticated",
      user: payload.user,
      token: payload.token,
    });
  }, []);

  const clearAuth = useCallback(() => {
    removeKey(AUTH_STORAGE_KEY);
    setAuthState({ status: "unauthenticated", user: null, token: null });
  }, []);

  const runAuthTask = useCallback(async (task) => {
    setAuthBusy(true);
    try {
      return await task();
    } finally {
      setAuthBusy(false);
    }
  }, []);

  const handleRegister = useCallback(
    async (form) => {
      setAuthError("");
      try {
        await runAuthTask(async () => {
          const payload = await registerUser(form);
          persistAuth({
            user: payload.user,
            token: payload.token.access_token,
          });
        });
      } catch (error) {
        setAuthError(error?.message ?? "Не удалось зарегистрироваться.");
        throw error;
      }
    },
    [persistAuth, runAuthTask]
  );

  const handleLogin = useCallback(
    async (credentials) => {
      setAuthError("");
      try {
        await runAuthTask(async () => {
          const payload = await loginUser(credentials);
          persistAuth({
            user: payload.user,
            token: payload.token.access_token,
          });
        });
      } catch (error) {
        setAuthError(error?.message ?? "Не удалось войти.");
        throw error;
      }
    },
    [persistAuth, runAuthTask]
  );

  const handleLogout = useCallback(() => {
    clearAuth();
    setAuthError("");
  }, [clearAuth]);

  return (
    <main className="app-shell">
      <div className="shell-wrapper">
        <header className="surface-card hero-panel">
          <div>
            <p className="eyebrow">Fabricat command deck</p>
            <h1>Управляйте ходом партии</h1>
            <p className="muted-text">
              Клиент напрямую работает с FastAPI и WebSocket сервером на{" "}
              <code>localhost:8000</code>. После входа запускайте сессии, следите
              за фазами месяца и отправляйте заявки так же, как это делает
              настоящий игрок.
            </p>
          </div>
          {isAuthenticated ? (
            <div className="session-pill">
              Текущий командир: <strong>{authState.user.nickname}</strong>
            </div>
          ) : null}
        </header>

        {isChecking ? (
          <section className="surface-card loading-block">
            <p>Проверяем сохранённый токен…</p>
          </section>
        ) : null}

        {!isChecking && !isAuthenticated ? (
          <AuthPanel
            busy={authBusy}
            onLogin={handleLogin}
            onRegister={handleRegister}
            errorMessage={authError}
          />
        ) : null}

        {isAuthenticated ? (
          <GameConsole
            user={authState.user}
            token={authState.token}
            onLogout={handleLogout}
          />
        ) : null}
      </div>
    </main>
  );
}
