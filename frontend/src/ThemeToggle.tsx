// ThemeToggle.tsx — üst toolbar'daki basit aydınlık/karanlık geçiş butonu
import type { ThemeId } from "./useTheme";

interface Props {
  theme: ThemeId;
  onToggle: () => void;
}

export function ThemeToggle({ theme, onToggle }: Props) {
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onToggle}
      title={isDark ? "Aydınlık moda geç" : "Karanlık moda geç"}
      aria-label={isDark ? "Aydınlık moda geç" : "Karanlık moda geç"}
    >
      <span className="theme-toggle-icon">{isDark ? "☾" : "☀"}</span>
      <span className="theme-toggle-label">{isDark ? "Karanlık" : "Aydınlık"}</span>
    </button>
  );
}
