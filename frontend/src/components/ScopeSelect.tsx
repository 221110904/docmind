import { useId } from "react";
import type { DocumentOut } from "../types";

interface Props {
  docs: DocumentOut[];
  value: string;
  onChange: (documentId: string) => void;
}

/** Choose between every document or one. Only documents that are Ready can be searched. */
export function ScopeSelect({ docs, value, onChange }: Props) {
  const id = useId();
  const ready = docs.filter((d) => d.status === "indexed");
  return (
    <div className="field">
      <label htmlFor={id}>Look in</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All documents</option>
        {ready.map((d) => (
          <option key={d.id} value={d.id}>
            {d.filename}
          </option>
        ))}
      </select>
    </div>
  );
}
