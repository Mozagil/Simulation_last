// useTheme.ts — tema state'i (aydınlık/karanlık) + localStorage + <html data-theme>
import { useCallback, useEffect, useState } from "react";

export type ThemeId = "light" | "dark";

const STORAGE_KEY = "cae.theme";
const DEFAULT: ThemeId = "light";

function readStored(): ThemeId {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" ? v : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

/** Tema uygula: <html data-theme="..."> + kaydet. */
export function applyTheme(id: ThemeId) {
  document.documentElement.setAttribute("data-theme", id);
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // localStorage kapalıysa (gizli sekme vb.) sessizce yok say.
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeId>(readStored);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((id: ThemeId) => setThemeState(id), []);
  const toggleTheme = useCallback(
    () => setThemeState((prev) => (prev === "light" ? "dark" : "light")),
    [],
  );

  return { theme, setTheme, toggleTheme };
}

/**
 * Tema token'ını JS tarafında oku — three.js sahne rengi, colorbar vb. için.
 *   const bg = cssVar("--scene-bg");            // "#0a0b0d"
 *   scene.background = new THREE.Color(bg);
 */
export function cssVar(name: string, el: Element = document.documentElement): string {
  return getComputedStyle(el).getPropertyValue(name).trim();
}
