export interface EmailTab {
  name: string;
  subject: string;
  body: string;
}

export interface Template {
  name: string;
  emails: EmailTab[];
}

export interface Signature {
  name: string;
  title: string;
  phone: string;
  email: string;
}

export interface Contact {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  personalEmail: string;
  company: string;
  title: string;
  phone: string;
  workPhone: string;
  mobilePhone: string;
  linkedIn: string;
  city: string;
  state: string;
  industry: string;
  tags: string[];
}

export interface ScheduleStep {
  id: string;
  emailName: string;
  delayDays: number;
  sendTime: string;
}

export interface Campaign {
  id: string;
  name: string;
  type: string;
  emails: number;
  status: string;
  updated: string;
}

export interface OverviewStat {
  label: string;
  value: string;
  change: string;
  positive: boolean;
}

export interface SequencePerformance {
  step: string;
  sent: number;
  opened: number;
  replied: number;
  openRate: number;
  replyRate: number;
}

export interface ActivityItem {
  contact: string;
  action: string;
  email: string;
  time: string;
}
