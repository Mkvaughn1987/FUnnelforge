"use client";

import { useState, useRef, useCallback } from "react";
import Link from "next/link";
import PageHeader from "@/components/PageHeader";

const DEFAULT_TABS = [
  "Introduction",
  "Follow Up",
  "Value Add",
  "Per My Voicemail",
  "Alignment",
  "Check In",
  "Close the Loop",
];

const VARIABLES = [
  "{FirstName}",
  "{LastName}",
  "{Company}",
  "{Title}",
  "{Phone}",
];

const TEMPLATES = [
  "Cold Outreach – SaaS",
  "Follow-Up Sequence",
  "Event Invite",
  "Re-Engagement",
  "Custom",
];

interface EmailData {
  subject: string;
  body: string;
}

export default function EmailEditorPage() {
  const [campaignName, setCampaignName] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState(TEMPLATES[0]);
  const [tabs, setTabs] = useState(DEFAULT_TABS);
  const [activeTab, setActiveTab] = useState(0);
  const [emails, setEmails] = useState<EmailData[]>(
    DEFAULT_TABS.map(() => ({ subject: "", body: "" }))
  );
  const [history, setHistory] = useState<{ tabs: string[]; emails: EmailData[]; activeTab: number }[]>([]);
  const [showVarDropdown, setShowVarDropdown] = useState(false);
  const [showSignatureEditor, setShowSignatureEditor] = useState(false);
  const [signature, setSignature] = useState(
    "Best regards,\nJohn Smith\nSales Manager | FlowDrop\njohn@flowdrop.io | (555) 123-4567"
  );
  const [savedTemplates, setSavedTemplates] = useState<string[]>([]);
  const [showExplorePanel, setShowExplorePanel] = useState(false);
  const [showSaveTemplateInput, setShowSaveTemplateInput] = useState(false);
  const [newTemplateName, setNewTemplateName] = useState("");

  const editorRef = useRef<HTMLDivElement>(null);
  const tabsContainerRef = useRef<HTMLDivElement>(null);

  const pushHistory = useCallback(() => {
    setHistory((prev) => [
      ...prev.slice(-19),
      { tabs: [...tabs], emails: emails.map((e) => ({ ...e })), activeTab },
    ]);
  }, [tabs, emails, activeTab]);

  const handleUndo = () => {
    if (history.length === 0) return;
    const last = history[history.length - 1];
    setTabs(last.tabs);
    setEmails(last.emails);
    setActiveTab(last.activeTab);
    setHistory((prev) => prev.slice(0, -1));
  };

  const handleAddEmail = () => {
    pushHistory();
    const name = `Email ${tabs.length + 1}`;
    setTabs((prev) => [...prev, name]);
    setEmails((prev) => [...prev, { subject: "", body: "" }]);
    setActiveTab(tabs.length);
  };

  const handleDeleteEmail = () => {
    if (tabs.length <= 1) return;
    pushHistory();
    const idx = activeTab;
    setTabs((prev) => prev.filter((_, i) => i !== idx));
    setEmails((prev) => prev.filter((_, i) => i !== idx));
    setActiveTab(Math.min(idx, tabs.length - 2));
  };

  const handleSubjectChange = (value: string) => {
    setEmails((prev) =>
      prev.map((e, i) => (i === activeTab ? { ...e, subject: value } : e))
    );
  };

  const insertVariable = (variable: string) => {
    const subjectInput = document.getElementById("subject-input") as HTMLInputElement | null;
    if (subjectInput) {
      const start = subjectInput.selectionStart ?? subjectInput.value.length;
      const end = subjectInput.selectionEnd ?? start;
      const current = emails[activeTab].subject;
      const updated = current.slice(0, start) + variable + current.slice(end);
      handleSubjectChange(updated);
      setTimeout(() => {
        subjectInput.focus();
        subjectInput.setSelectionRange(start + variable.length, start + variable.length);
      }, 0);
    }
    setShowVarDropdown(false);
  };

  const execCommand = (command: string, value?: string) => {
    document.execCommand(command, false, value);
    editorRef.current?.focus();
  };

  const handleBodyInput = () => {
    if (editorRef.current) {
      setEmails((prev) =>
        prev.map((e, i) =>
          i === activeTab ? { ...e, body: editorRef.current!.innerHTML } : e
        )
      );
    }
  };

  const handleSaveTemplate = () => {
    if (newTemplateName.trim()) {
      setSavedTemplates((prev) => [...prev, newTemplateName.trim()]);
      setNewTemplateName("");
      setShowSaveTemplateInput(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Email Editor"
        subtitle="Compose and customize your email sequence."
      />

      {/* Back link */}
      <Link
        href="/create-campaign"
        className="flex items-center gap-2 text-text-secondary hover:text-text-primary text-sm mb-6 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
        </svg>
        Back to Campaign
      </Link>

      {/* Campaign Name + Template */}
      <div className="flex flex-col lg:flex-row gap-4 mb-6">
        <div className="flex-1">
          <label className="block text-sm font-medium text-text-primary mb-2">
            Campaign Name
          </label>
          <input
            type="text"
            value={campaignName}
            onChange={(e) => setCampaignName(e.target.value)}
            placeholder="e.g. Q1 Outreach Sequence"
            className="w-full px-4 py-2.5 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-accent-blue transition-colors"
          />
        </div>
        <div className="w-full lg:w-64">
          <label className="block text-sm font-medium text-text-primary mb-2">
            Template
          </label>
          <select
            value={selectedTemplate}
            onChange={(e) => setSelectedTemplate(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg bg-bg border border-border text-text-primary focus:outline-none focus:border-accent-blue transition-colors"
          >
            {TEMPLATES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          onClick={handleAddEmail}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-accent-blue/10 text-accent-blue text-sm font-medium hover:bg-accent-blue/20 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Add Email
        </button>
        <button
          onClick={handleDeleteEmail}
          disabled={tabs.length <= 1}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-red-500/10 text-red-400 text-sm font-medium hover:bg-red-500/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
          </svg>
          Delete Email
        </button>
        <button
          onClick={handleUndo}
          disabled={history.length === 0}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface border border-border text-text-secondary text-sm font-medium hover:bg-surface-hover hover:text-text-primary transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3" />
          </svg>
          Undo
        </button>
        <button
          onClick={() => setShowExplorePanel(!showExplorePanel)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-accent-purple/10 text-accent-purple text-sm font-medium hover:bg-accent-purple/20 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
          Explore Templates
        </button>
        <button
          onClick={() => setShowSaveTemplateInput(!showSaveTemplateInput)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface border border-border text-text-secondary text-sm font-medium hover:bg-surface-hover hover:text-text-primary transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0 1 11.186 0Z" />
          </svg>
          Save New Template
        </button>
      </div>

      {/* Save template input */}
      {showSaveTemplateInput && (
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={newTemplateName}
            onChange={(e) => setNewTemplateName(e.target.value)}
            placeholder="Template name..."
            className="flex-1 max-w-xs px-4 py-2 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-accent-blue transition-colors text-sm"
            onKeyDown={(e) => e.key === "Enter" && handleSaveTemplate()}
          />
          <button
            onClick={handleSaveTemplate}
            className="px-4 py-2 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors"
          >
            Save
          </button>
          <button
            onClick={() => { setShowSaveTemplateInput(false); setNewTemplateName(""); }}
            className="px-4 py-2 rounded-lg bg-surface border border-border text-text-secondary text-sm hover:bg-surface-hover transition-colors"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Explore Templates Panel */}
      {showExplorePanel && (
        <div className="mb-4 bg-surface rounded-xl border border-border p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">Template Library</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[...TEMPLATES, ...savedTemplates].map((t) => (
              <button
                key={t}
                onClick={() => { setSelectedTemplate(t); setShowExplorePanel(false); }}
                className="px-3 py-2.5 rounded-lg bg-bg border border-border text-text-secondary text-sm text-left hover:border-accent-blue/50 hover:text-text-primary transition-colors"
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Email Tabs – horizontal scroll */}
      <div className="relative mb-6">
        <div
          ref={tabsContainerRef}
          className="flex gap-1 overflow-x-auto pb-1 scrollbar-hide"
          style={{ scrollbarWidth: "none" }}
        >
          {tabs.map((tab, idx) => (
            <button
              key={idx}
              onClick={() => setActiveTab(idx)}
              className={`flex-shrink-0 px-4 py-2.5 rounded-t-lg text-sm font-medium transition-colors whitespace-nowrap ${
                idx === activeTab
                  ? "bg-surface border border-b-0 border-border text-accent-blue"
                  : "text-text-secondary hover:text-text-primary hover:bg-surface-hover"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="h-px bg-border" />
      </div>

      {/* Editor Container */}
      <div className="bg-surface rounded-xl border border-border overflow-hidden">
        {/* Subject line row */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
          <label className="text-sm font-medium text-text-secondary flex-shrink-0">
            Subject:
          </label>
          <input
            id="subject-input"
            type="text"
            value={emails[activeTab]?.subject ?? ""}
            onChange={(e) => handleSubjectChange(e.target.value)}
            placeholder="Enter subject line..."
            className="flex-1 px-3 py-2 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-accent-blue transition-colors text-sm"
          />

          {/* Insert Variable */}
          <div className="relative">
            <button
              onClick={() => setShowVarDropdown(!showVarDropdown)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-accent-blue/10 text-accent-blue text-xs font-medium hover:bg-accent-blue/20 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5" />
              </svg>
              Insert Variable
            </button>
            {showVarDropdown && (
              <div className="absolute right-0 top-full mt-1 w-44 bg-surface border border-border rounded-lg shadow-xl z-20 py-1">
                {VARIABLES.map((v) => (
                  <button
                    key={v}
                    onClick={() => insertVariable(v)}
                    className="w-full px-3 py-2 text-left text-sm text-text-secondary hover:bg-surface-hover hover:text-accent-blue transition-colors font-mono"
                  >
                    {v}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Add/Edit Signature */}
          <button
            onClick={() => setShowSignatureEditor(!showSignatureEditor)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-hover text-text-secondary text-xs font-medium hover:text-text-primary transition-colors border border-border"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
            </svg>
            {showSignatureEditor ? "Close Signature" : "Add/Edit Signature"}
          </button>
        </div>

        {/* Rich Text Toolbar */}
        <div className="flex items-center gap-1 px-5 py-2.5 border-b border-border bg-bg/50">
          <button
            onClick={() => execCommand("bold")}
            className="p-2 rounded hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
            title="Bold"
          >
            <span className="text-sm font-bold">B</span>
          </button>
          <button
            onClick={() => execCommand("italic")}
            className="p-2 rounded hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
            title="Italic"
          >
            <span className="text-sm italic">I</span>
          </button>
          <button
            onClick={() => execCommand("underline")}
            className="p-2 rounded hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
            title="Underline"
          >
            <span className="text-sm underline">U</span>
          </button>

          <div className="w-px h-5 bg-border mx-1" />

          <button
            onClick={() => execCommand("insertUnorderedList")}
            className="p-2 rounded hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
            title="Bullet List"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0ZM3.75 12h.007v.008H3.75V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm-.375 5.25h.007v.008H3.75v-.008Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
            </svg>
          </button>
          <button
            onClick={() => execCommand("insertOrderedList")}
            className="p-2 rounded hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
            title="Numbered List"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.242 5.992h12m-12 6.003h12m-12 5.999h12M4.117 7.495v-3.75H2.99m1.125 3.75H2.99m1.125 0H4.24m-1.247 5.999h1.121a.374.374 0 0 0 0-.748H2.99m1.125 2.25H2.99m1.252 0a.375.375 0 0 0-.377.375.375.375 0 0 0 .377.375H4.24M2.99 18v.012h1.25V18H2.99Z" />
            </svg>
          </button>

          <div className="w-px h-5 bg-border mx-1" />

          <button
            onClick={() => {
              const url = prompt("Enter link URL:");
              if (url) execCommand("createLink", url);
            }}
            className="p-2 rounded hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
            title="Insert Link"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
            </svg>
          </button>

          <div className="w-px h-5 bg-border mx-1" />

          <button
            onClick={() => execCommand("justifyLeft")}
            className="p-2 rounded hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
            title="Align Left"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h10.5m-10.5 5.25h16.5" />
            </svg>
          </button>
          <button
            onClick={() => execCommand("justifyCenter")}
            className="p-2 rounded hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
            title="Align Center"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M6.75 12h10.5M3.75 17.25h16.5" />
            </svg>
          </button>
          <button
            onClick={() => execCommand("justifyRight")}
            className="p-2 rounded hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
            title="Align Right"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M7.5 12h13.5M3.75 17.25h16.5" />
            </svg>
          </button>
        </div>

        {/* Body Editor */}
        <div
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          onInput={handleBodyInput}
          className="min-h-[340px] px-6 py-5 text-text-primary text-sm leading-relaxed focus:outline-none"
          style={{ fontFamily: "var(--font-body), sans-serif" }}
          dangerouslySetInnerHTML={{
            __html: emails[activeTab]?.body ?? "",
          }}
          key={activeTab}
        />

        {/* Signature Display */}
        <div className="border-t border-border px-6 py-4 bg-bg/30">
          <p className="text-xs text-text-secondary mb-2 uppercase tracking-wider font-medium">
            Signature
          </p>
          <div className="text-sm text-text-secondary whitespace-pre-line leading-relaxed">
            {signature}
          </div>
        </div>
      </div>

      {/* Signature Editor (modal-style panel) */}
      {showSignatureEditor && (
        <div className="mt-4 bg-surface rounded-xl border border-border p-5">
          <h3 className="text-sm font-medium text-text-primary mb-3">
            Edit Signature
          </h3>
          <textarea
            value={signature}
            onChange={(e) => setSignature(e.target.value)}
            rows={5}
            className="w-full px-4 py-3 rounded-lg bg-bg border border-border text-text-primary text-sm focus:outline-none focus:border-accent-blue transition-colors resize-none leading-relaxed"
          />
          <div className="flex justify-end mt-3">
            <button
              onClick={() => setShowSignatureEditor(false)}
              className="px-4 py-2 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      )}

      {/* Bottom Action Buttons */}
      <div className="flex justify-end gap-3 mt-6 pb-8">
        <button className="px-5 py-2.5 rounded-lg bg-surface border border-border text-text-secondary text-sm font-medium hover:bg-surface-hover hover:text-text-primary transition-colors">
          Save Draft
        </button>
        <button className="px-5 py-2.5 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors">
          Preview &amp; Launch
        </button>
      </div>
    </div>
  );
}
