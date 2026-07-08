import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

interface SetupChecklistProps {
  hasCompanyProfile: boolean;
  hasTargetCompany: boolean;
  hasSignals: boolean;
}

export default function SetupChecklist({
  hasCompanyProfile,
  hasTargetCompany,
  hasSignals,
}: SetupChecklistProps) {
  const { t } = useTranslation("common");

  const steps = [
    {
      done: hasCompanyProfile,
      label: t("setupChecklist.companyProfile.label"),
      body: t("setupChecklist.companyProfile.body"),
      to: "/settings/profile",
      linkLabel: t("setupChecklist.companyProfile.linkLabel"),
    },
    {
      done: hasTargetCompany,
      label: t("setupChecklist.targetCompany.label"),
      body: t("setupChecklist.targetCompany.body"),
      to: "/settings/targets",
      linkLabel: t("setupChecklist.targetCompany.linkLabel"),
    },
    {
      done: hasSignals,
      label: t("setupChecklist.firstSignals.label"),
      body: t("setupChecklist.firstSignals.body"),
      to: null,
      linkLabel: null,
    },
  ];

  return (
    <div className="panel-card setup-checklist">
      <h3>{t("setupChecklist.title")}</h3>
      <ul className="checklist-steps">
        {steps.map((step) => (
          <li key={step.label} className={step.done ? "done" : ""}>
            <span className="checklist-mark" aria-hidden="true">
              {step.done ? "✓" : ""}
            </span>
            <div>
              <div className="checklist-label">{step.label}</div>
              <div className="subtitle">{step.body}</div>
              {step.to && !step.done && (
                <Link to={step.to} className="link-button">
                  {step.linkLabel} →
                </Link>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
