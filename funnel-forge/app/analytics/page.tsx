"use client";

import { useState } from "react";
import PageHeader from "@/components/PageHeader";
import { Card, Badge, SectionHeader } from "@/components/ui";
import {
  CAMPAIGNS_LIST,
  OVERVIEW_STATS,
  SEQUENCE_PERFORMANCE,
  RECENT_ACTIVITY,
  TIMEFRAMES,
} from "@/lib/sample-data";

const ACTION_STYLES: Record<string, string> = {
  replied: "text-green-400 bg-green-400/10",
  opened: "text-accent-blue bg-accent-blue/10",
  bounced: "text-red-400 bg-red-400/10",
};

export default function AnalyticsPage() {
  const [campaign, setCampaign] = useState("all");
  const [timeframe, setTimeframe] = useState("30d");
  const maxSent = Math.max(...SEQUENCE_PERFORMANCE.map((s) => s.sent));

  return (
    <div>
      <PageHeader title="Analytics" subtitle="Track your campaign performance." />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <select value={campaign} onChange={(e) => setCampaign(e.target.value)} className="px-3 py-2.5 rounded-lg bg-surface border border-border text-text-primary text-sm focus:outline-none focus:border-accent-blue transition-colors">
          {CAMPAIGNS_LIST.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <div className="flex rounded-lg border border-border overflow-hidden">
          {TIMEFRAMES.map((tf) => (
            <button key={tf} onClick={() => setTimeframe(tf)} className={`px-3 py-2 text-sm font-medium transition-colors ${timeframe === tf ? "bg-accent-blue text-white" : "bg-surface text-text-secondary hover:text-text-primary"}`}>{tf}</button>
          ))}
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
        {OVERVIEW_STATS.map((stat) => (
          <Card key={stat.label} padding="p-4">
            <p className="text-text-secondary text-xs mb-1">{stat.label}</p>
            <p className="text-2xl font-heading font-semibold">{stat.value}</p>
            <span className={`text-xs font-medium ${stat.positive ? "text-green-400" : "text-red-400"}`}>{stat.change}</span>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Sequence performance table */}
        <div className="lg:col-span-2 bg-surface rounded-xl border border-border overflow-hidden">
          <div className="px-5 py-3 border-b border-border bg-bg/50">
            <SectionHeader>Sequence Performance</SectionHeader>
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
                          <div className="h-full rounded-full bg-accent-blue transition-all" style={{ width: `${(row.openRate / 50) * 100}%` }} />
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

        {/* Right column */}
        <div className="space-y-6">
          {/* Funnel */}
          <Card padding="p-5">
            <SectionHeader>Email Funnel</SectionHeader>
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
                  <span className="absolute right-0 top-1/2 -translate-y-1/2 text-xs text-text-secondary">{row.sent.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </Card>

          {/* Recent activity */}
          <div className="bg-surface rounded-xl border border-border overflow-hidden">
            <div className="px-5 py-3 border-b border-border bg-bg/50">
              <SectionHeader>Recent Activity</SectionHeader>
            </div>
            <div className="divide-y divide-border">
              {RECENT_ACTIVITY.map((item, i) => (
                <div key={i} className="flex items-center gap-3 px-5 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium uppercase ${ACTION_STYLES[item.action] ?? "text-text-secondary bg-bg"}`}>
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
