import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { DomainPrecisionStat } from "../../api/types";

/**
 * Which publishers are producing signals worth keeping, and which are only producing
 * triage-outs and dismissals — with a one-click route from that observation to a
 * denylist entry, so noticing a bad source and acting on it aren't separate chores.
 */
export default function SourcePrecisionPanel({
  onBlockDomain,
  blockedDomains,
}: {
  onBlockDomain: (sourceName: string) => void;
  blockedDomains: string[];
}) {
  const { t } = useTranslation("settings");
  const [stats, setStats] = useState<DomainPrecisionStat[] | null>(null);

  useEffect(() => {
    // Failure here is not worth surfacing: this panel is advisory, and an error toast on
    // a settings page the user opened for something else would be pure noise.
    api
      .get<DomainPrecisionStat[]>("/news-diagnostics/source-precision")
      .then(setStats)
      .catch(() => setStats([]));
  }, []);

  if (stats === null) return null;

  const suggested = stats.filter((row) => row.denylist_suggested);
  if (suggested.length === 0) {
    return (
      <section className="settings-section">
        <h3>{t("sources.precision.title")}</h3>
        <p className="field-hint">{t("sources.precision.empty")}</p>
      </section>
    );
  }

  return (
    <section className="settings-section">
      <h3>{t("sources.precision.title")}</h3>
      <p className="field-hint">{t("sources.precision.hint")}</p>
      <table className="news-usage-table">
        <thead>
          <tr>
            <th>{t("sources.precision.articles")}</th>
            <th>{t("sources.precision.kept")}</th>
            <th>{t("sources.precision.discarded")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {suggested.map((row) => {
            // The denylist stores domains, but these stats are grouped by publisher name
            // (which is what a Google News redirect URL can tell us). Offer the name
            // lowercased as a starting point and let the admin correct it.
            const candidate = row.source_name.toLowerCase().replace(/\s+/g, "");
            const alreadyBlocked = blockedDomains.some((domain) => domain.includes(candidate));
            return (
              <tr key={row.source_name}>
                <td>
                  <strong>{row.source_name}</strong>
                  <br />
                  <span className="field-hint">{row.articles}</span>
                </td>
                <td>{row.signals_kept}</td>
                <td>
                  {row.triaged_out + row.dismissed} ({Math.round(row.waste_ratio * 100)}%)
                </td>
                <td>
                  {alreadyBlocked ? (
                    <span className="field-hint">{t("sources.precision.blocked")}</span>
                  ) : (
                    <button type="button" onClick={() => onBlockDomain(candidate)}>
                      {t("sources.precision.block")}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
