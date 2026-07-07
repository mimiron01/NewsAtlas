import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { useTheme } from "../hooks/useTheme";
import { HomeIcon, MenuIcon, MoonIcon, SignalsIcon, SunIcon, TargetsIcon } from "./icons/NavIcons";
import ProfileMenu from "./ProfileMenu";

const THEME_LABEL: Record<string, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

export default function ProtectedLayout() {
  const { user, isLoading, logout } = useAuth();
  const isAdmin = useIsAdmin();
  const { theme, cycleTheme } = useTheme();
  const [isNavOpen, setIsNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setIsNavOpen(false);
  }, [location.pathname]);

  if (isLoading) {
    return <p className="centered">Loading...</p>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="app-shell">
      <button
        type="button"
        className="nav-toggle"
        aria-label="Toggle navigation"
        onClick={() => setIsNavOpen((open) => !open)}
      >
        <MenuIcon />
      </button>
      {isNavOpen && (
        <div className="nav-backdrop" onClick={() => setIsNavOpen(false)} aria-hidden="true" />
      )}
      <aside className={`sidebar ${isNavOpen ? "open" : ""}`}>
        <h1 className="brand">NewsAtlas</h1>
        <nav>
          <NavLink to="/" end>
            <HomeIcon /> Dashboard
          </NavLink>
          <NavLink to="/signals">
            <SignalsIcon /> Signals
          </NavLink>
          <NavLink to="/settings/targets">
            <TargetsIcon /> My companies
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <button type="button" className="theme-toggle" onClick={cycleTheme}>
            {theme === "dark" ? <MoonIcon /> : <SunIcon />}
            {THEME_LABEL[theme]} theme
          </button>
          <ProfileMenu user={user} isAdmin={isAdmin} onLogout={logout} />
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
