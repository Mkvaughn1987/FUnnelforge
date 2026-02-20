"use client";

import { Modal } from "@/components/ui";
import type { Template } from "@/lib/types";
import { BUILT_IN_TEMPLATES } from "@/lib/sample-data";

interface Props {
  open: boolean;
  onClose: () => void;
  savedTemplates: Template[];
  onApply: (tmpl: Template) => void;
}

export default function TemplateBrowserModal({ open, onClose, savedTemplates, onApply }: Props) {
  const TemplateCard = ({ tmpl }: { tmpl: Template }) => (
    <button
      onClick={() => onApply(tmpl)}
      className="text-left p-4 rounded-lg bg-bg border border-border hover:border-accent-blue/50 transition-all group"
    >
      <p className="text-sm font-medium text-text-primary group-hover:text-accent-blue transition-colors">{tmpl.name}</p>
      <p className="text-xs text-text-secondary mt-1">{tmpl.emails.length} emails</p>
      <div className="flex flex-wrap gap-1 mt-2">
        {tmpl.emails.map((e, j) => (
          <span key={j} className="px-1.5 py-0.5 rounded bg-accent-blue/10 text-accent-blue text-[10px]">{e.name}</span>
        ))}
      </div>
    </button>
  );

  return (
    <Modal open={open} onClose={onClose} title="Explore Templates" maxWidth="max-w-3xl">
      {savedTemplates.length > 0 && (
        <div className="mb-6">
          <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-3">Your Templates</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {savedTemplates.map((tmpl, i) => (
              <TemplateCard key={`saved-${i}`} tmpl={tmpl} />
            ))}
          </div>
        </div>
      )}
      <div>
        <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-3">Built-in Templates</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {BUILT_IN_TEMPLATES.map((tmpl) => (
            <TemplateCard key={tmpl.name} tmpl={tmpl} />
          ))}
        </div>
      </div>
    </Modal>
  );
}
