"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import PageHeader from "@/components/PageHeader";
import EmailToolbar from "@/components/email-editor/EmailToolbar";
import TemplateBrowserModal from "@/components/email-editor/TemplateBrowserModal";
import SaveTemplateModal from "@/components/email-editor/SaveTemplateModal";
import { BackButton, Button, FolderIcon, Input } from "@/components/ui";
import type { EmailTab, Signature, Template } from "@/lib/types";
import { DEFAULT_EMAIL_TABS, VARIABLES } from "@/lib/sample-data";

export default function EmailEditorPage() {
  const router = useRouter();
  const editorRef = useRef<HTMLDivElement>(null);

  const [campaignName, setCampaignName] = useState("");
  const [emails, setEmails] = useState<EmailTab[]>(DEFAULT_EMAIL_TABS.map((t) => ({ ...t })));
  const [activeTab, setActiveTab] = useState(0);
  const [history, setHistory] = useState<EmailTab[][]>([]);
  const [showVarDropdown, setShowVarDropdown] = useState(false);
  const [showSigPanel, setShowSigPanel] = useState(false);
  const [signature, setSignature] = useState<Signature>({ name: "", title: "", phone: "", email: "" });
  const [showTemplateBrowser, setShowTemplateBrowser] = useState(false);
  const [showSaveTemplate, setShowSaveTemplate] = useState(false);
  const [savedTemplates, setSavedTemplates] = useState<Template[]>([]);

  const pushHistory = useCallback(() => {
    setHistory((h) => [...h.slice(-20), emails.map((e) => ({ ...e }))]);
  }, [emails]);

  const addEmail = () => {
    pushHistory();
    setEmails((prev) => [...prev, { name: `Email ${prev.length + 1}`, subject: "", body: "" }]);
    setActiveTab(emails.length);
  };

  const deleteEmail = () => {
    if (emails.length <= 1) return;
    pushHistory();
    setEmails((prev) => prev.filter((_, i) => i !== activeTab));
    setActiveTab((t) => Math.min(t, emails.length - 2));
  };

  const undo = () => {
    if (!history.length) return;
    const prev = history[history.length - 1];
    setHistory((h) => h.slice(0, -1));
    setEmails(prev);
    setActiveTab((t) => Math.min(t, prev.length - 1));
  };

  const updateSubject = (val: string) => {
    setEmails((prev) => prev.map((e, i) => (i === activeTab ? { ...e, subject: val } : e)));
  };

  const insertVariable = (v: string) => {
    document.execCommand("insertText", false, v);
    setShowVarDropdown(false);
  };

  const applyTemplate = (tmpl: Template) => {
    pushHistory();
    setEmails(tmpl.emails.map((e) => ({ ...e })));
    setActiveTab(0);
    setShowTemplateBrowser(false);
  };

  const saveAsTemplate = (name: string) => {
    setSavedTemplates((prev) => [...prev, { name, emails: emails.map((e) => ({ ...e })) }]);
    setShowSaveTemplate(false);
  };

  const sigText =
    signature.name || signature.title || signature.phone || signature.email
      ? [signature.name, signature.title, signature.phone, signature.email].filter(Boolean).join("\n")
      : "";

  return (
    <div className="flex flex-col h-[calc(100vh-64px)]">
      <PageHeader title="Email Editor" subtitle="Build your email sequence step by step." />

      <BackButton onClick={() => router.push("/create-campaign")} className="mb-4" />

      {/* Top bar */}
      <div className="bg-surface rounded-xl border border-border p-4 mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            value={campaignName}
            onChange={(e) => setCampaignName(e.target.value)}
            placeholder="Untitled Campaign"
            className="flex-1 min-w-[200px] text-xl font-semibold bg-transparent border-b border-border text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-accent-blue pb-1 transition-colors"
          />
          <Button variant="secondary" onClick={() => setShowTemplateBrowser(true)}>
            <FolderIcon className="w-4 h-4 text-text-secondary" />
            Templates
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <Button size="sm" onClick={addEmail}>+ Add Email</Button>
          <Button size="sm" variant="secondary" onClick={deleteEmail}>Delete Email</Button>
          <Button size="sm" variant="secondary" onClick={undo}>Undo</Button>
          <Button size="sm" variant="secondary" onClick={() => setShowTemplateBrowser(true)}>Explore Templates</Button>
          <Button size="sm" variant="secondary" onClick={() => setShowSaveTemplate(true)}>Save New Template</Button>
        </div>
      </div>

      {/* Email tabs */}
      <div className="flex items-center gap-1 mb-4 overflow-x-auto pb-1">
        {emails.map((email, i) => (
          <button
            key={i}
            onClick={() => setActiveTab(i)}
            className={`whitespace-nowrap px-4 py-2 rounded-t-lg text-sm font-medium border-b-2 transition-all flex-shrink-0 ${
              i === activeTab
                ? "bg-surface border-accent-blue text-accent-blue"
                : "bg-transparent border-transparent text-text-secondary hover:text-text-primary hover:bg-surface/50"
            }`}
          >
            {email.name}
          </button>
        ))}
      </div>

      {/* Editor area */}
      <div className="flex-1 bg-surface rounded-xl border border-border flex flex-col overflow-hidden">
        {/* Subject line */}
        <div className="p-4 border-b border-border">
          <label className="block text-xs font-medium text-text-secondary mb-1.5 uppercase tracking-wide">
            Email Name / Subject Line
          </label>
          <div className="flex items-center gap-2">
            <Input
              value={emails[activeTab]?.subject ?? ""}
              onChange={(e) => updateSubject(e.target.value)}
              placeholder="Enter subject line..."
            />
            <div className="relative">
              <Button variant="secondary" onClick={() => setShowVarDropdown(!showVarDropdown)} className="whitespace-nowrap text-accent-blue">
                + Insert Variable
              </Button>
              {showVarDropdown && (
                <div className="absolute right-0 top-full mt-1 bg-surface border border-border rounded-lg shadow-xl z-20 py-1 min-w-[160px]">
                  {VARIABLES.map((v) => (
                    <button
                      key={v}
                      onClick={() => insertVariable(v)}
                      className="block w-full text-left px-4 py-2 text-sm text-text-primary hover:bg-surface-hover transition-colors"
                    >
                      {v}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <Button variant="secondary" onClick={() => setShowSigPanel(!showSigPanel)} className="whitespace-nowrap">
              Add/Edit Signature
            </Button>
          </div>
        </div>

        {/* Signature edit panel */}
        {showSigPanel && (
          <div className="px-4 py-3 border-b border-border bg-bg/50">
            <div className="grid grid-cols-2 gap-3 max-w-xl">
              {(["name", "title", "phone", "email"] as const).map((field) => (
                <Input
                  key={field}
                  value={signature[field]}
                  onChange={(e) => setSignature((s) => ({ ...s, [field]: e.target.value }))}
                  placeholder={field.charAt(0).toUpperCase() + field.slice(1)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Toolbar */}
        <EmailToolbar editorRef={editorRef} />

        {/* Body editor */}
        <div className="flex-1 overflow-y-auto">
          <div
            ref={editorRef}
            contentEditable
            suppressContentEditableWarning
            className="min-h-[300px] px-6 py-4 text-text-primary leading-relaxed focus:outline-none"
            style={{ whiteSpace: "pre-wrap" }}
            onBlur={() => {
              const html = editorRef.current?.innerHTML ?? "";
              setEmails((prev) => prev.map((e, i) => (i === activeTab ? { ...e, body: html } : e)));
            }}
            dangerouslySetInnerHTML={{ __html: emails[activeTab]?.body ?? "" }}
          />
        </div>

        {/* Signature display */}
        {sigText && (
          <div className="px-6 py-3 border-t border-border bg-bg/40">
            <p className="text-text-secondary/60 text-sm whitespace-pre-line leading-relaxed">
              --{"\n"}{sigText}
            </p>
          </div>
        )}
      </div>

      {/* Bottom bar */}
      <div className="flex items-center justify-end gap-3 mt-4 pb-4">
        <Button variant="secondary">Save Draft</Button>
        <Button>Preview &amp; Launch</Button>
      </div>

      {/* Modals */}
      <TemplateBrowserModal
        open={showTemplateBrowser}
        onClose={() => setShowTemplateBrowser(false)}
        savedTemplates={savedTemplates}
        onApply={applyTemplate}
      />
      <SaveTemplateModal
        open={showSaveTemplate}
        onClose={() => setShowSaveTemplate(false)}
        emails={emails}
        defaultName={campaignName}
        onSave={saveAsTemplate}
      />
    </div>
  );
}
