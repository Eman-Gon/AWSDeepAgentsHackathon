# PROJECT PITCH: Commons
## AI-Powered Corruption Detection for Government Contracts

---

## The Problem

**Corruption in government procurement is hidden in spreadsheets.**

Every year, San Francisco awards $5B+ in city contracts. But corruption happens in the gaps:

- A city official receives $10k in campaign donations from a company owner
- That same owner's company suddenly wins $500k in contracts from that official's department  
- Investigation tools? Journalists manually cross-reference three databases over weeks

**The result**: Pay-to-play schemes go undetected. Taxpayer money flows to connected insiders. Citizens have no way to demand accountability.

**Corrupt procurement isn't rare—it's the default burden of transparency.**

---

## The Solution: Commons

An **AI-powered investigative intelligence platform** that autonomously detects corruption in government records in **seconds**.

### How It Works

1. **Ingest**: Pull SF government public data (contracts, donations, business registrations) via SODA API + Airbyte
2. **Graph**: Build a knowledge graph of 186K+ entities and their 245K+ relationships
3. **Investigate**: Gemini Flash agent autonomously traverses the graph, detects pay-to-play patterns
4. **Visualize**: Interactive graph shows entity networks, contract flows, corruption findings
5. **Report**: Journalists + watchdogs publish findings immediately

### Key Differentiators

| Feature | Why It Matters |
|---------|---|
| **Real-time AI agent** | Agent autonomously decides what to investigate, not hardcoded flow |
| **Fuzzy entity matching** | Handles "Recology Inc" vs "Recology, Inc." vs "Recology" automatically |
| **Multi-hop traversal** | Finds hidden connections: person → company → shared address → another company winning contracts |
| **Pattern detection** | Automatically flags corruption red flags (donations + contracts from same network) |
| **Anonymous tips** | Whistleblowers can submit tips securely without accounts |
| **Saved findings** | Journalists can persist investigations and publish for follow-up reporting |

---

## Market Opportunity

### The Market

- **TAM**: $50B+ annual US government contracts ÷ 50 states × 30% corruption estimate = **$7.5B fraud annually**
- **Design partners**: 
  - Investigative journalists (1000+/week in US pursuing government accountability)
  - Government watchdog organizations (1000+ nonprofits in US)
  - Whistleblower networks (Government Accountability Project, etc.)
  - Compliance + anti-corruption teams in large cities
  - Corporate fraud/procurement compliance

### Use Cases

1. **Investigative Journalism** (Reuters, ProPublica, AP, local news)
   - *Before Commons*: 3-6 month investigation to find one pay-to-play scheme
   - *With Commons*: 5 minutes to surface suspect entities + evidence chains
   - **Impact**: 10x more stories, more proactive coverage

2. **Government Watchdogs** (Common Cause, CCGA, Citizens Oversight, etc.)
   - Pre-election audits: Which candidates are funded by contractors getting city work?
   - Real-time alerts: New vendor + donation from city official's family = investigate

3. **Whistleblower Protection**
   - Anonymous tip submission (one-time token, IP-safe)
   - Can be integrated into SecureDrop, GlobeLeaks, existing whistleblower platforms

4. **Procurement Compliance**
   - Larger cities (NYC, LA, Chicago) use Commons to audit their own contracts
   - Internal controls: "Is this vendor connected to any current officials?"

5. **Law Enforcement** (DA, FBI white-collar units)
   - Build leads for corruption investigations
   - Visualize network of involved parties + evidence

---

## Business Model

### Why This Isn't a Nonprofit

Corruption detection is a **high-leverage, defensible business**:

- **SaaS B2G** (cities paying for compliance audit): $10k-50k/month per city
- **SaaS B2M** (media organizations): $5k-20k/month subscription
- **SaaS B2NGO** (watchdog organizations): $2k-10k/month
- **Custom reports** (law enforcement, corporate clients): $50k-500k per project
- **API licensing** (civic tech platforms): Usage-based pricing

**Example revenue at scale** (5-10 years):
- 50 US cities × $20k/month = $12M ARR
- 500 journalists/media orgs × $5k/month = $30M ARR
- 100 NGOs × $5k/month = $6M ARR
- **Total**: $48M ARR at 10% penetration

### Go-to-Market

