"use client";
import { useState } from "react";
import PageHeader from "@/components/PageHeader";
import AIChatPanel from "@/components/AIChatPanel";
export default function CreateCampaignPage() {
  const [mode, setMode] = useState<"choose" | "manual" | "ai">("choose");
  if (mode === "ai") {
    return (
      <div>
        <PageHeader title="Build with AI Chat" subtitle="Describe your campaign goals and let AI generate your email sequence." />
        <button
          onClick={() => setMode("choose")}
          className="flex items-center gap-2 text-text-secondary hover:text-text-primary text-sm mb-6 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
          </svg>
          Back
        </button>
        <AIChatPanel />
      </div>
    );
  }
  if (mode === "manual") {
    return (
      <div>
        <PageHeader title="Build Manually" subtitle="Set up your campaign details step by step." />
        <button
          onClick={() => setMode("choose")}
          className="flex items-center gap-2 text-text-secondary hover:text-text-primary text-sm mb-6 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
          </svg>
          Back
        </button>
        <div className="bg-surface rounded-xl border border-border p-6 space-y-6 max-w-2xl">
          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              Campaign Name
            </label>
            <input
              type="text"
              placeholder="e.g. Q1 Outreach Sequence"
              className="w-full px-4 py-2.5 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-accent-blue transition-colors"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              Campaign Type
            </label>
            <select className="w-full px-4 py-2.5 rounded-lg bg-bg border border-border text-text-primary focus:outline-none focus:border-accent-blue transition-colors">
              <option value="cold">Cold Outreach</option>
              <option value="nurture">Nurture Sequence</option>
              <option value="followup">Follow-Up</option>
              <option value="stay-connected">Stay Connected</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-text-primary mb-2">
              Description
            </label>
            <textarea
              rows={3}
              placeholder="What's the goal of this campaign?"
              className="w-full px-4 py-2.5 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-accent-blue transition-colors resize-none"
            />
          </div>
          <button className="px-5 py-2.5 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors">
            Continue to Build Emails
          </button>
        </div>
      </div>
    );
  }
  // Default: choose mode — 2x2 grid
  return (
    <div>
      <PageHeader title="Create Campaign" subtitle="Choose how you'd like to build your email campaign." />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl">
        {/* New Campaign */}
        <button
          onClick={() => setMode("manual")}
          className="group bg-surface rounded-xl border border-border p-8 text-left hover:border-accent-blue/50 transition-all"
        >
          <div className="w-12 h-12 rounded-lg bg-accent-blue/10 flex items-center justify-center mb-5">
            <svg className="w-6 h-6 text-accent-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </div>
          <h2 className="text-xl mb-2 group-hover:text-accent-blue transition-colors">New Campaign</h2>
          <p className="text-text-secondary text-sm leading-relaxed">
            Build a campaign from scratch with full control over every detail.
          </p>
        </button>
        {/* Saved Campaigns */}
        <button
          className="group bg-surface rounded-xl border border-border p-8 text-left hover:border-accent-purple/50 transition-all"
        >
          <div className="w-12 h-12 rounded-lg bg-accent-purple/10 flex items-center justify-center mb-5">
            <svg className="w-6 h-6 text-accent-purple" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z" />
            </svg>
          </div>
          <h2 className="text-xl mb-2 group-hover:text-accent-purple transition-colors">Saved Campaigns</h2>
          <p className="text-text-secondary text-sm leading-relaxed">
            View and manage all your saved campaign drafts and templates.
          </p>
        </button>
        {/* Build with AI */}
        <button
          onClick={() => setMode("ai")}
          className="group bg-surface rounded-xl border border-border p-8 text-left hover:border-accent-blue/50 transition-all"
        >
          <div className="w-12 h-12 rounded-lg bg-accent-blue/10 flex items-center justify-center mb-5">
            <svg className="w-6 h-6 text-accent-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
            </svg>
          </div>
          <h2 className="text-xl mb-2 group-hover:text-accent-blue transition-colors">Build with AI</h2>
          <p className="text-text-secondary text-sm leading-relaxed">
            Describe your goals and let AI generate a complete campaign for you.
          </p>
        </button>
      </div>
    </div>
  );
}
