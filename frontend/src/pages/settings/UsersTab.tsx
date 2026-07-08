import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../../api/client";
import type { AdminUser, TargetCompany } from "../../api/types";
import TagInput from "../../components/TagInput";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";

export default function UsersTab() {
  const { t } = useTranslation("settings");
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
      .catch((err) => showToast(err instanceof ApiError ? err.message : t("users.loadFailed"), "error"));
  }

  useEffect(loadUsers, [t]);

  async function toggleRole(targetUser: AdminUser) {
    const nextRole = targetUser.role === "admin" ? "user" : "admin";
    setPendingUserId(targetUser.id);
    try {
      await api.patch(`/admin/users/${targetUser.id}/role`, { role: nextRole });
      showToast(
        nextRole === "admin"
          ? t("users.roleChangedToAdmin", { name: targetUser.name })
          : t("users.roleChangedToUser", { name: targetUser.name }),
        "success"
      );
      loadUsers();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("users.roleUpdateFailed"), "error");
    } finally {
      setPendingUserId(null);
    }
  }

  async function handleAssign(event: FormEvent) {
    event.preventDefault();
    if (!assignUserId) {
      showToast(t("users.chooseUserFirst"), "error");
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
      showToast(t("users.companyAssigned"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("users.assignFailed"), "error");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div>
      <div className="panel-card">
        <h2>{t("users.title")}</h2>
        <p className="subtitle">{t("users.subtitle")}</p>
        <ul className="target-list">
          {users.map((targetUser) => {
            const isSelf = targetUser.id === currentUser?.id;
            return (
              <li key={targetUser.id}>
                <div>
                  <strong>{targetUser.name}</strong>
                  <span className="tag">{t(`users.roleLabel.${targetUser.role}`)}</span>
                  <div className="keywords">{targetUser.email}</div>
                </div>
                <div className="actions">
                  <button
                    type="button"
                    disabled={pendingUserId === targetUser.id}
                    onClick={() => toggleRole(targetUser)}
                    title={isSelf && targetUser.role === "admin" ? t("users.lastAdminHint") : undefined}
                  >
                    {targetUser.role === "admin" ? t("users.demote") : t("users.promote")}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <form className="panel-card" onSubmit={handleAssign}>
        <h3>{t("users.assignTitle")}</h3>
        <p className="subtitle">{t("users.assignSubtitle")}</p>
        <label>
          {t("users.userLabel")}
          <select value={assignUserId} onChange={(e) => setAssignUserId(e.target.value)} required>
            <option value="" disabled>
              {t("users.chooseUserPlaceholder")}
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
            {t("targets.companyName")}
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            {t("targets.industryOptional")}
            <input value={industry} onChange={(e) => setIndustry(e.target.value)} />
          </label>
        </div>
        <label>
          {t("targets.keywords")}
          <TagInput tags={keywords} onChange={setKeywords} placeholder={t("targets.keywordsPlaceholder")} />
        </label>
        <button type="submit" disabled={isSubmitting}>
          {t("users.assignButton")}
        </button>
      </form>
    </div>
  );
}
