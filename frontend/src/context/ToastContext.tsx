import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

type ToastVariant = "success" | "error";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
  action?: ToastAction;
}

interface ToastContextValue {
  showToast: (message: string, variant?: ToastVariant, action?: ToastAction) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const TOAST_DURATION_MS = 3000;
// A toast with an undo-style action stays up longer — the whole point is giving the
// user enough time to notice and click it before it's gone.
const TOAST_WITH_ACTION_DURATION_MS = 7000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const showToast = useCallback(
    (message: string, variant: ToastVariant = "success", action?: ToastAction) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev, { id, message, variant, action }]);
      setTimeout(
        () => {
          setToasts((prev) => prev.filter((toast) => toast.id !== id));
        },
        action ? TOAST_WITH_ACTION_DURATION_MS : TOAST_DURATION_MS
      );
    },
    []
  );

  function dismiss(id: number) {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.variant}`}>
            <span>{toast.message}</span>
            {toast.action && (
              <button
                type="button"
                className="toast-action"
                onClick={() => {
                  toast.action?.onClick();
                  dismiss(toast.id);
                }}
              >
                {toast.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