**Phase 1** (next 6 months): Public beta for SF + 1-2 other cities
- Launch open instance for journalists + watchdogs (free initially)
- Build case studies; measure impact (stories published, corruption detected)
- Seed partnerships with ProPublica, Reuters, local news outlets

**Phase 2** (6-12 months): City procurement teams
- Pitch to SF, LA, NYC procurement + audit teams
- Annual contracts: $20-50k/city for ongoing compliance

**Phase 3** (12+ months): Expand to state + federal procurement
- Scale to all 50 states + federal GSA contracts
- Add private sector: corporate procurement, supply chain compliance

---

## Product Roadmap

### MVP (Shipped ✅)
- ✅ Knowledge graph from SODA API (186K+ entities, 245K+ edges)
- ✅ Gemini Flash agent with function calling for autonomous investigation
- ✅ Interactive frontend: entity graph, globe, narrative findings
- ✅ Anonymous tip submission
- ✅ Investigation persistence + publication
- ✅ Deployed on Render (free tier)

### Phase 1 (Next 2-4 weeks)
- RBAC + journalist workflow (multiple investigators, peer review before publication)
- Saved findings feed (public dashboard of published corruption findings)
- Email alerts (watch an entity, get pinged when new contracts/donations appear)
- Expand to 5+ CA cities (Oakland, LA, San Diego, Berkeley, etc.)

### Phase 2 (2-3 months)
- Aerospike migration (10M+ entity scale, real-time graph updates)
- Full-text search (ElasticSearch integration)
- Overmind integration (auto-evaluation of finding quality, agent prompt optimization)
- Whistleblower platform integration (SecureDrop, GlobeLeaks)

### Phase 3 (3-6 months)
- Federal + state contract data (GSA, SAM.gov, state bid systems)
- Browser extension (investigate any vendor from city contracts portal)
- Real-time SODA sync (no more nightly batch; stream updates live)
- Mobile app (React Native for field investigators)

---

## Technical Moat

Commons has defensible technical advantages:

1. **Entity Linking at Scale**: Our fuzzy matching + deduplication handles 10:1 variations of company names (built with thefuzz, custom heuristics)
2. **AI Agent as Core UX**: Gemini Flash function calling means the agent autonomously decides *what* to investigate—not just execute hardcoded queries
3. **Graph Traversal for Corruption**: Multi-hop BFS + pattern detection finds corruption patterns humans would take months to discover
4. **Real-time SSE Streaming**: Interactive agent investigation with live updates (not batch reports)

Competitors (if they exist) are:
- Legacy procurement forensics tools (1980s UX, $100k+/year, manual workflows)
- Spreadsheet + manual cross-reference (what journalists do today)
- Governance risk platforms (Domo, Tableau dashboards—expensive, slow, not AI-powered)

Commons is the first **real-time, AI-native corruption detection platform** for government contracts.

---

## Team & Execution

### Why We'll Win

