"use client";

const hasWindow = () =>
  typeof window !== "undefined" && typeof window.localStorage !== "undefined";

export function readJson(key, fallback = null) {
  if (!hasWindow()) {
    return fallback;
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }

    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function writeJson(key, value) {
  if (!hasWindow()) {
    return value;
  }

  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore write errors (e.g., storage quota exceeded).
  }

  return value;
}

export function removeKey(key) {
  if (!hasWindow()) {
    return;
  }

  try {
    window.localStorage.removeItem(key);
  } catch {
    // Ignore removal errors.
  }
}

export function clearAll() {
  if (!hasWindow()) {
    return;
  }

  window.localStorage.clear();
}
