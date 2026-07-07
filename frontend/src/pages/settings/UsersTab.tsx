import { FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../../api/client";
import type { AdminUser, TargetCompany } from "../../api/types";
import TagInput from "../../components/TagInput";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";

export default function UsersTab() {
  const { showToast } = useToast();
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [pendingUserId, setPendingUserId] = useState<string | null>(null);

  const [assignUserId, setAssignUserId] = useState("");
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [industry, setIndustry] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function loadUsers() {
    api
      .get<AdminUser[]>("/admin/users")
      .then(setUsers)
      .catch((err) => showToast(err instanceof ApiError ? err.message : "Failed to load users", "error"));
  }

  useEffect(loadUsers, []);

  async function toggleRole(targetUser: AdminUser) {
    const nextRole = targetUser.role === "admin" ? "user" : "admin";
    setPendingUserId(targetUser.id);
    try {
      await api.patch(`/admin/users/${targetUser.id}/role`, { role: nextRole });
      showToast(`${targetUser.name} is now ${nextRole === "admin" ? "an admin" : "a regular user"}.`, "success");
      loadUsers();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to update role", "error");
    } finally {
      setPendingUserId(null);
    }
  }

  async function handleAssign(event: FormEvent) {
    event.preventDefault();
    if (!assignUserId) {
      showToast("Choose a user to assign this company to.", "error");
      return;
    }
    setIsSubmitting(true);
    try {
      await api.post<TargetCompany>(`/admin/users/${assignUserId}/companies`, {
        name,
        keywords,
        industry: industry || null,
      });
      setName("");
      setKeywords([]);
      setIndustry("");
      showToast("Company assigned.", "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to assign company", "error");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div>
      <div className="panel-card">
        <h2>Users</h2>
        <p className="subtitle">Promote or demote users. Admins manage workspace settings and can assign companies to any user.</p>
        <ul className="target-list">
          {users.map((targetUser) => {
            const isSelf = targetUser.id === currentUser?.id;
            return (
              <li key={targetUser.id}>
                <div>
                  <strong>{targetUser.name}</strong>
                  <span className="tag">{targetUser.role}</span>
                  <div className="keywords">{targetUser.email}</div>
                </div>
                <div className="actions">
                  <button
                    type="button"
                    disabled={pendingUserId === targetUser.id}
                    onClick={() => toggleRole(targetUser)}
                    title={isSelf && targetUser.role === "admin" ? "You may be the last remaining admin" : undefined}
                  >
                    {targetUser.role === "admin" ? "Demote to user" : "Promote to admin"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <form className="panel-card" onSubmit={handleAssign}>
        <h3>Assign a company to a user</h3>
        <p className="subtitle">
          Select an existing catalog company by typing its exact name, or a new name to create it.
          The user sees it in their dashboard immediately — no action needed from them.
        </p>
        <label>
          User
          <select value={assignUserId} onChange={(e) => setAssignUserId(e.target.value)} required>
            <option value="" disabled>
              Choose a user...
            </option>
            {users.map((targetUser) => (
              <option key={targetUser.id} value={targetUser.id}>
                {targetUser.name} ({targetUser.email})
              </option>
            ))}
          </select>
        </label>
        <div className="field-row">
          <label>
            Company name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Industry (optional)
            <input value={industry} onChange={(e) => setIndustry(e.target.value)} />
          </label>
        </div>
        <label>
          Keywords / aliases
          <TagInput tags={keywords} onChange={setKeywords} placeholder="Type a keyword and press Enter" />
        </label>
        <button type="submit" disabled={isSubmitting}>
          Assign company
        </button>
      </form>
    </div>
  );
}
