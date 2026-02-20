import PageHeader from "@/components/PageHeader";

export default function DashboardPage() {
  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Welcome to FlowDrop. Your campaigns at a glance." />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-surface rounded-xl border border-border p-6">
          <p className="text-text-secondary text-sm mb-1">Active Campaigns</p>
          <p className="text-3xl font-heading">0</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-6">
          <p className="text-text-secondary text-sm mb-1">Emails Sent</p>
          <p className="text-3xl font-heading">0</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-6">
          <p className="text-text-secondary text-sm mb-1">Open Rate</p>
          <p className="text-3xl font-heading">—</p>
        </div>
      </div>

      <div className="bg-surface rounded-xl border border-border p-8 text-center">
        <p className="text-text-secondary mb-4">No campaigns yet. Create your first campaign to get started.</p>
        <a
          href="/create-campaign"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Create Campaign
        </a>
      </div>
    </div>
  );
}
