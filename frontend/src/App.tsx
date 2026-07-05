import { Navigate, Route, Routes } from "react-router-dom";

import ProtectedLayout from "./components/ProtectedLayout";
import { useAuth } from "./context/AuthContext";
import AIUsage from "./pages/AIUsage";
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
        <Route path="/settings/profile" element={<SettingsProfile />} />
        <Route path="/settings/targets" element={<SettingsTargets />} />
        <Route path="/settings/ai-usage" element={<AIUsage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
