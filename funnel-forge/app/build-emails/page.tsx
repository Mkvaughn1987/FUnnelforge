import PageHeader from "@/components/PageHeader";

export default function BuildEmailsPage() {
  return (
    <div>
      <PageHeader title="Build Emails" subtitle="Craft and edit your email sequences." />

      <div className="bg-surface rounded-xl border border-border p-8 text-center">
        <p className="text-text-secondary">
          Select a campaign first, then build your email sequence here.
        </p>
      </div>
    </div>
  );
}
