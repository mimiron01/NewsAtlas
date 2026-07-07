import { FormEvent, useState } from "react";

import type { SignalTodo } from "../api/types";

interface TodoListProps {
  todos: SignalTodo[];
  onAdd: (text: string) => void;
  onToggle: (todo: SignalTodo) => void;
  onDelete: (todo: SignalTodo) => void;
}

export default function TodoList({ todos, onAdd, onToggle, onDelete }: TodoListProps) {
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
          placeholder="Add a note or todo..."
          maxLength={1000}
          aria-label="New todo text"
        />
        <button type="submit" disabled={!draft.trim()}>
          Add
        </button>
      </form>

      {sorted.length === 0 ? (
        <p className="subtitle">No notes yet. Add one to track a follow-up on this signal.</p>
      ) : (
        <ul className="todo-items">
          {sorted.map((todo) => (
            <li key={todo.id} className={todo.is_done ? "done" : ""}>
              <label className="checkbox-label todo-item-label">
                <input
                  type="checkbox"
                  checked={todo.is_done}
                  onChange={() => onToggle(todo)}
                  aria-label={todo.is_done ? `Mark "${todo.text}" incomplete` : `Mark "${todo.text}" complete`}
                />
                <span className="todo-text">{todo.text}</span>
              </label>
              <button
                type="button"
                className="link-button todo-delete"
                onClick={() => onDelete(todo)}
                aria-label={`Delete "${todo.text}"`}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
