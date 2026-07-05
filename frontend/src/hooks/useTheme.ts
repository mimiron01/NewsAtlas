import { useCallback, useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "newsatlas_theme";

function applyTheme(theme: Theme) {
  if (theme === "system") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? "system"
  );

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const cycleTheme = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === "system" ? "light" : prev === "light" ? "dark" : "system";
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return { theme, cycleTheme };
}
