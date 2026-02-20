"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import PageHeader from "@/components/PageHeader";

/* ── Types ── */
interface EmailTab {
  name: string;
  subject: string;
  body: string;
}

interface Signature {
  name: string;
  title: string;
  phone: string;
  email: string;
}

const DEFAULT_TABS: EmailTab[] = [
  { name: "Introduction", subject: "", body: "" },
  { name: "Follow Up", subject: "", body: "" },
  { name: "Value Add", subject: "", body: "" },
  { name: "Per My Voicemail", subject: "", body: "" },
  { name: "Alignment", subject: "", body: "" },
  { name: "Check In", subject: "", body: "" },
  { name: "Close the Loop", subject: "", body: "" },
];

const VARIABLES = ["{FirstName}", "{LastName}", "{Company}", "{Title}", "{Phone}"];

/* ── Template library ── */
interface Template {
  name: string;
  emails: EmailTab[];
}

const BUILT_IN_TEMPLATES: Template[] = [
  {
    name: "Cold Outreach",
    emails: [
      { name: "Introduction", subject: "Quick intro — {Company} + your team", body: "<p>Hi {FirstName},</p><p>I came across {Company} and wanted to reach out. We help teams like yours streamline their outreach and close deals faster.</p><p>Would you be open to a quick 15-minute call this week?</p>" },
      { name: "Follow Up", subject: "Following up — {FirstName}", body: "<p>Hi {FirstName},</p><p>Just circling back on my note from a few days ago. I know things get busy — I'd love to find a time that works for a brief chat.</p><p>Any interest?</p>" },
      { name: "Value Add", subject: "Thought you'd find this useful", body: "<p>Hi {FirstName},</p><p>I wanted to share a resource that's been helping similar teams in your space see 30%+ improvement in response rates.</p><p>Happy to walk you through it if you're interested.</p>" },
      { name: "Break Up", subject: "Should I close your file?", body: "<p>Hi {FirstName},</p><p>I haven't heard back, so I'll assume the timing isn't right. No hard feelings — I'll close out your file for now.</p><p>If anything changes, feel free to reach out anytime.</p>" },
    ],
  },
  {
    name: "Sales Funnel",
    emails: [
      { name: "Introduction", subject: "Helping {Company} grow", body: "<p>Hi {FirstName},</p><p>I noticed {Company} is expanding — congrats! We specialize in helping growing teams like yours scale their sales outreach without adding headcount.</p><p>Worth a quick conversation?</p>" },
      { name: "Social Proof", subject: "How [Client] increased pipeline by 40%", body: "<p>Hi {FirstName},</p><p>Wanted to share a quick win — one of our clients in a similar space saw a 40% increase in qualified pipeline within 60 days of using our platform.</p><p>I'd love to show you how we could do the same for {Company}.</p>" },
      { name: "Case Study", subject: "Case study for {Company}", body: "<p>Hi {FirstName},</p><p>I put together a brief case study that's directly relevant to what you're doing at {Company}. It covers the exact playbook our top-performing customers use.</p><p>Want me to send it over?</p>" },
      { name: "Demo Offer", subject: "Free demo — see it in action", body: "<p>Hi {FirstName},</p><p>Sometimes seeing is believing. I'd love to give you a personalized 15-minute demo showing exactly how this would work for {Company}.</p><p>No strings attached — just pick a time that works.</p>" },
      { name: "Close the Loop", subject: "Last note from me", body: "<p>Hi {FirstName},</p><p>I don't want to be that person who keeps filling your inbox, so this will be my last reach-out for now.</p><p>If you ever want to revisit this, my door is always open. Wishing you and the {Company} team continued success!</p>" },
    ],
  },
  {
    name: "Welcome Series",
    emails: [
      { name: "Welcome", subject: "Welcome aboard, {FirstName}!", body: "<p>Hi {FirstName},</p><p>Welcome! We're thrilled to have you on board. Here's a quick overview of what you can expect over the next few days as we help you get started.</p>" },
      { name: "Getting Started", subject: "Your first steps", body: "<p>Hi {FirstName},</p><p>Ready to dive in? Here are 3 quick things you can do right now to get the most out of your account:</p><ol><li>Complete your profile</li><li>Import your contacts</li><li>Send your first campaign</li></ol>" },
      { name: "Tips & Tricks", subject: "Pro tips to save you time", body: "<p>Hi {FirstName},</p><p>Now that you've had a chance to explore, here are some insider tips our power users swear by to get even better results.</p>" },
      { name: "Check In", subject: "How's it going, {FirstName}?", body: "<p>Hi {FirstName},</p><p>Just checking in — how are things going so far? If you have any questions or need help, I'm here for you.</p><p>Hit reply and let me know!</p>" },
    ],
  },
  {
    name: "Re-engagement",
    emails: [
      { name: "We Miss You", subject: "It's been a while, {FirstName}", body: "<p>Hi {FirstName},</p><p>We noticed it's been a while since we last connected. A lot has changed on our end, and I think you'd be impressed with what's new.</p><p>Worth catching up?</p>" },
      { name: "What's New", subject: "You're missing out on some big updates", body: "<p>Hi {FirstName},</p><p>Since we last spoke, we've launched several features that directly address the challenges you mentioned. I'd love to show you what's changed.</p>" },
      { name: "Special Offer", subject: "Something special for you, {FirstName}", body: "<p>Hi {FirstName},</p><p>As a valued contact, I wanted to extend a special offer your way. Let me know if you'd like to hear the details — no pressure.</p>" },
      { name: "Final Check", subject: "Should I keep you on our list?", body: "<p>Hi {FirstName},</p><p>I want to respect your inbox. If you're no longer interested, no worries at all — just let me know and I'll update your preferences.</p><p>But if you're still open to hearing from us, I've got some great stuff to share.</p>" },
    ],
  },
];

