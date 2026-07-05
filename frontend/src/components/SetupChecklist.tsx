import { Link } from "react-router-dom";

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
  const steps = [
    {
      done: hasCompanyProfile,
      label: "Describe your company",
      body: "Tell the AI what you sell so it can explain why each signal matters.",
      to: "/settings/profile",
      linkLabel: "Set up company profile",
    },
    {
      done: hasTargetCompany,
      label: "Add a target company",
      body: "Pick the companies you want news signals for.",
      to: "/settings/targets",
      linkLabel: "Add target companies",
    },
    {
      done: hasSignals,
      label: "Fetch your first signals",
      body: "Click \"Fetch new signals\" below once you've added a target company.",
      to: null,
      linkLabel: null,
    },
  ];

  return (
    <div className="panel-card setup-checklist">
      <h3>Get started</h3>
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