- **Regulatory tailwind**: Government transparency laws (FOIA, SODA) make data available
- **AI moment**: Gemini Flash + function calling makes autonomous investigation practical for the first time
- **Clear use case**: Journalists + watchdogs are desperately looking for this tool (we've talked to 5+ ProPublica reporters—they want it)
- **Low CAC**: Marketing is word-of-mouth + ProPublica posts a story using Commons → 10k journalists know it exists
- **High LTV**: Cities renew compliance contracts yearly; media subscriptions are sticky

### Execution Plan (Next 12 Months)

| Timeline | Milestone | Success Metric |
|----------|-----------|---|
| **Week 1-4** | Ship Phase 1 features (RBAC, alerts, expanded cities) | 5+ cities loaded; 100+ beta users |
| **Month 2-3** | Journalism partnerships + ProPublica case study | 1 major news organization uses Commons for investigation |
| **Month 4-6** | City procurement pilots (SF, LA, 1-2 others) | 1-2 city contracts signed ($30k+) |
| **Month 7-12** | Phase 2 + 3 (Aerospike, search, federal data) | 50 cities + 5 major news orgs; $200k ARR |

---

## Funding Ask

**Seed round: $500k-1M to:**
- Fund 2 engineers (core platform + data pipeline) for 12 months
- Hire 1 journalist/product manager (GT + partnerships + journalism GTM)
- Cloud infrastructure (Aerospike, Turso scaling, compute)
- Legal + compliance (data handling, privacy, API terms)
- Initial marketing ($50k ProPublica sponsorship, conference talks)

**Use of Funds**:
```
Salaries (3 people × 12mo):      $300k
Cloud + infrastructure:           $100k
Legal + compliance:                $50k
Marketing + partnerships:          $50k
Buffer/contingency:               $100k
────────────────────────────────
Total:                           $600k
```

**Milestones for Series A** (18 months):
- 100+ cities + counties using Commons for procurement audit
- 10+ major investigative news organizations
- $1M+ ARR
- Federal contract data integrated (GSA, state systems)
- 5M+ entities in knowledge graph

---

## Competitive Landscape

### Who Plays in This Space

| Player | Product | Weakness |
|--------|---------|----------|
| **Procurement forensics companies** (Domo, Tableau, Alteryx) | BI dashboards for contract analysis | Manual queries, no AI, $100k+/year, slow |
| **Watchdog platforms** (SPAN, Sludge, OpenSecrets API) | Basic contract + donation portals | Separate databases, no correlation, no AI |
| **Journalism tools** (Recordset) | Records request automation | Doesn't find corruption—just helps get docs |
| **OCG, ICAC, 1MG** | Government anti-corruption agencies | Only cover specific industries/agencies, slow |
| **NOBODY** | AI-powered corruption detection | **Commons is first to market** |

---

## Why Commons Succeeds

### The Thesis

**AI + Government Transparency = Corruption Detection Becomes Scalable**

For the first time in history:
1. Government contracts are open data (SODA API, 50+ cities)
2. AI agents can autonomously investigate complex data (Gemini Flash function calling)
3. Journalists + watchdogs need this tool (we've validated)
4. Business model exists (cities pay for compliance, media pays for subscription)

Commons is the natural monopoly at the intersection of these three trends.

### Why We're the Team to Do It

- Built the MVP in 2 weeks (AWS Deep Agents Hackathon)
- Already deployed on Render + getting interest from journalists
- Understand the regulatory + government market from prior work
- Clear GTM to early customers (ProPublica, Common Cause, etc.)

---

## The Ask

**Help us build the transparency infrastructure for 21st-century government accountability.**

Corrupt officials hide in spreadsheets. We're building the flashlight.

**Contact**: investigative-intelligence@commons.app  
**Live Demo**: https://commons-ovyq.onrender.com  
**Code**: https://github.com/Eman-Gon/AWSDeepAgentsHackathon  

---

## Appendix: Key Metrics

### Current State (Shipped MVP)
- **Knowledge Graph Scale**: 186K entities, 245K edges, 500MB SQLite
- **Data Sources**: SF contracts (10 years), campaign finance, business registrations
- **Investigation Speed**: <5 seconds for complete multi-hop traversal + pattern detection
- **Frontend**: Real-time SSE streaming, interactive graph, globe visualization
- **Deployment**: Render free tier, auto-scaling on enterprise (not yet)

### Unit Economics (Projection)

**SaaS B2G** (cities):
- ACV: $30k/year (procurement compliance audit)
- CAC: $5k (sales + onboarding)
- LTV: $150k (5-year average customer lifetime)
- LTV:CAC: **30:1** ✅ (excellent)

**SaaS B2M** (media):
- ACV: $10k/year (subscription)
- CAC: $2k (marketing + GTM)
- LTV: $50k (5 years)
- LTV:CAC: **25:1** ✅

### Achievable Milestones

| Year 1 | Year 3 | Year 5 |
|--------|--------|--------|
| 10 cities | 100 cities | 500+ cities |
| 5 media orgs | 50 media orgs | 200+ media orgs |
| $200k ARR | $2M ARR | $10M ARR |
| 2M entities | 20M entities | 100M+ entities |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **Data quality** | Continuous validation pipeline; corrections crowd-sourced from journalists |
| **False positives** | Human review workflow; pattern confidence scores help filter; Overmind evaluation |
| **API rate limits** | SODA throttles ~100 req/min; we batch + cache; upgrade to pro tier if needed |
| **Privacy/legal** | All data is public records; no PII beyond gov records; DPA with cities; legal counsel |
| **AI safety** | Pattern confidence scores; human-in-the-loop for findings; we never accuse, only surface evidence |
| **Regulatory** | FOIA + state transparency laws make procurement data public; we're re-publishing it, not harvesting private data |

