import { useTranslation } from "react-i18next";

import { StarIcon } from "./icons/NavIcons";

interface FavoriteButtonProps {
  isFavorited: boolean;
  onToggle: () => void;
  className?: string;
}

export default function FavoriteButton({ isFavorited, onToggle, className }: FavoriteButtonProps) {
  const { t } = useTranslation("signals");
  return (
    <button
      type="button"
      className={`favorite-button${isFavorited ? " active" : ""}${className ? ` ${className}` : ""}`}
      aria-label={isFavorited ? t("unfavorite") : t("favorite")}
      aria-pressed={isFavorited}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onToggle();
      }}
    >
      <StarIcon filled={isFavorited} />
    </button>
  );
}
