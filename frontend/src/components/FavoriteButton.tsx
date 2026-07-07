import { StarIcon } from "./icons/NavIcons";

interface FavoriteButtonProps {
  isFavorited: boolean;
  onToggle: () => void;
  className?: string;
}

export default function FavoriteButton({ isFavorited, onToggle, className }: FavoriteButtonProps) {
  return (
    <button
      type="button"
      className={`favorite-button${isFavorited ? " active" : ""}${className ? ` ${className}` : ""}`}
      aria-label={isFavorited ? "Unfavorite" : "Favorite"}
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
