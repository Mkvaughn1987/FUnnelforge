"use client";

import { useState } from "react";
import PageHeader from "@/components/PageHeader";

/* ── Types ── */
interface ScheduleStep {
  id: string;
  emailName: string;
  delayDays: number;
  sendTime: string;
}

const DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const DEFAULT_STEPS: ScheduleStep[] = [
  { id: "1", emailName: "Introduction", delayDays: 0, sendTime: "09:00" },
  { id: "2", emailName: "Follow Up", delayDays: 3, sendTime: "09:00" },
  { id: "3", emailName: "Value Add", delayDays: 5, sendTime: "10:00" },
  { id: "4", emailName: "Per My Voicemail", delayDays: 7, sendTime: "09:00" },
  { id: "5", emailName: "Alignment", delayDays: 10, sendTime: "10:00" },
  { id: "6", emailName: "Check In", delayDays: 14, sendTime: "09:00" },
  { id: "7", emailName: "Close the Loop", delayDays: 21, sendTime: "09:00" },
];

const PRESETS: { label: string; description: string; steps: ScheduleStep[] }[] = [
  {
    label: "Aggressive (5 days)",
    description: "Daily emails for a quick push",
    steps: DEFAULT_STEPS.map((s, i) => ({ ...s, delayDays: i })),
  },
  {
    label: "Standard (21 days)",
    description: "Balanced cadence over 3 weeks",
    steps: DEFAULT_STEPS,
  },
  {
    label: "Gentle (45 days)",
    description: "Spaced out over 6+ weeks",
    steps: DEFAULT_STEPS.map((s, i) => ({ ...s, delayDays: i * 7 })),
  },
];

