import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { useTheme } from "../hooks/useTheme";
import { MenuIcon, MoonIcon, ProfileIcon, SignalsIcon, SunIcon, TargetsIcon, UsageIcon, UsersIcon } from "./icons/NavIcons";

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
            <SignalsIcon /> Signals
          </NavLink>
          <NavLink to="/settings/targets">
            <TargetsIcon /> My companies
          </NavLink>
          {isAdmin && (
            <>
              <NavLink to="/settings/profile">
                <ProfileIcon /> Company profile
              </NavLink>
              <NavLink to="/settings/ai-usage">
                <UsageIcon /> AI usage
              </NavLink>
              <NavLink to="/admin/users">
                <UsersIcon /> Users
              </NavLink>
            </>
          )}
        </nav>
        <div className="sidebar-footer">
          <button type="button" className="theme-toggle" onClick={cycleTheme}>
            {theme === "dark" ? <MoonIcon /> : <SunIcon />}
            {THEME_LABEL[theme]} theme
          </button>
          <span>{user.name}</span>
          <button type="button" className="link-button" onClick={logout}>
            Log out
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
