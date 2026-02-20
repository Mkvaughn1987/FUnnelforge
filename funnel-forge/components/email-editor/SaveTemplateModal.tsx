"use client";

import { useState } from "react";
import { Button, Input } from "@/components/ui";
import type { EmailTab } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
  emails: EmailTab[];
  defaultName: string;
  onSave: (name: string) => void;
}

export default function SaveTemplateModal({ open, onClose, emails, defaultName, onSave }: Props) {
  const [name, setName] = useState(defaultName);

  if (!open) return null;

  const handleSave = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onSave(trimmed);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-surface rounded-xl border border-border p-6 w-full max-w-md mx-4 shadow-2xl">
        <h2 className="text-xl font-semibold mb-4">Save as Template</h2>
        <p className="text-sm text-text-secondary mb-4">
          Save your current {emails.length}-email sequence as a reusable template.
        </p>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSave(); }}
          placeholder="Template name..."
          autoFocus
        />
        <div className="flex flex-wrap gap-1 my-4">
          {emails.map((e, i) => (
            <span key={i} className="px-2 py-0.5 rounded bg-accent-blue/10 text-accent-blue text-xs">{e.name}</span>
          ))}
        </div>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave}>Save Template</Button>
        </div>
      </div>
    </div>
  );
}
