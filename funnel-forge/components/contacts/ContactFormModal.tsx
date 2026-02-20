"use client";

import { useState } from "react";
import { Modal, Button, Input } from "@/components/ui";
import type { Contact } from "@/lib/types";
import { CONTACT_FORM_FIELDS } from "@/lib/sample-data";

interface Props {
  open: boolean;
  onClose: () => void;
  contact: Contact | null;
  formData: Omit<Contact, "id">;
  onFormChange: (data: Omit<Contact, "id">) => void;
  onSave: () => void;
}

export default function ContactFormModal({ open, onClose, contact, formData, onFormChange, onSave }: Props) {
  const [tagInput, setTagInput] = useState("");

  const addTag = () => {
    const tag = tagInput.trim().toLowerCase();
    if (tag && !formData.tags.includes(tag)) {
      onFormChange({ ...formData, tags: [...formData.tags, tag] });
    }
    setTagInput("");
  };

  const removeTag = (tag: string) => {
    onFormChange({ ...formData, tags: formData.tags.filter((t) => t !== tag) });
  };

  return (
    <Modal open={open} onClose={onClose} title={contact ? "Edit Contact" : "Add Contact"}>
      <div className="grid grid-cols-2 gap-4 mb-4">
        {CONTACT_FORM_FIELDS.map((field) => (
          <div key={field.key} className={field.span2 ? "col-span-2" : ""}>
            <Input
              label={field.label}
              type={field.key.includes("email") ? "email" : field.key === "linkedIn" ? "url" : "text"}
              value={formData[field.key]}
              onChange={(e) => onFormChange({ ...formData, [field.key]: e.target.value })}
              placeholder={field.placeholder}
            />
          </div>
        ))}
      </div>

      {/* Tags */}
      <div className="mb-5">
        <label className="block text-xs font-medium text-text-secondary mb-1 uppercase tracking-wide">Tags</label>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {formData.tags.map((tag) => (
            <span key={tag} className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-blue/10 text-accent-blue text-xs">
              {tag}
              <button onClick={() => removeTag(tag)} className="hover:text-red-400 transition-colors">&times;</button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
            placeholder="Add tag..."
            className="flex-1"
          />
          <Button variant="secondary" onClick={addTag}>Add</Button>
        </div>
      </div>

      <div className="flex justify-end gap-3">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button onClick={onSave}>{contact ? "Save Changes" : "Add Contact"}</Button>
      </div>
    </Modal>
  );
}
