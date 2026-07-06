import { Navigate, Route, Routes } from "react-router-dom";

import ProtectedLayout from "./components/ProtectedLayout";
import RequireAdmin from "./components/RequireAdmin";
import { useAuth } from "./context/AuthContext";
import AdminUsers from "./pages/AdminUsers";
import Login from "./pages/Login";
import SettingsProfile from "./pages/SettingsProfile";
import SettingsTargets from "./pages/SettingsTargets";
import SignalDetail from "./pages/SignalDetail";
import SignalsFeed from "./pages/SignalsFeed";

export default function App() {
  const { user, isLoading } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={!isLoading && user ? <Navigate to="/" replace /> : <Login />}
      />
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<SignalsFeed />} />
        <Route path="/signals/:signalId" element={<SignalDetail />} />
        <Route path="/settings/targets" element={<SettingsTargets />} />
        <Route element={<RequireAdmin />}>
          <Route path="/settings/profile" element={<SettingsProfile />} />
          <Route path="/admin/users" element={<AdminUsers />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
