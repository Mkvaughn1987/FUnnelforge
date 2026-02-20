import PageHeader from "@/components/PageHeader";
export default function AnalyticsPage() {
  return (
    <div>
      <PageHeader title="Analytics" subtitle="Track your campaign performance." />
      <div className="bg-surface rounded-xl border border-border p-8 text-center">
        <p className="text-text-secondary">
          Analytics will appear here once you start sending campaigns.
        </p>
      </div>
    </div>
  );
}
