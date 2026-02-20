"use client";

import { useRouter } from "next/navigation";
import { BackButton, Button, Input, Card } from "@/components/ui";

interface Props {
  onBack: () => void;
}

export default function ManualCampaignForm({ onBack }: Props) {
  const router = useRouter();

  return (
    <>
      <BackButton onClick={onBack} />
      <Card className="max-w-2xl space-y-6">
        <Input label="Campaign Name" placeholder="e.g. Q1 Outreach Sequence" />
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1 uppercase tracking-wide">
            Campaign Type
          </label>
          <select className="w-full px-4 py-2.5 rounded-lg bg-bg border border-border text-text-primary focus:outline-none focus:border-accent-blue transition-colors text-sm">
            <option value="cold">Cold Outreach</option>
            <option value="nurture">Nurture Sequence</option>
            <option value="followup">Follow-Up</option>
            <option value="stay-connected">Stay Connected</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1 uppercase tracking-wide">
            Description
          </label>
          <textarea
            rows={3}
            placeholder="What's the goal of this campaign?"
            className="w-full px-4 py-2.5 rounded-lg bg-bg border border-border text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus:border-accent-blue transition-colors resize-none text-sm"
          />
        </div>
        <Button onClick={() => router.push("/create-campaign/email-editor")}>
          Continue to Build Emails
        </Button>
      </Card>
    </>
  );
}
