import { FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { TargetCompany } from "../api/types";
import TagInput from "../components/TagInput";
import { useToast } from "../context/ToastContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

export default function SettingsTargets() {
  usePageTitle("My companies");
  const { showToast } = useToast();
  const isAdmin = useIsAdmin();
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [industry, setIndustry] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  function loadCompanies() {
    api
      .get<TargetCompany[]>("/target-companies")
      .then(setCompanies)
      .catch((err) => showToast(err instanceof ApiError ? err.message : "Failed to load companies", "error"));
  }

  useEffect(loadCompanies, []);

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await api.post<TargetCompany>("/target-companies", {
        name,
        keywords,
        industry: industry || null,
      });
      setName("");
      setKeywords([]);
      setIndustry("");
      showToast("Target company added.", "success");
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to add company", "error");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function toggleActive(company: TargetCompany) {
    setPendingId(company.id);
    try {
      await api.patch(`/target-companies/${company.id}`, { is_active: !company.is_active });
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to update company", "error");
    } finally {
      setPendingId(null);
    }
  }

  async function toggleMute(company: TargetCompany) {
    setPendingId(company.id);
    try {
      await api.post(`/target-companies/${company.id}/mute`);
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to update company", "error");
    } finally {
      setPendingId(null);
    }
  }

  async function remove(company: TargetCompany) {
    setPendingId(company.id);
    try {
      await api.delete(`/target-companies/${company.id}`);
      showToast(
        isAdmin ? `Deleted "${company.name}".` : `Unfollowed "${company.name}".`,
        "success"
      );
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to remove company", "error");
    } finally {
      setPendingId(null);
      setConfirmingId(null);
    }
  }

  function removeLabel(): string {
    return isAdmin ? "Delete" : "Unfollow";
  }

  function confirmCopy(company: TargetCompany): string {
    if (isAdmin) {
      return `This permanently deletes "${company.name}" and all its signals for every user. Continue?`;
    }
    if (company.follower_count <= 1) {
      return `You're the only follower — unfollowing "${company.name}" removes it (and its signals) for everyone. Continue?`;
    }
    return `Unfollow "${company.name}"? Other users tracking it keep seeing it.`;
  }

  return (
    <div>
      <form className="panel-card" onSubmit={handleAdd}>
        <h2>My companies</h2>
        <p className="subtitle">
          Add the companies you want news signals for. Keywords/aliases help match more articles.
        </p>
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
          <TagInput
            tags={keywords}
            onChange={setKeywords}
            placeholder="Type a keyword and press Enter"
          />
        </label>
        <button type="submit" disabled={isSubmitting}>
          Add target company
        </button>
      </form>

      <div className="panel-card">
        <h3>Tracked companies ({companies.length})</h3>
        {companies.length === 0 && <p className="subtitle">No target companies yet.</p>}
        <ul className="target-list">
          {companies.map((company) => (
            <li key={company.id} className={company.is_active ? "" : "inactive"}>
              <div>
                <strong>{company.name}</strong>
                {company.industry && <span className="tag">{company.industry}</span>}
                {company.is_muted && <span className="tag">Muted</span>}
                {company.keywords.length > 0 && (
                  <div className="keywords">{company.keywords.join(", ")}</div>
                )}
              </div>
              <div className="actions">
                <button
                  type="button"
                  disabled={pendingId === company.id}
                  onClick={() => toggleMute(company)}
                >
                  {company.is_muted ? "Unmute" : "Mute"}
                </button>
                <button
                  type="button"
                  disabled={pendingId === company.id}
                  onClick={() => toggleActive(company)}
                >
                  {company.is_active ? "Pause" : "Resume"}
                </button>
                {confirmingId === company.id ? (
                  <>
                    <button
                      type="button"
                      className="danger"
                      disabled={pendingId === company.id}
                      onClick={() => remove(company)}
                    >
                      Confirm {removeLabel().toLowerCase()}
                    </button>
                    <button type="button" onClick={() => setConfirmingId(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="danger"
                    title={confirmCopy(company)}
                    onClick={() => setConfirmingId(company.id)}
                  >
                    {removeLabel()}
                  </button>
                )}
              </div>
              {confirmingId === company.id && <p className="subtitle">{confirmCopy(company)}</p>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
