import { NavLink, Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function ProtectedLayout() {
  const { user, isLoading, logout } = useAuth();

  if (isLoading) {
    return <p className="centered">Loading...</p>;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1 className="brand">NewsAtlas</h1>
        <nav>
          <NavLink to="/" end>
            Signals
          </NavLink>
          <NavLink to="/settings/profile">Company profile</NavLink>
          <NavLink to="/settings/targets">Target companies</NavLink>
        </nav>
        <div className="sidebar-footer">
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
