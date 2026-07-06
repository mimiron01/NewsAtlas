import { useAuth } from "../context/AuthContext";

export function useIsAdmin(): boolean {
  const { user } = useAuth();
  return user?.role === "admin";
}
