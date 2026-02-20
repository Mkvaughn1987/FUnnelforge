# FlowDrop

**AI-powered email sequencer for sales teams.**

FlowDrop helps you build, schedule, and manage multi-step email campaigns with a clean, modern interface. Create campaigns manually, load from built-in templates, or let AI generate a complete sequence for you.

![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-38bdf8?logo=tailwindcss)
![React](https://img.shields.io/badge/React-19-61dafb?logo=react)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6?logo=typescript)

---

## Features

- **Campaign Builder** — Create campaigns from scratch or use built-in templates (Cold Outreach, Sales Funnel, Welcome Series, Re-engagement)
- **Rich Email Editor** — Compose emails with a full formatting toolbar, merge variables (`{FirstName}`, `{Company}`, etc.), and email signatures
- **AI Campaign Generator** — Describe your goals in natural language and let AI build a complete email sequence
- **Contact Management** — Add contacts manually or bulk-import from CSV/TSV (supports ZoomInfo, HubSpot, Salesforce column formats)
- **Send Scheduling** — Configure sequence timing with preset cadences, per-email delay/time controls, sending day rules, and daily limits
- **Analytics Dashboard** — Track opens, replies, bounces, and funnel performance across all campaigns

## Getting Started

### Prerequisites

- **Node.js** 18+ and **npm**

### Install & Run

```bash
git clone <your-repo-url>
cd funnel-forge
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Environment Variables

Copy the example env file and add your keys:

```bash
cp .env.example .env.local
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | No | Enables the AI campaign builder chat. Get a key at [platform.openai.com](https://platform.openai.com/api-keys). |

The app works fully without an API key — AI chat will show a helpful message instead of erroring.

## Project Structure

```
app/
  page.tsx                        # Dashboard
  create-campaign/
    page.tsx                      # Campaign creation hub (manual / saved / AI)
    email-editor/page.tsx         # Rich email editor with templates
  contacts/page.tsx               # Contact management + CSV import
  send-schedule/page.tsx          # Schedule configuration
  analytics/page.tsx              # Campaign analytics
  api/chat/route.ts               # OpenAI-powered AI chat endpoint
components/
  ui.tsx                          # Shared UI primitives (Button, Input, Card, Modal, Badge)
  PageHeader.tsx                  # Page header with gradient
  Sidebar.tsx                     # Navigation sidebar
  AIChatPanel.tsx                 # AI chat interface
  campaigns/                      # Campaign sub-components
  email-editor/                   # Email editor sub-components (toolbar, modals)
  contacts/                       # Contact sub-components (table, form modal)
lib/
  types.ts                        # Shared TypeScript interfaces
  sample-data.ts                  # Demo data and constants
```

## Tech Stack

- **Framework:** [Next.js 16](https://nextjs.org/) (App Router, Turbopack)
- **Styling:** [Tailwind CSS 4](https://tailwindcss.com/) with custom theme tokens
- **Language:** TypeScript 5
- **AI:** OpenAI GPT-4o-mini (optional)
- **Fonts:** Geist (UI) + Nunito (logo)

## Deploy

Deploy instantly on [Vercel](https://vercel.com/new):

```bash
npm run build   # Verify production build
```

Or deploy to any platform that supports Node.js.

## License

MIT
