import { useTranslation } from "react-i18next";

interface SkeletonProps {
  rows?: number;
}

export default function Skeleton({ rows = 3 }: SkeletonProps) {
  const { t } = useTranslation("common");
  return (
    <div className="skeleton-group" role="status" aria-live="polite">
      <span className="visually-hidden">{t("loading")}</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton-row" aria-hidden="true" />
      ))}
    </div>
  );
}
