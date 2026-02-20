"use client";

import { useState } from "react";
import PageHeader from "@/components/PageHeader";

/* ── Sample data ── */
const CAMPAIGNS = [
  { id: "all", name: "All Campaigns" },
  { id: "q1-outreach", name: "Q1 Cold Outreach" },
  { id: "nurture-2025", name: "Nurture 2025" },
  { id: "re-engage", name: "Re-engagement" },
];

const OVERVIEW_STATS = [
  { label: "Emails Sent", value: "1,247", change: "+12%", positive: true },
  { label: "Open Rate", value: "42.3%", change: "+3.1%", positive: true },
  { label: "Reply Rate", value: "8.7%", change: "+1.2%", positive: true },
  { label: "Bounce Rate", value: "2.1%", change: "-0.5%", positive: true },
  { label: "Unsubscribed", value: "0.4%", change: "+0.1%", positive: false },
];

const SEQUENCE_PERFORMANCE = [
  { step: "Introduction", sent: 1247, opened: 528, replied: 109, openRate: 42.3, replyRate: 8.7 },
  { step: "Follow Up", sent: 1138, opened: 501, replied: 91, openRate: 44.0, replyRate: 8.0 },
  { step: "Value Add", sent: 1047, opened: 440, replied: 73, openRate: 42.0, replyRate: 7.0 },
  { step: "Per My Voicemail", sent: 974, opened: 370, replied: 58, openRate: 38.0, replyRate: 6.0 },
  { step: "Alignment", sent: 916, opened: 357, replied: 51, openRate: 39.0, replyRate: 5.6 },
  { step: "Check In", sent: 865, opened: 312, replied: 43, openRate: 36.1, replyRate: 5.0 },
  { step: "Close the Loop", sent: 822, opened: 280, replied: 37, openRate: 34.1, replyRate: 4.5 },
];

const RECENT_ACTIVITY = [
  { contact: "Sarah Chen", action: "opened", email: "Introduction", time: "2 min ago" },
  { contact: "Marcus Rivera", action: "replied", email: "Follow Up", time: "15 min ago" },
  { contact: "Emily Okafor", action: "opened", email: "Value Add", time: "1 hr ago" },
  { contact: "James Thornton", action: "bounced", email: "Introduction", time: "2 hrs ago" },
  { contact: "Priya Mehta", action: "opened", email: "Check In", time: "3 hrs ago" },
  { contact: "Alex Kim", action: "replied", email: "Introduction", time: "4 hrs ago" },
  { contact: "Jordan Lee", action: "opened", email: "Follow Up", time: "5 hrs ago" },
];

const TIMEFRAMES = ["7d", "14d", "30d", "90d"];

export default function AnalyticsPage() {
  const [campaign, setCampaign] = useState("all");
  const [timeframe, setTimeframe] = useState("30d");

  const actionColor = (action: string) => {
    switch (action) {
      case "replied": return "text-green-400 bg-green-400/10";
      case "opened": return "text-accent-blue bg-accent-blue/10";
      case "bounced": return "text-red-400 bg-red-400/10";
      default: return "text-text-secondary bg-bg";
    }
  };

  /* Simple CSS bar chart */
  const maxSent = Math.max(...SEQUENCE_PERFORMANCE.map((s) => s.sent));

  return (
    <div>
      <PageHeader title="Analytics" subtitle="Track your campaign performance." />

      {/* ── Filters ── */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <select
          value={campaign}
          onChange={(e) => setCampaign(e.target.value)}
          className="px-3 py-2.5 rounded-lg bg-surface border border-border text-text-primary text-sm focus:outline-none focus:border-accent-blue transition-colors"
        >
          {CAMPAIGNS.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <div className="flex rounded-lg border border-border overflow-hidden">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-3 py-2 text-sm font-medium transition-colors ${
                timeframe === tf
                  ? "bg-accent-blue text-white"
                  : "bg-surface text-text-secondary hover:text-text-primary"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
        {OVERVIEW_STATS.map((stat) => (
          <div key={stat.label} className="bg-surface rounded-xl border border-border p-4">
            <p className="text-text-secondary text-xs mb-1">{stat.label}</p>
            <p className="text-2xl font-heading font-semibold">{stat.value}</p>
            <span className={`text-xs font-medium ${stat.positive ? "text-green-400" : "text-red-400"}`}>
              {stat.change}
            </span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Sequence performance table + bar chart ── */}
        <div className="lg:col-span-2 bg-surface rounded-xl border border-border overflow-hidden">
          <div className="px-5 py-3 border-b border-border bg-bg/50">
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide">Sequence Performance</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-5 py-3 text-left text-text-secondary font-medium">Step</th>
                  <th className="px-4 py-3 text-right text-text-secondary font-medium">Sent</th>
                  <th className="px-4 py-3 text-right text-text-secondary font-medium">Opened</th>
                  <th className="px-4 py-3 text-right text-text-secondary font-medium">Replied</th>
                  <th className="px-4 py-3 text-left text-text-secondary font-medium w-40">Open Rate</th>
                </tr>
              </thead>
              <tbody>
                {SEQUENCE_PERFORMANCE.map((row) => (
                  <tr key={row.step} className="border-b border-border last:border-0 hover:bg-surface-hover/30 transition-colors">
                    <td className="px-5 py-3 text-text-primary font-medium">{row.step}</td>
                    <td className="px-4 py-3 text-right text-text-secondary">{row.sent.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-text-secondary">{row.opened.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-accent-blue font-medium">{row.replied}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 rounded-full bg-bg overflow-hidden">
                          <div
                            className="h-full rounded-full bg-accent-blue transition-all"
                            style={{ width: `${(row.openRate / 50) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-text-secondary w-10 text-right">{row.openRate}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── Right column ── */}
        <div className="space-y-6">
          {/* Funnel visualization */}
          <div className="bg-surface rounded-xl border border-border p-5">
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-4">Email Funnel</h2>
            <div className="space-y-2">
              {SEQUENCE_PERFORMANCE.map((row, i) => (
                <div key={row.step} className="relative">
                  <div
                    className="h-8 rounded-lg flex items-center px-3 transition-all"
                    style={{
                      width: `${(row.sent / maxSent) * 100}%`,
                      background: `rgba(56, 197, 178, ${0.15 + (1 - i / SEQUENCE_PERFORMANCE.length) * 0.25})`,
                    }}
                  >
                    <span className="text-xs text-text-primary font-medium truncate">{row.step}</span>
                  </div>
                  <span className="absolute right-0 top-1/2 -translate-y-1/2 text-xs text-text-secondary">
                    {row.sent.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Recent activity */}
          <div className="bg-surface rounded-xl border border-border overflow-hidden">
            <div className="px-5 py-3 border-b border-border bg-bg/50">
              <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide">Recent Activity</h2>
            </div>
            <div className="divide-y divide-border">
              {RECENT_ACTIVITY.map((item, i) => (
                <div key={i} className="flex items-center gap-3 px-5 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium uppercase ${actionColor(item.action)}`}>
                    {item.action}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text-primary truncate">
                      <span className="font-medium">{item.contact}</span>
                      <span className="text-text-secondary"> — {item.email}</span>
                    </p>
                  </div>
                  <span className="text-xs text-text-secondary flex-shrink-0">{item.time}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
