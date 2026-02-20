import type {
  Contact,
  EmailTab,
  Template,
  ScheduleStep,
  Campaign,
  OverviewStat,
  SequencePerformance,
  ActivityItem,
} from "./types";

/* ── Contacts ── */

export const EMPTY_CONTACT: Omit<Contact, "id"> = {
  firstName: "",
  lastName: "",
  email: "",
  personalEmail: "",
  company: "",
  title: "",
  phone: "",
  workPhone: "",
  mobilePhone: "",
  linkedIn: "",
  city: "",
  state: "",
  industry: "",
  tags: [],
};

export const SAMPLE_CONTACTS: Contact[] = [
  { id: "1", firstName: "Sarah", lastName: "Chen", email: "sarah@acmecorp.com", personalEmail: "", company: "Acme Corp", title: "VP of Sales", phone: "(555) 123-4567", workPhone: "", mobilePhone: "", linkedIn: "", city: "Nashville", state: "Tennessee", industry: "Technology", tags: ["prospect"] },
  { id: "2", firstName: "Marcus", lastName: "Rivera", email: "marcus@globex.io", personalEmail: "", company: "Globex Inc", title: "CTO", phone: "(555) 234-5678", workPhone: "", mobilePhone: "", linkedIn: "", city: "Denver", state: "Colorado", industry: "Software", tags: ["lead", "tech"] },
  { id: "3", firstName: "Emily", lastName: "Okafor", email: "emily@brightwavehq.com", personalEmail: "", company: "Brightwave HQ", title: "Marketing Director", phone: "(555) 345-6789", workPhone: "", mobilePhone: "", linkedIn: "", city: "Atlanta", state: "Georgia", industry: "Marketing", tags: ["lead"] },
  { id: "4", firstName: "James", lastName: "Thornton", email: "james@nimbusdata.co", personalEmail: "", company: "Nimbus Data", title: "CEO", phone: "(555) 456-7890", workPhone: "", mobilePhone: "", linkedIn: "", city: "Austin", state: "Texas", industry: "Data", tags: ["prospect", "decision-maker"] },
  { id: "5", firstName: "Priya", lastName: "Mehta", email: "priya@zenithsoftware.com", personalEmail: "", company: "Zenith Software", title: "Head of Partnerships", phone: "(555) 567-8901", workPhone: "", mobilePhone: "", linkedIn: "", city: "San Francisco", state: "California", industry: "SaaS", tags: ["partner"] },
];

/* ── Email editor ── */

export const DEFAULT_EMAIL_TABS: EmailTab[] = [
  { name: "Introduction", subject: "", body: "" },
  { name: "Follow Up", subject: "", body: "" },
  { name: "Value Add", subject: "", body: "" },
  { name: "Per My Voicemail", subject: "", body: "" },
  { name: "Alignment", subject: "", body: "" },
  { name: "Check In", subject: "", body: "" },
  { name: "Close the Loop", subject: "", body: "" },
];

export const VARIABLES = ["{FirstName}", "{LastName}", "{Company}", "{Title}", "{Phone}"];

