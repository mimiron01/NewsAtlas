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
      // Satisfied by either a tracked company or a tracked topic — both are fetchable
      // work, so both routes out of this step are offered.
      done: hasTargetCompany,
      label: t("setupChecklist.targetCompany.label"),
      body: t("setupChecklist.targetCompany.body"),
      to: "/settings/targets",
      linkLabel: t("setupChecklist.targetCompany.linkLabel"),
      // Deep-links straight into the template gallery (see
      // docs/topics-ux-improvements-planning.html §4.1) rather than the blank create
      // form — a user coming from "browse topic templates" here shouldn't have to find
      // that action again themselves.
      secondaryTo: "/themes?gallery=1",
      secondaryLinkLabel: t("setupChecklist.targetCompany.themeLinkLabel"),
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
              {step.secondaryTo && !step.done && (
                <Link to={step.secondaryTo} className="link-button">
                  {step.secondaryLinkLabel} →
                </Link>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
