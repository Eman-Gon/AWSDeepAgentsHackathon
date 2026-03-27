import { NODE_COLORS, NODE_SIZES } from '@/config/constants';
import type { AgentStep, GraphNode } from '@/types';

function makeNode(id: string, label: string, group: GraphNode['group']): GraphNode {
  return {
    id,
    label,
    group,
    color: NODE_COLORS[group],
    font: { color: '#fff', size: 14, face: 'Inter, system-ui, sans-serif' },
    shape: 'dot',
    size: NODE_SIZES[group] ?? 18,
  };
}

export const DEMO_INVESTIGATION: AgentStep[] = [
  {
    tool: 'search_entity',
    message: 'Searching knowledge graph for "Recology SF"...',
    nodes: [makeNode('company:recology', 'Recology SF', 'company')],
    edges: [],
    delay: 1200,
  },
  {
    tool: 'airbyte_enrichment',
    message: 'Airbyte evidence layer checked connected external systems for fresh context on Recology SF.',
    sources: [
      {
        system: 'Airbyte GitHub',
        label: 'Issue references mentioning Recology',
        detail: 'External connector step',
      },
    ],
    delay: 900,
  },
  {
    tool: 'search_entity',
    message: 'Found: Recology SF — 12 city contracts totaling $3.8B since 2010. Primary department: SF Environment.',
    delay: 1800,
  },
  {
    tool: 'traverse_connections',
    message: 'Traversing connections (hop 1): officers, contracts, addresses...',
    nodes: [
      makeNode('person:paul_giusti', 'Paul Giusti', 'person'),
      makeNode('person:mike_sangiacomo', 'Mike Sangiacomo', 'person'),
      makeNode('contract:recology_main', '$3.2B Waste Mgmt', 'contract'),
      makeNode('contract:recology_2', '$412M Recycling', 'contract'),
      makeNode('address:pier96', 'Pier 96, SF', 'address'),
    ],
    edges: [
      { from: 'person:paul_giusti', to: 'company:recology', label: 'OFFICER_OF' },
      { from: 'person:mike_sangiacomo', to: 'company:recology', label: 'CEO' },
      { from: 'company:recology', to: 'contract:recology_main', label: 'AWARDED' },
      { from: 'company:recology', to: 'contract:recology_2', label: 'AWARDED' },
      { from: 'company:recology', to: 'address:pier96', label: 'REGISTERED_AT' },
    ],
    delay: 2000,
  },
  {
    tool: 'traverse_connections',
    message: 'Traversing connections (hop 2): campaign donations, related entities...',
    nodes: [
      makeNode('campaign:breed_2018', 'London Breed 2018', 'campaign'),
      makeNode('campaign:peskin_2016', 'Aaron Peskin 2016', 'campaign'),
      makeNode('person:mohammed_nuru', 'Mohammed Nuru', 'person'),
      makeNode('company:cleanscapes', 'CleanScapes Inc', 'company'),
    ],
    edges: [
      { from: 'person:paul_giusti', to: 'campaign:breed_2018', label: 'DONATED $10,000' },
      { from: 'person:paul_giusti', to: 'campaign:peskin_2016', label: 'DONATED $4,800' },
      { from: 'person:paul_giusti', to: 'person:mohammed_nuru', label: 'GIFTED' },
      { from: 'person:mohammed_nuru', to: 'contract:recology_main', label: 'APPROVED_BY' },
      { from: 'company:cleanscapes', to: 'address:pier96', label: 'REGISTERED_AT' },
    ],
    delay: 2200,
  },
  {
    tool: 'detect_patterns',
    message: 'Running corruption pattern detection on entity cluster...',
    delay: 1500,
  },
  {
    tool: 'detect_patterns',
    message: 'Pattern analysis complete.',
    patterns: [
      {
        type: 'CONTRACTOR_GIFTED_APPROVING_OFFICIAL',
        severity: 'CRITICAL',
        detail: 'Paul Giusti (Recology VP) provided gifts to Mohammed Nuru (DPW Director) who approved Recology\'s $3.2B waste management contract. Nuru was later charged with public corruption by the FBI.',
        confidence: 0.95,
      },
      {
        type: 'CONTRACTOR_DONATED_TO_OVERSIGHT_OFFICIAL',
        severity: 'HIGH',
        detail: 'Recology officers donated $14,800 to campaigns of supervisors on the Budget & Finance Committee, which oversees waste management rate-setting.',
        confidence: 0.88,
      },
      {
        type: 'SHARED_ADDRESS_MULTIPLE_CONTRACTORS',
        severity: 'MEDIUM',
        detail: 'CleanScapes Inc shares a registered address with Recology SF at Pier 96. CleanScapes was acquired by Recology in 2015 — potential bid-rigging on "competitive" contracts.',
        confidence: 0.72,
      },
    ],
    delay: 2000,
  },
  {
    tool: 'check_prior_investigations',
    message: 'Cross-referencing prior investigations... Investigation #14 (2 months ago) flagged Mohammed Nuru\'s connections to multiple city contractors. Investigation #23 flagged the Pier 96 address cluster.',
    delay: 1800,
  },
  {
    tool: 'get_pattern_confidence',
    message: 'Querying Overmind for historical confidence... Pattern "CONTRACTOR_GIFTED_APPROVING_OFFICIAL + DONATED_TO_OVERSIGHT" has led to confirmed corruption findings in 82% of prior investigations.',
    delay: 1500,
  },
  {
    tool: 'file_investigation',
    message: 'Investigation complete. Summary: Recology SF shows a CRITICAL pattern of corruption indicators — direct gifts to the approving official (Mohammed Nuru, now federally indicted), campaign donations to oversight committee members, and a shared address with an acquired competitor suggesting market consolidation. Recommended: escalate for editorial review.',
    delay: 0,
  },
];
