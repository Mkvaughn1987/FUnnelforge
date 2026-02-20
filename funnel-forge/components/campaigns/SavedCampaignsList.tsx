"use client";

import { useRouter } from "next/navigation";
import { BackButton, Card, Badge, EnvelopeIcon, ChevronRightIcon } from "@/components/ui";
import { SAVED_CAMPAIGNS } from "@/lib/sample-data";

interface Props {
  onBack: () => void;
}

export default function SavedCampaignsList({ onBack }: Props) {
  const router = useRouter();

  return (
    <>
      <BackButton onClick={onBack} />
      <div className="space-y-3 max-w-3xl">
        {SAVED_CAMPAIGNS.map((c) => (
          <button
            key={c.id}
            onClick={() => router.push("/create-campaign/email-editor")}
            className="w-full flex items-center gap-4 bg-surface rounded-xl border border-border p-5 text-left hover:border-accent-blue/50 transition-all group"
          >
            <div className="w-10 h-10 rounded-lg bg-accent-blue/10 flex items-center justify-center flex-shrink-0">
              <EnvelopeIcon className="w-5 h-5 text-accent-blue" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary group-hover:text-accent-blue transition-colors">{c.name}</p>
              <p className="text-xs text-text-secondary">{c.type} &middot; {c.emails} emails &middot; Updated {c.updated}</p>
            </div>
            <Badge variant={c.status === "Active" ? "success" : "default"}>
              {c.status}
            </Badge>
            <ChevronRightIcon className="w-4 h-4 text-text-secondary group-hover:text-accent-blue transition-colors flex-shrink-0" />
          </button>
        ))}
      </div>
    </>
  );
}
