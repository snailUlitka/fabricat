"use client";

import { useState } from "react";

const DEFAULT_LOGIN = { nickname: "", password: "" };
const DEFAULT_REGISTER = {
  nickname: "",
  password: "",
  confirmPassword: "",
  icon: "astronaut",
};

const AVATAR_OPTIONS = [
  "astronaut",
  "botanist",
  "captain",
  "diver",
  "engineer",
  "geologist",
  "hacker",
  "inventor",
  "pilot",
  "scientist",
];

/**
 * Authentication panel containing both sign-in and registration flows.
 */
export default function AuthPanel({
  busy = false,
  onLogin = async () => {},
  onRegister = async () => {},
  errorMessage = "",
}) {
  const [mode, setMode] = useState("login");
  const [loginForm, setLoginForm] = useState(DEFAULT_LOGIN);
  const [registerForm, setRegisterForm] = useState(DEFAULT_REGISTER);
  const [localError, setLocalError] = useState("");

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setLocalError("");
  };

  const handleLoginSubmit = async (event) => {
    event.preventDefault();
    if (!loginForm.nickname.trim() || !loginForm.password.trim()) {
      setLocalError("Введите ник и пароль, с которыми регистрировались.");
      return;
    }

    setLocalError("");
    try {
      await onLogin({
        nickname: loginForm.nickname.trim(),
        password: loginForm.password,
      });
    } catch (error) {
      setLocalError(error?.message ?? "Unable to sign in right now.");
    }
  };

  const handleRegisterSubmit = async (event) => {
    event.preventDefault();

    const nickname = registerForm.nickname.trim();
    const { password, confirmPassword, icon } = registerForm;

    if (nickname.length < 3) {
      setLocalError("Choose a nickname that is at least 3 characters long.");
      return;
    }

    if (password.length < 6) {
      setLocalError("Passwords should be at least 6 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setLocalError("Passwords do not match.");
      return;
    }

    setLocalError("");

    try {
      await onRegister({ nickname, password, icon });
    } catch (error) {
      setLocalError(error?.message ?? "Unable to create an account right now.");
    }
  };

  const errorToDisplay = localError || errorMessage;

  return (
    <section className="surface-card auth-panel">
      <div className="panel-heading">
        <p className="eyebrow">First Contact</p>
        <h2>Авторизуйтесь, чтобы войти в Fabricat</h2>
        <p className="muted-text">
          Ник и пароль напрямую уходят в бекенд на <code>localhost:8000</code>.
          После регистрации вы сразу получите токен доступа.
        </p>
      </div>

      <div className="tab-switcher">
        <button
          type="button"
          className={`tab-button ${mode === "login" ? "is-active" : ""}`}
          onClick={() => switchMode("login")}
          aria-pressed={mode === "login"}
        >
          Sign in
        </button>
        <button
          type="button"
          className={`tab-button ${mode === "register" ? "is-active" : ""}`}
          onClick={() => switchMode("register")}
          aria-pressed={mode === "register"}
        >
          Create account
        </button>
      </div>

      {errorToDisplay ? (
        <div className="error-banner" role="alert">
          {errorToDisplay}
        </div>
      ) : null}

      {mode === "login" ? (
        <form className="auth-form" onSubmit={handleLoginSubmit}>
          <div className="form-grid">
            <label className="form-field">
              <span>Nickname</span>
              <input
                type="text"
                placeholder="Commander_42"
                value={loginForm.nickname}
                onChange={(event) =>
                  setLoginForm((form) => ({
                    ...form,
                    nickname: event.target.value,
                  }))
                }
                autoComplete="username"
                disabled={busy}
              />
            </label>

            <label className="form-field">
              <span>Password</span>
              <input
                type="password"
                placeholder="••••••"
                value={loginForm.password}
                onChange={(event) =>
                  setLoginForm((form) => ({
                    ...form,
                    password: event.target.value,
                  }))
                }
                autoComplete="current-password"
                disabled={busy}
              />
            </label>
          </div>

          <div className="form-actions">
            <button
              type="submit"
              className="button button-primary"
              disabled={busy}
            >
              {busy ? "Signing in…" : "Enter console"}
            </button>
          </div>
        </form>
      ) : (
        <form className="auth-form" onSubmit={handleRegisterSubmit}>
          <div className="form-grid">
            <label className="form-field">
              <span>Commander name</span>
              <input
                type="text"
                placeholder="Commander Vega"
                value={registerForm.nickname}
                onChange={(event) =>
                  setRegisterForm((form) => ({
                    ...form,
                    nickname: event.target.value,
                  }))
                }
                autoComplete="off"
                disabled={busy}
              />
            </label>

            <label className="form-field">
              <span>Password</span>
              <input
                type="password"
                placeholder="Minimum 6 characters"
                value={registerForm.password}
                onChange={(event) =>
                  setRegisterForm((form) => ({
                    ...form,
                    password: event.target.value,
                  }))
                }
                autoComplete="new-password"
                disabled={busy}
              />
            </label>

            <label className="form-field">
              <span>Confirm password</span>
              <input
                type="password"
                placeholder="Repeat password"
                value={registerForm.confirmPassword}
                onChange={(event) =>
                  setRegisterForm((form) => ({
                    ...form,
                    confirmPassword: event.target.value,
                  }))
                }
                autoComplete="new-password"
                disabled={busy}
              />
            </label>

            <label className="form-field">
              <span>Avatar</span>
              <select
                value={registerForm.icon}
                onChange={(event) =>
                  setRegisterForm((form) => ({
                    ...form,
                    icon: event.target.value,
                  }))
                }
                disabled={busy}
              >
                {AVATAR_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="form-actions">
            <button
              type="submit"
              className="button button-primary"
              disabled={busy}
            >
              {busy ? "Creating profile…" : "Create access key"}
            </button>
          </div>
        </form>
      )}

      <p className="muted-text hint-text">
        После входа можно открыть игровую сессию и сразу отправлять действия
        через WebSocket.
      </p>
    </section>
  );
}
