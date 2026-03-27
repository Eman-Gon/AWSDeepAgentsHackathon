export const NODE_COLORS: Record<string, { background: string; border: string }> = {
  person:   { background: '#3B82F6', border: '#2563EB' },
  company:  { background: '#22C55E', border: '#16A34A' },
  contract: { background: '#EAB308', border: '#CA8A04' },
  campaign: { background: '#EF4444', border: '#DC2626' },
  address:  { background: '#6B7280', border: '#4B5563' },
};

export const NODE_SIZES: Record<string, number> = {
  person: 25,
  company: 25,
  contract: 18,
  campaign: 18,
  address: 18,
};

export const SEVERITY_COLORS: Record<string, { border: string; bg: string; text: string; badge: string }> = {
  CRITICAL: { border: '#ef4444', bg: 'rgba(239,68,68,0.1)', text: '#f87171', badge: 'rgba(239,68,68,0.2)' },
  HIGH:     { border: '#f97316', bg: 'rgba(249,115,22,0.1)', text: '#fb923c', badge: 'rgba(249,115,22,0.2)' },
  MEDIUM:   { border: '#eab308', bg: 'rgba(234,179,8,0.1)',  text: '#facc15', badge: 'rgba(234,179,8,0.2)' },
};

export const TOOL_ICONS: Record<string, string> = {
  search_entity: '🔍',
  traverse_connections: '🔗',
  detect_patterns: '⚠️',
  airbyte_enrichment: '🧩',
  check_prior_investigations: '📁',
  get_pattern_confidence: '📊',
  file_investigation: '📋',
  briefing: '📄',
  final_briefing: '📄',
};

export const SUGGESTIONS = [
  'Recology SF',
  'Mohammed Nuru',
  'Platinum Advisors',
  'Zuckerberg SF General',
  'Salesforce Tower',
];
