import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../context/AuthContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useTheme } from "../hooks/useTheme";
import { HomeIcon, MenuIcon, TargetsIcon, ThemeIcon } from "./icons/NavIcons";
import ProfileMenu from "./ProfileMenu";

export default function ProtectedLayout() {
  const { user, isLoading, logout } = useAuth();
  const isAdmin = useIsAdmin();
  const { theme, cycleTheme } = useTheme();
  const [isNavOpen, setIsNavOpen] = useState(false);
  const location = useLocation();
  const { t } = useTranslation(["nav", "common"]);
  // Below 720px the nav collapses via CSS (max-height: 0); above it, the links are
  // always visible regardless of isNavOpen. Only remove collapsed links from tab order
  // on the width where they're actually collapsed — inert unconditionally on !isNavOpen
  // would make the desktop nav permanently unfocusable, since isNavOpen only ever
  // toggles from the mobile hamburger.
  const isMobileNav = useMediaQuery("(max-width: 720px)");

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
          <nav
            className={`navbar-links ${isNavOpen ? "open" : ""}`}
            inert={isMobileNav && !isNavOpen ? true : undefined}
          >
            <NavLink to="/" end>
              <HomeIcon /> {t("nav:links.dashboard")}
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