export default function SendSchedulePage() {
  const [steps, setSteps] = useState<ScheduleStep[]>(DEFAULT_STEPS);
  const [activeDays, setActiveDays] = useState<Set<string>>(new Set(["Mon", "Tue", "Wed", "Thu", "Fri"]));
  const [timezone, setTimezone] = useState("America/New_York");
  const [startDate, setStartDate] = useState("");
  const [dailyLimit, setDailyLimit] = useState(50);
  const [delayBetween, setDelayBetween] = useState(60);

  const toggleDay = (day: string) => {
    setActiveDays((prev) => {
      const next = new Set(prev);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });
  };

  const updateStep = (id: string, field: keyof ScheduleStep, value: string | number) => {
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, [field]: value } : s)));
  };

  const applyPreset = (preset: typeof PRESETS[number]) => {
    setSteps(preset.steps.map((s) => ({ ...s })));
  };

  /* ── Timeline visualization ── */
  const maxDays = Math.max(...steps.map((s) => s.delayDays), 1);

  return (
    <div>
      <PageHeader title="Send Schedule" subtitle="Configure when your emails are sent." />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Left: Schedule settings ── */}
        <div className="lg:col-span-2 space-y-6">
          {/* Presets */}
          <div className="bg-surface rounded-xl border border-border p-5">
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-3">Quick Presets</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  onClick={() => applyPreset(preset)}
                  className="text-left p-3 rounded-lg bg-bg border border-border hover:border-accent-blue/40 transition-colors"
                >
                  <p className="text-sm font-medium text-text-primary">{preset.label}</p>
                  <p className="text-xs text-text-secondary mt-0.5">{preset.description}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Timeline visual */}
          <div className="bg-surface rounded-xl border border-border p-5">
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-4">Sequence Timeline</h2>
            <div className="relative">
              {/* Track line */}
              <div className="absolute top-4 left-4 right-4 h-0.5 bg-border rounded-full" />
              <div className="flex justify-between relative px-4">
                {steps.map((step, i) => {
                  const pct = maxDays > 0 ? (step.delayDays / maxDays) * 100 : (i / (steps.length - 1)) * 100;
                  return (
                    <div
                      key={step.id}
                      className="flex flex-col items-center"
                      style={{ position: "absolute", left: `${pct}%`, transform: "translateX(-50%)" }}
                    >
                      <div className="w-8 h-8 rounded-full bg-accent-blue/20 border-2 border-accent-blue flex items-center justify-center text-xs font-bold text-accent-blue">
                        {i + 1}
                      </div>
                      <p className="text-[10px] text-text-secondary mt-1 whitespace-nowrap">Day {step.delayDays}</p>
                    </div>
                  );
                })}
              </div>
              <div className="h-14" />
            </div>
          </div>

          {/* Step-by-step schedule */}
          <div className="bg-surface rounded-xl border border-border overflow-hidden">
            <div className="px-5 py-3 border-b border-border bg-bg/50">
              <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide">Email Sequence</h2>
            </div>
            <div className="divide-y divide-border">
              {steps.map((step, i) => (
                <div key={step.id} className="flex items-center gap-4 px-5 py-4 hover:bg-surface-hover/30 transition-colors">
                  <div className="w-8 h-8 rounded-full bg-accent-blue/10 flex items-center justify-center text-sm font-bold text-accent-blue flex-shrink-0">
                    {i + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">{step.emailName}</p>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <div className="flex items-center gap-1.5">
                      <label className="text-xs text-text-secondary">Day</label>
                      <input
                        type="number"
                        min={0}
                        value={step.delayDays}
                        onChange={(e) => updateStep(step.id, "delayDays", parseInt(e.target.value) || 0)}
                        className="w-16 px-2 py-1.5 rounded-lg bg-bg border border-border text-text-primary text-sm text-center focus:outline-none focus:border-accent-blue transition-colors"
                      />
                    </div>
                    <div className="flex items-center gap-1.5">
                      <label className="text-xs text-text-secondary">Time</label>
                      <input
                        type="time"
                        value={step.sendTime}
                        onChange={(e) => updateStep(step.id, "sendTime", e.target.value)}
                        className="px-2 py-1.5 rounded-lg bg-bg border border-border text-text-primary text-sm focus:outline-none focus:border-accent-blue transition-colors"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Right: Global settings ── */}
        <div className="space-y-6">
          {/* Sending days */}
          <div className="bg-surface rounded-xl border border-border p-5">
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-3">Sending Days</h2>
            <div className="flex flex-wrap gap-2">
              {DAYS_OF_WEEK.map((day) => (
                <button
                  key={day}
                  onClick={() => toggleDay(day)}
                  className={`w-11 h-11 rounded-lg text-xs font-medium transition-colors ${
                    activeDays.has(day)
                      ? "bg-accent-blue text-white"
                      : "bg-bg border border-border text-text-secondary hover:border-accent-blue/40"
                  }`}
                >
                  {day}
                </button>
              ))}
            </div>
          </div>

          {/* Timezone */}
          <div className="bg-surface rounded-xl border border-border p-5">
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-3">Timezone</h2>
            <select
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg bg-bg border border-border text-text-primary text-sm focus:outline-none focus:border-accent-blue transition-colors"
            >
              <option value="America/New_York">Eastern (ET)</option>
              <option value="America/Chicago">Central (CT)</option>
              <option value="America/Denver">Mountain (MT)</option>
              <option value="America/Los_Angeles">Pacific (PT)</option>
              <option value="UTC">UTC</option>
            </select>
          </div>

          {/* Start date */}
          <div className="bg-surface rounded-xl border border-border p-5">
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-3">Start Date</h2>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg bg-bg border border-border text-text-primary text-sm focus:outline-none focus:border-accent-blue transition-colors"
            />
          </div>

          {/* Sending limits */}
          <div className="bg-surface rounded-xl border border-border p-5 space-y-4">
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide">Sending Limits</h2>
            <div>
              <label className="block text-xs text-text-secondary mb-1.5">Daily email limit</label>
              <input
                type="number"
                min={1}
                max={500}
                value={dailyLimit}
                onChange={(e) => setDailyLimit(parseInt(e.target.value) || 50)}
                className="w-full px-3 py-2.5 rounded-lg bg-bg border border-border text-text-primary text-sm focus:outline-none focus:border-accent-blue transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1.5">Delay between emails (seconds)</label>
              <input
                type="number"
                min={10}
                max={600}
                value={delayBetween}
                onChange={(e) => setDelayBetween(parseInt(e.target.value) || 60)}
                className="w-full px-3 py-2.5 rounded-lg bg-bg border border-border text-text-primary text-sm focus:outline-none focus:border-accent-blue transition-colors"
              />
            </div>
          </div>

          {/* Summary */}
          <div className="bg-surface rounded-xl border border-border p-5">
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wide mb-3">Summary</h2>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-text-secondary">Emails in sequence</span>
                <span className="text-text-primary font-medium">{steps.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Total duration</span>
                <span className="text-text-primary font-medium">{maxDays} days</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Active send days</span>
                <span className="text-text-primary font-medium">{activeDays.size}/week</span>
              </div>
            </div>
          </div>

          {/* Save */}
          <button className="w-full px-5 py-3 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/90 transition-colors">
            Save Schedule
          </button>
        </div>
      </div>
    </div>
  );
}
