import PageHeader from "@/components/PageHeader";
import { Card, PlusIcon } from "@/components/ui";

export default function DashboardPage() {
  const stats = [
    { label: "Active Campaigns", value: "0" },
    { label: "Emails Sent", value: "0" },
    { label: "Open Rate", value: "\u2014" },
  ];

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Welcome to FlowDrop. Your campaigns at a glance." />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {stats.map((s) => (
          <Card key={s.label}>
            <p className="text-text-secondary text-sm mb-1">{s.label}</p>
            <p className="text-3xl font-heading">{s.value}</p>
          </Card>
        ))}
      </div>

      <Card className="text-center" padding="p-8">
        <p className="text-text-secondary mb-4">No campaigns yet. Create your first campaign to get started.</p>
        <a
          href="/create-campaign"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors"
        >
          <PlusIcon />
          Create Campaign
        </a>
      </Card>
    </div>
  );
}
