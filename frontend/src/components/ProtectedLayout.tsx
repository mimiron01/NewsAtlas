import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../context/AuthContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { useTheme } from "../hooks/useTheme";
import LanguageSwitcher from "./LanguageSwitcher";
import { HomeIcon, MenuIcon, MoonIcon, SignalsIcon, SunIcon, TargetsIcon } from "./icons/NavIcons";
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
      <button
        type="button"
        className="nav-toggle"
        aria-label={t("nav:toggleNav")}
        onClick={() => setIsNavOpen((open) => !open)}
      >
        <MenuIcon />
      </button>
      {isNavOpen && (
        <div className="nav-backdrop" onClick={() => setIsNavOpen(false)} aria-hidden="true" />
      )}
      <aside className={`sidebar ${isNavOpen ? "open" : ""}`}>
        <h1 className="brand">{t("nav:brand")}</h1>
        <nav>
          <NavLink to="/" end>
            <HomeIcon /> {t("nav:links.dashboard")}
          </NavLink>
          <NavLink to="/signals">
            <SignalsIcon /> {t("nav:links.signals")}
          </NavLink>
          <NavLink to="/settings/targets">
            <TargetsIcon /> {t("nav:links.targets")}
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <button type="button" className="theme-toggle" onClick={cycleTheme}>
            {theme === "dark" ? <MoonIcon /> : <SunIcon />}
            {t(`nav:theme.${theme}`)}
          </button>
          <LanguageSwitcher />
          <ProfileMenu user={user} isAdmin={isAdmin} onLogout={logout} />
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