export const BUILT_IN_TEMPLATES: Template[] = [
  {
    name: "Cold Outreach",
    emails: [
      { name: "Introduction", subject: "Quick intro \u2014 {Company} + your team", body: "<p>Hi {FirstName},</p><p>I came across {Company} and wanted to reach out. We help teams like yours streamline their outreach and close deals faster.</p><p>Would you be open to a quick 15-minute call this week?</p>" },
      { name: "Follow Up", subject: "Following up \u2014 {FirstName}", body: "<p>Hi {FirstName},</p><p>Just circling back on my note from a few days ago. I know things get busy \u2014 I\u2019d love to find a time that works for a brief chat.</p><p>Any interest?</p>" },
      { name: "Value Add", subject: "Thought you'd find this useful", body: "<p>Hi {FirstName},</p><p>I wanted to share a resource that\u2019s been helping similar teams in your space see 30%+ improvement in response rates.</p><p>Happy to walk you through it if you\u2019re interested.</p>" },
      { name: "Break Up", subject: "Should I close your file?", body: "<p>Hi {FirstName},</p><p>I haven\u2019t heard back, so I\u2019ll assume the timing isn\u2019t right. No hard feelings \u2014 I\u2019ll close out your file for now.</p><p>If anything changes, feel free to reach out anytime.</p>" },
    ],
  },
  {
    name: "Sales Funnel",
    emails: [
      { name: "Introduction", subject: "Helping {Company} grow", body: "<p>Hi {FirstName},</p><p>I noticed {Company} is expanding \u2014 congrats! We specialize in helping growing teams like yours scale their sales outreach without adding headcount.</p><p>Worth a quick conversation?</p>" },
      { name: "Social Proof", subject: "How [Client] increased pipeline by 40%", body: "<p>Hi {FirstName},</p><p>Wanted to share a quick win \u2014 one of our clients in a similar space saw a 40% increase in qualified pipeline within 60 days of using our platform.</p><p>I\u2019d love to show you how we could do the same for {Company}.</p>" },
      { name: "Case Study", subject: "Case study for {Company}", body: "<p>Hi {FirstName},</p><p>I put together a brief case study that\u2019s directly relevant to what you\u2019re doing at {Company}. It covers the exact playbook our top-performing customers use.</p><p>Want me to send it over?</p>" },
      { name: "Demo Offer", subject: "Free demo \u2014 see it in action", body: "<p>Hi {FirstName},</p><p>Sometimes seeing is believing. I\u2019d love to give you a personalized 15-minute demo showing exactly how this would work for {Company}.</p><p>No strings attached \u2014 just pick a time that works.</p>" },
      { name: "Close the Loop", subject: "Last note from me", body: "<p>Hi {FirstName},</p><p>I don\u2019t want to be that person who keeps filling your inbox, so this will be my last reach-out for now.</p><p>If you ever want to revisit this, my door is always open. Wishing you and the {Company} team continued success!</p>" },
    ],
  },
  {
    name: "Welcome Series",
    emails: [
      { name: "Welcome", subject: "Welcome aboard, {FirstName}!", body: "<p>Hi {FirstName},</p><p>Welcome! We\u2019re thrilled to have you on board. Here\u2019s a quick overview of what you can expect over the next few days as we help you get started.</p>" },
      { name: "Getting Started", subject: "Your first steps", body: "<p>Hi {FirstName},</p><p>Ready to dive in? Here are 3 quick things you can do right now to get the most out of your account:</p><ol><li>Complete your profile</li><li>Import your contacts</li><li>Send your first campaign</li></ol>" },
      { name: "Tips & Tricks", subject: "Pro tips to save you time", body: "<p>Hi {FirstName},</p><p>Now that you\u2019ve had a chance to explore, here are some insider tips our power users swear by to get even better results.</p>" },
      { name: "Check In", subject: "How's it going, {FirstName}?", body: "<p>Hi {FirstName},</p><p>Just checking in \u2014 how are things going so far? If you have any questions or need help, I\u2019m here for you.</p><p>Hit reply and let me know!</p>" },
    ],
  },
  {
    name: "Re-engagement",
    emails: [
      { name: "We Miss You", subject: "It's been a while, {FirstName}", body: "<p>Hi {FirstName},</p><p>We noticed it\u2019s been a while since we last connected. A lot has changed on our end, and I think you\u2019d be impressed with what\u2019s new.</p><p>Worth catching up?</p>" },
      { name: "What's New", subject: "You're missing out on some big updates", body: "<p>Hi {FirstName},</p><p>Since we last spoke, we\u2019ve launched several features that directly address the challenges you mentioned. I\u2019d love to show you what\u2019s changed.</p>" },
      { name: "Special Offer", subject: "Something special for you, {FirstName}", body: "<p>Hi {FirstName},</p><p>As a valued contact, I wanted to extend a special offer your way. Let me know if you\u2019d like to hear the details \u2014 no pressure.</p>" },
      { name: "Final Check", subject: "Should I keep you on our list?", body: "<p>Hi {FirstName},</p><p>I want to respect your inbox. If you\u2019re no longer interested, no worries at all \u2014 just let me know and I\u2019ll update your preferences.</p><p>But if you\u2019re still open to hearing from us, I\u2019ve got some great stuff to share.</p>" },
    ],
  },
];

/* ── Schedule ── */

export const DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

export const DEFAULT_SCHEDULE_STEPS: ScheduleStep[] = [
  { id: "1", emailName: "Introduction", delayDays: 0, sendTime: "09:00" },
  { id: "2", emailName: "Follow Up", delayDays: 3, sendTime: "09:00" },
  { id: "3", emailName: "Value Add", delayDays: 5, sendTime: "10:00" },
  { id: "4", emailName: "Per My Voicemail", delayDays: 7, sendTime: "09:00" },
  { id: "5", emailName: "Alignment", delayDays: 10, sendTime: "10:00" },
  { id: "6", emailName: "Check In", delayDays: 14, sendTime: "09:00" },
  { id: "7", emailName: "Close the Loop", delayDays: 21, sendTime: "09:00" },
];

