import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../context/AuthContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { useTheme } from "../hooks/useTheme";
import { HomeIcon, MenuIcon, SignalsIcon, TargetsIcon, ThemeIcon } from "./icons/NavIcons";
import ProfileMenu from "./ProfileMenu";

export default function ProtectedLayout() {
  const { user, isLoading, logout } = useAuth();
  const isAdmin = useIsAdmin();
  const { theme, cycleTheme } = useTheme();
  const [isNavOpen, setIsNavOpen] = useState(false);
  const location = useLocation();
  const { t } = useTranslation(["nav", "common"]);

  useEffect(() => {
    setIsNavOpen(false);
  }, [location.pathname]);

  if (isLoading) {
    return <p className="centered">{t("common:loading")}</p>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="app-shell">
      <header className="navbar">
        <div className="navbar-center">
          <h1 className="brand">{t("nav:brand")}</h1>
          <button
            type="button"
            className="nav-toggle"
            aria-label={t("nav:toggleNav")}
            aria-expanded={isNavOpen}
            onClick={() => setIsNavOpen((open) => !open)}
          >
            <MenuIcon />
          </button>
          <nav className={`navbar-links ${isNavOpen ? "open" : ""}`}>
            <NavLink to="/" end>
              <HomeIcon /> {t("nav:links.dashboard")}
            </NavLink>
            <NavLink to="/signals">
              <SignalsIcon /> {t("nav:links.signals")}
            </NavLink>
            <NavLink to="/settings/targets">
              <TargetsIcon /> {t("nav:links.targets")}
            </NavLink>
            <NavLink to="/themes">
              <ThemeIcon /> {t("nav:links.themes")}
            </NavLink>
          </nav>
        </div>
        <div className="navbar-actions">
          <ProfileMenu user={user} isAdmin={isAdmin} onLogout={logout} theme={theme} cycleTheme={cycleTheme} />
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
