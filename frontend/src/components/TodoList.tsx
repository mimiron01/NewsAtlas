import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import type { SignalTodo } from "../api/types";

interface TodoListProps {
  todos: SignalTodo[];
  onAdd: (text: string) => void;
  onToggle: (todo: SignalTodo) => void;
  onDelete: (todo: SignalTodo) => void;
}

export default function TodoList({ todos, onAdd, onToggle, onDelete }: TodoListProps) {
  const { t } = useTranslation(["signals", "common"]);
  const [draft, setDraft] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    onAdd(text);
    setDraft("");
  }

  const sorted = [...todos].sort((a, b) => {
    if (a.is_done !== b.is_done) return a.is_done ? 1 : -1;
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });

  return (
    <div className="todo-list">
      <form className="todo-add-form" onSubmit={handleSubmit}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("signals:todos.addPlaceholder")}
          maxLength={1000}
          aria-label={t("signals:todos.newTodoLabel")}
        />
        <button type="submit" disabled={!draft.trim()}>
          {t("common:add")}
        </button>
      </form>

      {sorted.length === 0 ? (
        <p className="subtitle">{t("signals:todos.empty")}</p>
      ) : (
        <ul className="todo-items">
          {sorted.map((todo) => (
            <li key={todo.id} className={todo.is_done ? "done" : ""}>
              <label className="checkbox-label todo-item-label">
                <input
                  type="checkbox"
                  checked={todo.is_done}
                  onChange={() => onToggle(todo)}
                  aria-label={
                    todo.is_done
                      ? t("signals:todos.markIncomplete", { text: todo.text })
                      : t("signals:todos.markComplete", { text: todo.text })
                  }
                />
                <span className="todo-text">{todo.text}</span>
              </label>
              <button
                type="button"
                className="link-button todo-delete"
                onClick={() => onDelete(todo)}
                aria-label={t("signals:todos.delete", { text: todo.text })}
              >
                {t("common:delete")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
