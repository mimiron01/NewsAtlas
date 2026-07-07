import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { User } from "../api/types";
import { ChevronUpDownIcon, GearIcon, LogoutIcon } from "./icons/NavIcons";

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function ProfileMenu({
  user,
  isAdmin,
  onLogout,
}: {
  user: User;
  isAdmin: boolean;
  onLogout: () => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!isOpen) return;
    function handlePointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setIsOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  function goToSettings() {
    setIsOpen(false);
    navigate("/settings/company");
  }

  function handleLogout() {
    setIsOpen(false);
    onLogout();
  }

  return (
    <div className="profile-menu" ref={containerRef}>
      {isOpen && (
        <div className="profile-popover" role="menu">
          {isAdmin && (
            <button type="button" role="menuitem" onClick={goToSettings}>
              <GearIcon /> Settings
            </button>
          )}
          <button type="button" role="menuitem" onClick={handleLogout}>
            <LogoutIcon /> Log out
          </button>
        </div>
      )}
      <button
        type="button"
        className="profile-trigger"
        aria-haspopup="true"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((open) => !open)}
      >
        <span className="profile-avatar">{initialsFor(user.name)}</span>
        <span className="profile-info">
          <strong>{user.name}</strong>
          <span>{user.email}</span>
        </span>
        <ChevronUpDownIcon />
      </button>
    </div>
  );
}
