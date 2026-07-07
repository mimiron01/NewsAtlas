import { Navigate, Route, Routes } from "react-router-dom";

import ProtectedLayout from "./components/ProtectedLayout";
import RequireAdmin from "./components/RequireAdmin";
import { useAuth } from "./context/AuthContext";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import AITab from "./pages/settings/AITab";
import CompanyTab from "./pages/settings/CompanyTab";
import LogsTab from "./pages/settings/LogsTab";
import SettingsLayout from "./pages/settings/SettingsLayout";
import SourcesTab from "./pages/settings/SourcesTab";
import UsageTab from "./pages/settings/UsageTab";
import UsersTab from "./pages/settings/UsersTab";
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
        <Route path="/" element={<Dashboard />} />
        <Route path="/signals" element={<SignalsFeed />} />
        <Route path="/signals/:signalId" element={<SignalDetail />} />
        <Route path="/settings/targets" element={<SettingsTargets />} />
        <Route element={<RequireAdmin />}>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route index element={<Navigate to="company" replace />} />
            <Route path="company" element={<CompanyTab />} />
            <Route path="sources" element={<SourcesTab />} />
            <Route path="ai" element={<AITab />} />
            <Route path="usage" element={<UsageTab />} />
            <Route path="users" element={<UsersTab />} />
            <Route path="logs" element={<LogsTab />} />
          </Route>
          {/* Old paths, kept working for existing bookmarks/history */}
          <Route path="/settings/profile" element={<Navigate to="/settings/company" replace />} />
          <Route path="/settings/ai-usage" element={<Navigate to="/settings/usage" replace />} />
          <Route path="/admin/users" element={<Navigate to="/settings/users" replace />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
