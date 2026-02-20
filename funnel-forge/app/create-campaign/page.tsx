"use client";

import { useState } from "react";
import PageHeader from "@/components/PageHeader";
import AIChatPanel from "@/components/AIChatPanel";
import SavedCampaignsList from "@/components/campaigns/SavedCampaignsList";
import ManualCampaignForm from "@/components/campaigns/ManualCampaignForm";
import { BackButton, PlusIcon, FolderIcon, SparklesIcon } from "@/components/ui";

type Mode = "choose" | "manual" | "ai" | "saved";

const CARDS = [
  {
    mode: "manual" as Mode,
    title: "New Campaign",
    description: "Build a campaign from scratch with full control over every detail.",
    icon: PlusIcon,
    accent: "accent-blue",
  },
  {
    mode: "saved" as Mode,
    title: "Saved Campaigns",
    description: "View and manage all your saved campaign drafts and templates.",
    icon: FolderIcon,
    accent: "accent-purple",
  },
  {
    mode: "ai" as Mode,
    title: "Build with AI",
    description: "Describe your goals and let AI generate a complete campaign for you.",
    icon: SparklesIcon,
    accent: "accent-blue",
  },
];

export default function CreateCampaignPage() {
  const [mode, setMode] = useState<Mode>("choose");

  if (mode === "ai") {
    return (
      <div>
        <PageHeader title="Build with AI Chat" subtitle="Describe your campaign goals and let AI generate your email sequence." />
        <BackButton onClick={() => setMode("choose")} />
        <AIChatPanel />
      </div>
    );
  }

  if (mode === "saved") {
    return (
      <div>
        <PageHeader title="Saved Campaigns" subtitle="View and manage your saved campaign drafts." />
        <SavedCampaignsList onBack={() => setMode("choose")} />
      </div>
    );
  }

  if (mode === "manual") {
    return (
      <div>
        <PageHeader title="Build Manually" subtitle="Set up your campaign details step by step." />
        <ManualCampaignForm onBack={() => setMode("choose")} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Create Campaign" subtitle="Choose how you'd like to build your email campaign." />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl">
        {CARDS.map((card) => {
          const Icon = card.icon;
          return (
            <button
              key={card.mode}
              onClick={() => setMode(card.mode)}
              className={`group bg-surface rounded-xl border border-border p-8 text-left hover:border-${card.accent}/50 transition-all`}
            >
              <div className={`w-12 h-12 rounded-lg bg-${card.accent}/10 flex items-center justify-center mb-5`}>
                <Icon className={`w-6 h-6 text-${card.accent}`} />
              </div>
              <h2 className={`text-xl mb-2 group-hover:text-${card.accent} transition-colors`}>{card.title}</h2>
              <p className="text-text-secondary text-sm leading-relaxed">{card.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