export const SCHEDULE_PRESETS: { label: string; description: string; steps: ScheduleStep[] }[] = [
  {
    label: "Aggressive (5 days)",
    description: "Daily emails for a quick push",
    steps: DEFAULT_SCHEDULE_STEPS.map((s, i) => ({ ...s, delayDays: i })),
  },
  {
    label: "Standard (21 days)",
    description: "Balanced cadence over 3 weeks",
    steps: DEFAULT_SCHEDULE_STEPS,
  },
  {
    label: "Gentle (45 days)",
    description: "Spaced out over 6+ weeks",
    steps: DEFAULT_SCHEDULE_STEPS.map((s, i) => ({ ...s, delayDays: i * 7 })),
  },
];

/* ── Analytics ── */

export const CAMPAIGNS_LIST: Campaign[] = [
  { id: "all", name: "All Campaigns", type: "", emails: 0, status: "", updated: "" },
  { id: "q1-outreach", name: "Q1 Cold Outreach", type: "Cold Outreach", emails: 7, status: "Active", updated: "Feb 18, 2026" },
  { id: "nurture-2025", name: "Nurture 2025", type: "Nurture Sequence", emails: 5, status: "Active", updated: "Feb 15, 2026" },
  { id: "re-engage", name: "Re-engagement", type: "Follow-Up", emails: 4, status: "Draft", updated: "Feb 10, 2026" },
];

export const SAVED_CAMPAIGNS = CAMPAIGNS_LIST.filter((c) => c.id !== "all");

export const OVERVIEW_STATS: OverviewStat[] = [
  { label: "Emails Sent", value: "1,247", change: "+12%", positive: true },
  { label: "Open Rate", value: "42.3%", change: "+3.1%", positive: true },
  { label: "Reply Rate", value: "8.7%", change: "+1.2%", positive: true },
  { label: "Bounce Rate", value: "2.1%", change: "-0.5%", positive: true },
  { label: "Unsubscribed", value: "0.4%", change: "+0.1%", positive: false },
];

export const SEQUENCE_PERFORMANCE: SequencePerformance[] = [
  { step: "Introduction", sent: 1247, opened: 528, replied: 109, openRate: 42.3, replyRate: 8.7 },
  { step: "Follow Up", sent: 1138, opened: 501, replied: 91, openRate: 44.0, replyRate: 8.0 },
  { step: "Value Add", sent: 1047, opened: 440, replied: 73, openRate: 42.0, replyRate: 7.0 },
  { step: "Per My Voicemail", sent: 974, opened: 370, replied: 58, openRate: 38.0, replyRate: 6.0 },
  { step: "Alignment", sent: 916, opened: 357, replied: 51, openRate: 39.0, replyRate: 5.6 },
  { step: "Check In", sent: 865, opened: 312, replied: 43, openRate: 36.1, replyRate: 5.0 },
  { step: "Close the Loop", sent: 822, opened: 280, replied: 37, openRate: 34.1, replyRate: 4.5 },
];

export const RECENT_ACTIVITY: ActivityItem[] = [
  { contact: "Sarah Chen", action: "opened", email: "Introduction", time: "2 min ago" },
  { contact: "Marcus Rivera", action: "replied", email: "Follow Up", time: "15 min ago" },
  { contact: "Emily Okafor", action: "opened", email: "Value Add", time: "1 hr ago" },
  { contact: "James Thornton", action: "bounced", email: "Introduction", time: "2 hrs ago" },
  { contact: "Priya Mehta", action: "opened", email: "Check In", time: "3 hrs ago" },
  { contact: "Alex Kim", action: "replied", email: "Introduction", time: "4 hrs ago" },
  { contact: "Jordan Lee", action: "opened", email: "Follow Up", time: "5 hrs ago" },
];

export const TIMEFRAMES = ["7d", "14d", "30d", "90d"] as const;

/* ── Contact form fields ── */

export const CONTACT_FORM_FIELDS: { key: keyof Omit<Contact, "id" | "tags">; label: string; placeholder: string; span2?: boolean }[] = [
  { key: "firstName", label: "First Name", placeholder: "John" },
  { key: "lastName", label: "Last Name", placeholder: "Doe" },
  { key: "email", label: "Work Email", placeholder: "john@company.com", span2: true },
  { key: "personalEmail", label: "Personal Email", placeholder: "john@gmail.com", span2: true },
  { key: "company", label: "Company", placeholder: "Acme Corp" },
  { key: "title", label: "Job Title", placeholder: "VP of Sales" },
  { key: "phone", label: "Phone", placeholder: "(555) 123-4567" },
  { key: "mobilePhone", label: "Mobile Phone", placeholder: "(555) 987-6543" },
  { key: "workPhone", label: "Work Phone", placeholder: "(555) 111-2222" },
  { key: "linkedIn", label: "LinkedIn URL", placeholder: "https://linkedin.com/in/..." },
  { key: "city", label: "City", placeholder: "Nashville" },
  { key: "state", label: "State", placeholder: "Tennessee" },
  { key: "industry", label: "Industry", placeholder: "Technology" },
];
