import { FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { TargetCompany } from "../api/types";

export default function SettingsTargets() {
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("");
  const [industry, setIndustry] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function loadCompanies() {
    api
      .get<TargetCompany[]>("/target-companies")
      .then(setCompanies)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load companies"));
  }

  useEffect(loadCompanies, []);

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await api.post<TargetCompany>("/target-companies", {
        name,
        keywords: keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        industry: industry || null,
      });
      setName("");
      setKeywords("");
      setIndustry("");
      loadCompanies();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add company");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function toggleActive(company: TargetCompany) {
    await api.patch(`/target-companies/${company.id}`, { is_active: !company.is_active });
    loadCompanies();
  }

  async function remove(company: TargetCompany) {
    await api.delete(`/target-companies/${company.id}`);
    loadCompanies();
  }

  return (
    <div>
      <form className="panel-card" onSubmit={handleAdd}>
        <h2>Target companies</h2>
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
          Keywords / aliases (comma separated)
          <input value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        </label>
        {error && <p className="error-text">{error}</p>}
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
                {company.keywords.length > 0 && (
                  <div className="keywords">{company.keywords.join(", ")}</div>
                )}
              </div>
              <div className="actions">
                <button type="button" onClick={() => toggleActive(company)}>
                  {company.is_active ? "Pause" : "Resume"}
                </button>
                <button type="button" className="danger" onClick={() => remove(company)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
