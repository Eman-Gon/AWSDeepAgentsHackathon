# Frontend Development — Commons Investigation Platform

You are working on the **Commons** frontend: an investigative intelligence dashboard built with Next.js + TypeScript + React. The frontend lives in `homepage/`.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 16 + TypeScript (strict) + React 19 |
| Graph Viz | vis-network + vis-data (force-directed entity graph) |
| Styling | Tailwind CSS 4 |
| Real-time | SSE / WebSocket for streaming agent output |
| Auth | Auth0 (mock first, wire last) |
| Build | Next.js App Router, static export for GitHub Pages |
| Deploy | GitHub Pages via `static.yml` workflow |

## Project Layout

```
homepage/
├── src/
│   ├── app/
│   │   ├── layout.tsx         # Root layout (Geist fonts, metadata)
│   │   ├── page.tsx           # Main page — wires all 3 panels together
│   │   └── globals.css        # Tailwind imports, dark theme, animations
│   ├── components/
│   │   ├── SearchBar.tsx      # Investigation query input + suggestions
│   │   ├── GraphVisualization.tsx  # vis.js force-directed entity graph
│   │   └── AgentNarrative.tsx # Streaming tool calls + pattern alerts
│   └── lib/
│       ├── mock-data.ts       # Demo investigation steps, nodes, edges
│       └── types.ts           # Shared types (InvestigationStatus)
├── next.config.ts
├── tsconfig.json
├── tailwind.config.ts
└── package.json
```

## Component Architecture

### Three-Panel Layout

The UI has three zones. **The graph visualization IS the demo — prioritize it above all else.**

1. **SearchBar** (top) — Input field + entity suggestions. Calls `onInvestigate(query)`.
2. **GraphVisualization** (left, main area) — vis.js Network graph, dynamically loaded (`next/dynamic`, SSR disabled). Nodes animate in as agent discovers entities.
3. **AgentNarrative** (right, 420px sidebar) — Streaming tool call log with severity-colored pattern alerts.

### Graph Node Types & Colors

| Entity Type | Color | Size |
|-------------|-------|------|
| Person | `#3B82F6` (blue) | 25 |
| Company | `#22C55E` (green) | 25 |
| Contract | `#EAB308` (gold) | 18 |
| Campaign | `#EF4444` (red) | 18 |
| Address | `#6B7280` (gray) | 18 |

### Pattern Alert Severities

| Severity | Border/BG Color | Use |
|----------|----------------|-----|
| CRITICAL | Red (`red-500`) | Direct corruption evidence |
| HIGH | Orange (`orange-500`) | Strong correlation |
| MEDIUM | Yellow (`yellow-500`) | Circumstantial indicator |

## Key Types

```typescript
// Entity graph node (extends vis-network Node)
interface GraphNode {
  id: string;           // e.g. "person:john_doe" or "company:acme"
  label: string;
  group: "person" | "company" | "contract" | "campaign" | "address";
}

// Entity graph edge (extends vis-network Edge)
interface GraphEdge {
  from: string;
  to: string;
  label: string;        // e.g. "DONATED_TO", "OFFICER_OF", "AWARDED"
}

// Corruption pattern alert
interface PatternAlert {
  type: string;         // e.g. "CONTRACTOR_DONATED_TO_AWARDING_OFFICIAL"
  severity: "CRITICAL" | "HIGH" | "MEDIUM";
  detail: string;
  confidence: number;   // 0.0–1.0
}

// One step in the agent's investigation
interface AgentStep {
  tool: string;         // Tool name shown in narrative
  message: string;      // Human-readable description
  nodes?: GraphNode[];  // New nodes to add to graph
  edges?: GraphEdge[];  // New edges to add to graph
  patterns?: PatternAlert[];  // Detected patterns
  delay: number;        // ms to wait before showing this step
}

type InvestigationStatus = "idle" | "running" | "complete";
```

## How the Investigation Flow Works

1. User types entity name in SearchBar, clicks Investigate
2. `page.tsx` sets status to `"running"`, iterates through `AgentStep[]`
3. Each step is delayed, then pushed to state — triggering:
   - New nodes/edges animate onto the graph (GraphVisualization)
   - Tool call + message appears in narrative panel (AgentNarrative)
   - Pattern alerts render with severity badges
4. When all steps complete, status becomes `"complete"`

Currently uses `DEMO_INVESTIGATION` mock data in `lib/mock-data.ts`. To wire to the real backend, replace with SSE/WebSocket that yields `AgentStep` objects.

## Wiring to Real Backend (TODO)

Replace the mock loop in `page.tsx` with:

```typescript
const eventSource = new EventSource(`/api/investigate?q=${encodeURIComponent(query)}`);
eventSource.onmessage = (event) => {
  const step: AgentStep = JSON.parse(event.data);
  setSteps((prev) => [...prev, step]);
  if (step.nodes) setNodes((prev) => [...prev, ...step.nodes!]);
  if (step.edges) setEdges((prev) => [...prev, ...step.edges!]);
};
eventSource.addEventListener("done", () => {
  eventSource.close();
  setStatus("complete");
});
```

The backend agent (Person 3's agent) should emit SSE events matching the `AgentStep` interface.

## GraphVisualization Details

- Uses `next/dynamic` with `ssr: false` (vis.js needs DOM)
- `vis-data` DataSets are kept in refs — new nodes/edges are `.add()`-ed incrementally
- Network auto-fits with animation on new data
- Physics: Barnes-Hut with `gravitationalConstant: -3000`, `springLength: 150`
- Legend overlay shows color-coded entity types

## Styling Conventions

- Dark theme only (`bg-zinc-950`, `text-zinc-100`)
- Use Tailwind utility classes, no custom CSS files per component
- Animations via `animate-fade-in` keyframe (defined in `globals.css`)
- vis.js tooltip override in `globals.css` for dark theme

## Dev Commands

```bash
# from homepage/
npm run dev          # dev server at localhost:3000
npm run build        # production build
npm run lint         # ESLint
```

## Security Rules

- Auth0 routes: build with mock "Sign In" button first, wire Auth0 last
- Never expose API keys in client code
- Sanitize any user input before displaying

## What to do now

$ARGUMENTS
