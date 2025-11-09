"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { WS_BASE } from "@/lib/apiClient";

const INITIAL_SESSION = {
  sessionCode: null,
  month: null,
  phase: null,
  phaseDurationSeconds: 0,
};

const PHASE_LABELS = {
  expenses: "1. Expenses",
  market: "2. Market",
  buy: "3. Buy RMs",
  production: "4. Production",
  sell: "5. Sell FGs",
  loans: "6. Loans",
  construction: "7. Construction",
  end_month: "8. End of month",
};

const CONSTRUCTION_OPTIONS = [
  { value: "idle", label: "Idle" },
  { value: "build_basic", label: "Build basic factory" },
  { value: "build_auto", label: "Build automated factory" },
  { value: "upgrade", label: "Upgrade basic → auto" },
];

const LOAN_DECISIONS = [
  { value: "call", label: "Call repayment" },
  { value: "skip", label: "Skip / idle" },
];

const formatSeconds = (seconds) => {
  if (seconds == null) {
    return "—";
  }
  const clamped = Math.max(0, seconds);
  const minutes = Math.floor(clamped / 60);
  const remainder = clamped % 60;
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
};

export default function GameConsole({ user, token, onLogout }) {
  const socketRef = useRef(null);
  const pendingCodeRef = useRef(null);

  const [connectionState, setConnectionState] = useState("idle");
  const [sessionInfo, setSessionInfo] = useState(INITIAL_SESSION);
  const [currentTick, setCurrentTick] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [reports, setReports] = useState([]);
  const [lastAck, setLastAck] = useState(null);
  const [serverError, setServerError] = useState("");
  const [wsError, setWsError] = useState("");
  const [sessionCodeInput, setSessionCodeInput] = useState("");
  const [connectNonce, setConnectNonce] = useState(0);
  const [lastStatus, setLastStatus] = useState(null);
  const [seniorityHistory, setSeniorityHistory] = useState([]);
  const [tieBreakLog, setTieBreakLog] = useState([]);
  const [sessionRunning, setSessionRunning] = useState(false);
  const [lastControlAck, setLastControlAck] = useState(null);

  const [buyForm, setBuyForm] = useState({ quantity: 2, price: 320 });
  const [sellForm, setSellForm] = useState({ quantity: 2, price: 480 });
  const [productionForm, setProductionForm] = useState({ basic: 1, auto: 0 });
  const [loanForm, setLoanForm] = useState({ slot: 0, decision: "call" });
  const [constructionChoice, setConstructionChoice] = useState("idle");

  const currentPhase = currentTick?.phase ?? sessionInfo.phase;
  const userId = user?.id ?? user?.id_;

  const connectToSession = useCallback(
    (code) => {
      if (!token) {
        setServerError("Нет токена авторизации.");
        return;
      }

      pendingCodeRef.current = code?.trim() || null;
      setReports([]);
      setAnalytics(null);
      setLastAck(null);
      setLastStatus(null);
      setSeniorityHistory([]);
      setTieBreakLog([]);
      setServerError("");
      setWsError("");
      setSessionInfo(INITIAL_SESSION);
      setCurrentTick(null);
      setSessionRunning(false);
      setLastControlAck(null);
      setConnectionState("connecting");
      setConnectNonce((nonce) => nonce + 1);
    },
    [token]
  );

  const disconnect = useCallback(() => {
    setConnectionState("idle");
    setSessionInfo(INITIAL_SESSION);
    setCurrentTick(null);
    setLastAck(null);
    setServerError("");
    setSessionRunning(false);
    setLastControlAck(null);
    if (socketRef.current) {
      socketRef.current.close(1000, "Client disconnect");
      socketRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (connectNonce === 0 || !token) {
      return;
    }

    if (socketRef.current) {
      socketRef.current.close(1000, "Reconnect");
      socketRef.current = null;
    }

    const wsUrl = `${WS_BASE}/ws/game?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;
    const desiredCode = pendingCodeRef.current;

    ws.onopen = () => {
      setConnectionState("connected");
      const joinPayload = { type: "join" };
      if (desiredCode) {
        joinPayload.session_code = desiredCode;
      }
      ws.send(JSON.stringify(joinPayload));
    };

    ws.onerror = () => {
      setWsError(
        "WebSocket не отвечает. Убедитесь, что backend слушает порт 8000."
      );
    };

    ws.onclose = () => {
      setConnectionState("idle");
      socketRef.current = null;
    };

    ws.onmessage = (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (payload.type) {
        case "welcome": {
          setSessionInfo({
            sessionCode: payload.session_code,
            month: payload.month,
            phase: payload.phase,
            phaseDurationSeconds: payload.phase_duration_seconds,
          });
          setAnalytics(payload.analytics);
          setSeniorityHistory(payload.seniority);
          setTieBreakLog(payload.tie_break_log);
          setSessionRunning(false);
          setLastControlAck(null);
          setServerError("");
          break;
        }
        case "phase_tick": {
          setCurrentTick(payload.tick);
          setSessionInfo((info) => ({
            ...info,
            phase: payload.tick.phase,
          }));
          break;
        }
        case "phase_report": {
          setReports((prev) => [payload.report, ...prev].slice(0, 20));
          setAnalytics(payload.report.analytics);
          setSessionInfo((info) => ({
            ...info,
            month: payload.report.month,
          }));
          break;
        }
        case "action_ack": {
          setLastAck(payload);
          setServerError("");
          break;
        }
        case "phase_status": {
          setLastStatus(payload);
          setAnalytics(payload.analytics);
          setSessionInfo((info) => ({
            ...info,
            phase: payload.phase,
            month: payload.month,
          }));
          break;
        }
        case "error": {
          setServerError(payload.message);
          break;
        }
        case "session_control_ack": {
          if (payload.started) {
            setSessionRunning(true);
          } else if (payload.detail?.reason === "session_finished") {
            setSessionRunning(false);
          }
          setLastControlAck(payload);
          break;
        }
        default:
          break;
      }
    };

    return () => {
      ws.close(1000, "cleanup");
    };
  }, [connectNonce, token]);

  const sendMessage = useCallback((message) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setServerError("WebSocket не подключен.");
      return false;
    }
    socket.send(JSON.stringify(message));
    return true;
  }, []);

  const sendPhaseAction = useCallback(
    (payload) => {
      if (!currentPhase) {
        setServerError("Текущая фаза неизвестна.");
        return;
      }
      if (!sessionRunning) {
        setServerError("Сессия ещё не запущена.");
        return;
      }
      sendMessage({
        type: "phase_action",
        phase: currentPhase,
        payload,
      });
    },
    [currentPhase, sendMessage, sessionRunning]
  );

  const requestStatus = useCallback(() => {
    sendMessage({ type: "phase_status" });
  }, [sendMessage]);

  const sendHeartbeat = useCallback(() => {
    sendMessage({ type: "heartbeat", nonce: Date.now().toString(16) });
  }, [sendMessage]);


  const handleBuySubmit = (event) => {
    event.preventDefault();
    sendPhaseAction({
      kind: "submit_buy_bid",
      quantity: Math.max(0, Number(buyForm.quantity) || 0),
      price: Math.max(0, Number(buyForm.price) || 0),
    });
  };

  const handleSellSubmit = (event) => {
    event.preventDefault();
    sendPhaseAction({
      kind: "submit_sell_bid",
      quantity: Math.max(0, Number(sellForm.quantity) || 0),
      price: Math.max(0, Number(sellForm.price) || 0),
    });
  };

  const handleProductionSubmit = (event) => {
    event.preventDefault();
    sendPhaseAction({
      kind: "production_plan",
      basic: Math.max(0, Number(productionForm.basic) || 0),
      auto: Math.max(0, Number(productionForm.auto) || 0),
    });
  };

  const handleLoanSubmit = (event) => {
    event.preventDefault();
    sendPhaseAction({
      kind: "loan_decision",
      slot: Math.max(0, Number(loanForm.slot) || 0),
      decision: loanForm.decision,
    });
  };

  const handleConstructionSubmit = (event) => {
    event.preventDefault();
    sendPhaseAction({
      kind: "construction_request",
      project: constructionChoice,
    });
  };

  const handleSkip = () => {
    sendPhaseAction({ kind: "skip" });
  };

  const isConnected = connectionState === "connected";

  const startSession = useCallback(() => {
    if (!isConnected) {
      setServerError("Сначала подключитесь к сессии.");
      return;
    }
    setServerError("");
    sendMessage({ type: "session_control", command: "start" });
  }, [isConnected, sendMessage]);

  const analyticsPlayers = analytics?.players ?? [];
  const bankruptIds = analytics?.bankrupt_players ?? [];

  const currentPhaseLabel = currentPhase
    ? PHASE_LABELS[currentPhase] ?? currentPhase
    : "—";

  const sessionMeta = useMemo(
    () => [
      { label: "Session code", value: sessionInfo.sessionCode ?? "—" },
      { label: "Month", value: sessionInfo.month ?? "—" },
      { label: "Phase", value: currentPhaseLabel },
      {
        label: "Tick",
        value: formatSeconds(currentTick?.remaining_seconds),
      },
    ],
    [currentPhaseLabel, currentTick?.remaining_seconds, sessionInfo.month, sessionInfo.sessionCode]
  );

  return (
    <section className="game-console">
      <section className="surface-card connection-panel">
        <div className="panel-heading">
          <p className="eyebrow">Соединение</p>
          <h2>Управление WebSocket</h2>
        </div>
        <div className="connection-grid">
          <label className="form-field">
            <span>Войти по коду</span>
            <input
              type="text"
              placeholder="например, 4f9c0a12"
              value={sessionCodeInput}
              onChange={(event) => setSessionCodeInput(event.target.value)}
            />
          </label>
          <div className="connection-buttons">
            <button
              type="button"
              className="button button-primary"
              onClick={() => connectToSession(sessionCodeInput)}
            >
              {isConnected ? "Переподключиться" : "Подключиться / создать"}
            </button>
            <button
              type="button"
              className="button button-secondary"
              onClick={() => connectToSession(null)}
            >
              Новая сессия
            </button>
            <button
              type="button"
              className="button button-ghost"
              onClick={disconnect}
              disabled={!isConnected}
            >
              Отключиться
            </button>
            <button
              type="button"
              className="button button-ghost"
              onClick={onLogout}
            >
              Выйти из профиля
            </button>
          </div>
        </div>
        <p className="muted-text small">
          Статус: <strong>{connectionState}</strong>
        </p>
        <p className="muted-text small">
          Сессия:{" "}
          <strong>{sessionRunning ? "запущена" : "ожидает запуска"}</strong>
        </p>
        {sessionInfo.sessionCode ? (
          <p className="muted-text small">
            Код текущей сессии: <code>{sessionInfo.sessionCode}</code>
          </p>
        ) : null}
        <div className="connection-helpers">
            <button
              type="button"
              className="button button-secondary"
              onClick={requestStatus}
              disabled={!isConnected}
            >
              Запросить phase_status
            </button>
            <button
              type="button"
              className="button button-secondary"
              onClick={sendHeartbeat}
              disabled={!isConnected}
            >
              Heartbeat
            </button>
            <button
              type="button"
              className="button button-primary"
              onClick={startSession}
              disabled={!isConnected || sessionRunning}
            >
              Запустить сессию
            </button>
            <button
              type="button"
              className="button button-primary"
              onClick={handleSkip}
              disabled={!isConnected || !sessionRunning}
            >
              Skip фазу
            </button>
          </div>
          {lastControlAck ? (
            <p className="muted-text small">
              Команда {lastControlAck.command}:{" "}
              {lastControlAck.started ? "выполнена" : "отклонена"}
            </p>
          ) : null}
        {(serverError || wsError) && (
          <div className="error-banner" role="alert">
            {serverError || wsError}
          </div>
        )}
        {lastAck ? (
          <p className="muted-text small">
            Последний ACK: {lastAck.action} (phase {lastAck.phase})
          </p>
        ) : null}
      </section>

      <section className="surface-card meta-panel">
        <div className="panel-heading">
          <p className="eyebrow">Фаза</p>
          <h3>Текущее состояние</h3>
        </div>
        <div className="meta-grid">
          {sessionMeta.map((item) => (
            <div key={item.label} className="meta-cell">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
        {lastStatus ? (
          <p className="muted-text small">
            Последний phase_status: {lastStatus.phase} (остаток{" "}
            {formatSeconds(lastStatus.remaining_seconds)})
          </p>
        ) : null}
      </section>

      <section className="surface-card analytics-panel">
        <div className="panel-heading">
          <p className="eyebrow">Игроки</p>
          <h3>Показатели месяца</h3>
        </div>
        {analyticsPlayers.length === 0 ? (
          <p className="muted-text">Нет данных — дождитесь welcome или отчёта.</p>
        ) : (
          <div className="table-scroll">
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Cash</th>
                  <th>RMs</th>
                  <th>FGs</th>
                  <th>Factories</th>
                  <th>Loans</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {analyticsPlayers.map((player) => {
                  const isBankrupt =
                    player.bankrupt || bankruptIds.includes(player.player_id);
                  return (
                    <tr
                      key={player.player_id}
                      className={isBankrupt ? "is-bankrupt" : undefined}
                    >
                      <td>
                        {player.player_id}
                        {player.player_id === userId ? " (you)" : ""}
                      </td>
                      <td>{player.money.toFixed(2)}</td>
                      <td>{player.raw_materials}</td>
                      <td>{player.finished_goods}</td>
                      <td>{player.factories}</td>
                      <td>{player.active_loans}</td>
                      <td>{isBankrupt ? "Bankrupt" : "Active"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="action-grid">
        <article className="surface-card action-card">
          <div className="panel-heading">
            <p className="eyebrow">Phase BUY</p>
            <h3>Заявка на покупку РМ</h3>
          </div>
          <form onSubmit={handleBuySubmit} className="stacked-form">
            <label className="form-field">
              <span>Quantity</span>
              <input
                type="number"
                value={buyForm.quantity}
                onChange={(event) =>
                  setBuyForm((form) => ({
                    ...form,
                    quantity: event.target.value,
                  }))
                }
                disabled={!isConnected}
              />
            </label>
            <label className="form-field">
              <span>Price per unit</span>
              <input
                type="number"
                value={buyForm.price}
                onChange={(event) =>
                  setBuyForm((form) => ({
                    ...form,
                    price: event.target.value,
                  }))
                }
                disabled={!isConnected}
              />
            </label>
            <div className="form-actions">
              <button
                type="submit"
                className="button button-primary"
                disabled={
                  !isConnected || !sessionRunning || currentPhase !== "buy"
                }
              >
                Отправить bid
              </button>
            </div>
          </form>
        </article>

        <article className="surface-card action-card">
          <div className="panel-heading">
            <p className="eyebrow">Phase PRODUCTION</p>
            <h3>План производства</h3>
          </div>
          <form onSubmit={handleProductionSubmit} className="stacked-form">
            <label className="form-field">
              <span>Basic factories</span>
              <input
                type="number"
                value={productionForm.basic}
                onChange={(event) =>
                  setProductionForm((form) => ({
                    ...form,
                    basic: event.target.value,
                  }))
                }
                disabled={!isConnected}
              />
            </label>
            <label className="form-field">
              <span>Automated factories</span>
              <input
                type="number"
                value={productionForm.auto}
                onChange={(event) =>
                  setProductionForm((form) => ({
                    ...form,
                    auto: event.target.value,
                  }))
                }
                disabled={!isConnected}
              />
            </label>
            <div className="form-actions">
              <button
                type="submit"
                className="button button-primary"
                disabled={
                  !isConnected ||
                  !sessionRunning ||
                  currentPhase !== "production"
                }
              >
                Запланировать
              </button>
            </div>
          </form>
        </article>

        <article className="surface-card action-card">
          <div className="panel-heading">
            <p className="eyebrow">Phase SELL</p>
            <h3>Заявка на продажу ФГ</h3>
          </div>
          <form onSubmit={handleSellSubmit} className="stacked-form">
            <label className="form-field">
              <span>Quantity</span>
              <input
                type="number"
                value={sellForm.quantity}
                onChange={(event) =>
                  setSellForm((form) => ({
                    ...form,
                    quantity: event.target.value,
                  }))
                }
                disabled={!isConnected}
              />
            </label>
            <label className="form-field">
              <span>Price per unit</span>
              <input
                type="number"
                value={sellForm.price}
                onChange={(event) =>
                  setSellForm((form) => ({
                    ...form,
                    price: event.target.value,
                  }))
                }
                disabled={!isConnected}
              />
            </label>
            <div className="form-actions">
              <button
                type="submit"
                className="button button-primary"
                disabled={
                  !isConnected || !sessionRunning || currentPhase !== "sell"
                }
              >
                Отправить bid
              </button>
            </div>
          </form>
        </article>

        <article className="surface-card action-card">
          <div className="panel-heading">
            <p className="eyebrow">Phase LOANS</p>
            <h3>Решение по займам</h3>
          </div>
          <form onSubmit={handleLoanSubmit} className="stacked-form">
            <label className="form-field">
              <span>Loan slot</span>
              <input
                type="number"
                value={loanForm.slot}
                min="0"
                max="1"
                onChange={(event) =>
                  setLoanForm((form) => ({
                    ...form,
                    slot: event.target.value,
                  }))
                }
                disabled={!isConnected}
              />
            </label>
            <label className="form-field">
              <span>Decision</span>
              <select
                value={loanForm.decision}
                onChange={(event) =>
                  setLoanForm((form) => ({
                    ...form,
                    decision: event.target.value,
                  }))
                }
                disabled={!isConnected}
              >
                {LOAN_DECISIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-actions">
              <button
                type="submit"
                className="button button-primary"
                disabled={
                  !isConnected || !sessionRunning || currentPhase !== "loans"
                }
              >
                Обновить слот
              </button>
            </div>
          </form>
        </article>

        <article className="surface-card action-card">
          <div className="panel-heading">
            <p className="eyebrow">Phase CONSTRUCTION</p>
            <h3>Строительство / апгрейды</h3>
          </div>
          <form onSubmit={handleConstructionSubmit} className="stacked-form">
            <label className="form-field">
              <span>Project</span>
              <select
                value={constructionChoice}
                onChange={(event) => setConstructionChoice(event.target.value)}
                disabled={!isConnected}
              >
                {CONSTRUCTION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-actions">
              <button
                type="submit"
                className="button button-primary"
                disabled={
                  !isConnected ||
                  !sessionRunning ||
                  currentPhase !== "construction"
                }
              >
                Отправить запрос
              </button>
            </div>
          </form>
        </article>
      </section>

      <section className="surface-card log-panel">
        <div className="panel-heading">
          <p className="eyebrow">Журнал фаз</p>
          <h3>Последние отчёты</h3>
        </div>
        {reports.length === 0 ? (
          <p className="muted-text">Нет отчётов. Дождитесь завершения фазы.</p>
        ) : (
          <ul className="log-list">
            {reports.map((report) => (
              <li key={`${report.phase}-${report.completed_at}`}>
                <strong>
                  Месяц {report.month}, фаза {PHASE_LABELS[report.phase] ?? report.phase}
                </strong>
                <ul className="journal-list">
                  {report.journal.map((entry, index) => (
                    <li key={`${report.phase}-${index}`}>
                      <span className="log-timestamp">
                        {new Date(report.completed_at).toLocaleTimeString()}
                      </span>
                      <p>{entry.message}</p>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="surface-card seniority-panel">
        <div className="panel-heading">
          <p className="eyebrow">Seniority</p>
          <h3>Порядок и броски</h3>
        </div>
        {seniorityHistory.length === 0 ? (
          <p className="muted-text">Данные появятся после welcome.</p>
        ) : (
          <ul className="structures-list">
            {seniorityHistory.map((entry) => (
              <li key={entry.month}>
                Месяц {entry.month}: {entry.order.join(" → ")}
              </li>
            ))}
          </ul>
        )}
        {tieBreakLog.length > 0 ? (
          <div className="tie-log">
            <p className="muted-text small">Броски:</p>
            <ul className="structures-list">
              {tieBreakLog.map((entry) => (
                <li key={`${entry.attempt}-${entry.player_id}`}>
                  Попытка {entry.attempt}: игрок {entry.player_id} выкинул{" "}
                  {entry.value}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </section>
  );
}