export default function EmailEditorPage() {
  const router = useRouter();
  const editorRef = useRef<HTMLDivElement>(null);

  /* ── State ── */
  const [campaignName, setCampaignName] = useState("");
  const [emails, setEmails] = useState<EmailTab[]>(DEFAULT_TABS.map((t) => ({ ...t })));
  const [activeTab, setActiveTab] = useState(0);
  const [history, setHistory] = useState<EmailTab[][]>([]);
  const [showVarDropdown, setShowVarDropdown] = useState(false);
  const [showSigPanel, setShowSigPanel] = useState(false);
  const [signature, setSignature] = useState<Signature>({ name: "", title: "", phone: "", email: "" });
  const [showTemplateBrowser, setShowTemplateBrowser] = useState(false);
  const [showSaveTemplate, setShowSaveTemplate] = useState(false);
  const [savedTemplates, setSavedTemplates] = useState<Template[]>([]);
  const [newTemplateName, setNewTemplateName] = useState("");

  /* ── Helpers ── */
  const pushHistory = useCallback(() => {
    setHistory((h) => [...h.slice(-20), emails.map((e) => ({ ...e }))]);
  }, [emails]);

  const addEmail = () => {
    pushHistory();
    const n = emails.length + 1;
    setEmails((prev) => [...prev, { name: `Email ${n}`, subject: "", body: "" }]);
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

  const exec = (cmd: string, val?: string) => {
    document.execCommand(cmd, false, val);
    editorRef.current?.focus();
  };

  const sigText =
    signature.name || signature.title || signature.phone || signature.email
      ? [signature.name, signature.title, signature.phone, signature.email].filter(Boolean).join("\n")
      : "";

  const applyTemplate = (tmpl: Template) => {
    pushHistory();
    setEmails(tmpl.emails.map((e) => ({ ...e })));
    setActiveTab(0);
    setShowTemplateBrowser(false);
  };

  const saveAsTemplate = () => {
    const name = newTemplateName.trim();
    if (!name) return;
    setSavedTemplates((prev) => [...prev, { name, emails: emails.map((e) => ({ ...e })) }]);
    setNewTemplateName("");
    setShowSaveTemplate(false);
  };

  const allTemplates = [...BUILT_IN_TEMPLATES, ...savedTemplates];

  /* ── Toolbar button groups (Word-style) ── */

  /* ── Render ── */
  return (
    <div className="flex flex-col h-[calc(100vh-64px)]">
      <PageHeader title="Email Editor" subtitle="Build your email sequence step by step." />

      {/* ── Back button ── */}
      <button
        onClick={() => router.push("/create-campaign")}
        className="flex items-center gap-2 text-text-secondary hover:text-text-primary text-sm mb-4 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
        </svg>
        Back
      </button>

      {/* ── Top bar: name + template + buttons ── */}
      <div className="bg-surface rounded-xl border border-border p-4 mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            value={campaignName}
            onChange={(e) => setCampaignName(e.target.value)}
            placeholder="Untitled Campaign"
            className="flex-1 min-w-[200px] text-xl font-semibold bg-transparent border-b border-border text-text-primary placeholder:text-text-secondary/40 focus:outline-none focus:border-accent-blue pb-1 transition-colors"
          />
          <button
            onClick={() => setShowTemplateBrowser(true)}
            className="px-3 py-2 rounded-lg bg-bg border border-border text-text-primary text-sm hover:border-accent-blue/40 transition-colors flex items-center gap-2"
          >
            <svg className="w-4 h-4 text-text-secondary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z" />
            </svg>
            Templates
          </button>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap items-center gap-2 mt-3">
          {[
            { label: "+ Add Email", action: addEmail, primary: true },
            { label: "Delete Email", action: deleteEmail, primary: false },
            { label: "Undo", action: undo, primary: false },
            { label: "Explore Templates", action: () => setShowTemplateBrowser(true), primary: false },
            { label: "Save New Template", action: () => { setNewTemplateName(campaignName); setShowSaveTemplate(true); }, primary: false },
          ].map((btn) => (
            <button
              key={btn.label}
              onClick={btn.action}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                btn.primary
                  ? "bg-accent-blue text-white hover:bg-accent-blue/90"
                  : "bg-bg border border-border text-text-secondary hover:text-text-primary hover:border-accent-blue/40"
              }`}
            >
              {btn.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Email tabs ── */}
      <div className="flex items-center gap-1 mb-4 overflow-x-auto pb-1 scrollbar-thin">
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

      {/* ── Editor area ── */}
      <div className="flex-1 bg-surface rounded-xl border border-border flex flex-col overflow-hidden">
        {/* Subject line row */}
        <div className="p-4 border-b border-border">
          <label className="block text-xs font-medium text-text-secondary mb-1.5 uppercase tracking-wide">
            Email Name / Subject Line
          </label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={emails[activeTab]?.subject ?? ""}
              onChange={(e) => updateSubject(e.target.value)}
              placeholder="Enter subject line..."
              className="flex-1 px-4 py-2.5 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-accent-blue transition-colors"
            />

            {/* Insert Variable */}
            <div className="relative">
              <button
                onClick={() => setShowVarDropdown(!showVarDropdown)}
                className="px-3 py-2.5 rounded-lg bg-bg border border-border text-accent-blue text-sm font-medium hover:border-accent-blue/40 transition-colors whitespace-nowrap"
              >
                + Insert Variable
              </button>
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

            {/* Signature button */}
            <button
              onClick={() => setShowSigPanel(!showSigPanel)}
              className="px-3 py-2.5 rounded-lg bg-bg border border-border text-text-secondary text-sm font-medium hover:text-accent-blue hover:border-accent-blue/40 transition-colors whitespace-nowrap"
            >
              Add/Edit Signature
            </button>
          </div>
        </div>

        {/* Signature edit panel (collapsible) */}
        {showSigPanel && (
          <div className="px-4 py-3 border-b border-border bg-bg/50">
            <div className="grid grid-cols-2 gap-3 max-w-xl">
              {(["name", "title", "phone", "email"] as const).map((field) => (
                <input
                  key={field}
                  type="text"
                  value={signature[field]}
                  onChange={(e) => setSignature((s) => ({ ...s, [field]: e.target.value }))}
                  placeholder={field.charAt(0).toUpperCase() + field.slice(1)}
                  className="px-3 py-2 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/50 text-sm focus:outline-none focus:border-accent-blue transition-colors"
                />
              ))}
            </div>
          </div>
        )}

        {/* Rich text toolbar — Word-style grouped buttons */}
        <div className="flex items-center gap-0.5 px-4 py-2 border-b border-border bg-bg/30 flex-wrap">
          {/* Font size */}
          <select
            onChange={(e) => { exec("fontSize", e.target.value); e.target.value = ""; }}
            defaultValue=""
            className="h-8 px-2 rounded bg-surface border border-border text-text-primary text-xs focus:outline-none focus:border-accent-blue mr-1"
          >
            <option value="" disabled>Font Size</option>
            <option value="1">8</option>
            <option value="2">10</option>
            <option value="3">12</option>
            <option value="4">14</option>
            <option value="5">18</option>
            <option value="6">24</option>
            <option value="7">36</option>
          </select>

          <div className="w-px h-5 bg-border mx-1.5" />

          {/* Text style: Bold / Italic / Underline */}
          <button onMouseDown={(e) => { e.preventDefault(); exec("bold"); }} className="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors" title="Bold">
            <span className="text-sm font-bold">B</span>
          </button>
          <button onMouseDown={(e) => { e.preventDefault(); exec("italic"); }} className="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors" title="Italic">
            <span className="text-sm italic font-serif">I</span>
          </button>
          <button onMouseDown={(e) => { e.preventDefault(); exec("underline"); }} className="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors" title="Underline">
            <span className="text-sm underline">U</span>
          </button>

          <div className="w-px h-5 bg-border mx-1.5" />

          {/* Alignment: Left / Center / Right */}
          <button onMouseDown={(e) => { e.preventDefault(); exec("justifyLeft"); }} className="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors" title="Align Left">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" d="M3 6h18M3 12h12M3 18h18" />
            </svg>
          </button>
          <button onMouseDown={(e) => { e.preventDefault(); exec("justifyCenter"); }} className="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors" title="Align Center">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" d="M3 6h18M6 12h12M3 18h18" />
            </svg>
          </button>
          <button onMouseDown={(e) => { e.preventDefault(); exec("justifyRight"); }} className="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors" title="Align Right">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" d="M3 6h18M9 12h12M3 18h18" />
            </svg>
          </button>

          <div className="w-px h-5 bg-border mx-1.5" />

          {/* Lists: Bullet / Numbered */}
          <button onMouseDown={(e) => { e.preventDefault(); exec("insertUnorderedList"); }} className="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors" title="Bullet List">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
            </svg>
          </button>
          <button onMouseDown={(e) => { e.preventDefault(); exec("insertOrderedList"); }} className="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors" title="Numbered List">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" d="M10 6h11M10 12h11M10 18h11" />
              <text x="2" y="8" fill="currentColor" stroke="none" fontSize="7" fontFamily="sans-serif" fontWeight="600">1</text>
              <text x="2" y="14" fill="currentColor" stroke="none" fontSize="7" fontFamily="sans-serif" fontWeight="600">2</text>
              <text x="2" y="20" fill="currentColor" stroke="none" fontSize="7" fontFamily="sans-serif" fontWeight="600">3</text>
            </svg>
          </button>

          <div className="w-px h-5 bg-border mx-1.5" />

          {/* Link */}
          <button
            onMouseDown={(e) => {
              e.preventDefault();
              const url = prompt("Enter URL:");
              if (url) exec("createLink", url);
            }}
            className="w-8 h-8 flex items-center justify-center rounded hover:bg-surface-hover text-text-secondary hover:text-accent-blue transition-colors"
            title="Insert Link"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
            </svg>
          </button>
        </div>

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

      {/* ── Bottom bar ── */}
      <div className="flex items-center justify-end gap-3 mt-4 pb-4">
        <button className="px-5 py-2.5 rounded-lg bg-bg border border-border text-text-secondary text-sm font-medium hover:text-text-primary hover:border-accent-blue/40 transition-colors">
          Save Draft
        </button>
        <button className="px-6 py-2.5 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors">
          Preview &amp; Launch
        </button>
      </div>

      {/* ── Template Browser Modal ── */}
      {showTemplateBrowser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-surface rounded-xl border border-border w-full max-w-3xl mx-4 shadow-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border">
              <h2 className="text-xl font-semibold">Explore Templates</h2>
              <button onClick={() => setShowTemplateBrowser(false)} className="text-text-secondary hover:text-text-primary transition-colors">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {savedTemplates.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-3">Your Templates</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {savedTemplates.map((tmpl, i) => (
                      <button
                        key={`saved-${i}`}
                        onClick={() => applyTemplate(tmpl)}
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
                    ))}
                  </div>
                </div>
              )}
              <div>
                <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-3">Built-in Templates</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {BUILT_IN_TEMPLATES.map((tmpl) => (
                    <button
                      key={tmpl.name}
                      onClick={() => applyTemplate(tmpl)}
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
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Save Template Modal ── */}
      {showSaveTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-surface rounded-xl border border-border p-6 w-full max-w-md mx-4 shadow-2xl">
            <h2 className="text-xl font-semibold mb-4">Save as Template</h2>
            <p className="text-sm text-text-secondary mb-4">
              Save your current {emails.length}-email sequence as a reusable template.
            </p>
            <input
              type="text"
              value={newTemplateName}
              onChange={(e) => setNewTemplateName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") saveAsTemplate(); }}
              placeholder="Template name..."
              className="w-full px-4 py-2.5 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/50 text-sm focus:outline-none focus:border-accent-blue transition-colors mb-3"
              autoFocus
            />
            <div className="flex flex-wrap gap-1 mb-5">
              {emails.map((e, i) => (
                <span key={i} className="px-2 py-0.5 rounded bg-accent-blue/10 text-accent-blue text-xs">{e.name}</span>
              ))}
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowSaveTemplate(false)} className="px-4 py-2 rounded-lg bg-bg border border-border text-text-secondary text-sm font-medium hover:text-text-primary transition-colors">
                Cancel
              </button>
              <button onClick={saveAsTemplate} className="px-5 py-2 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors">
                Save Template
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
