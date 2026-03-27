export type InvestigationStatus = 'idle' | 'running' | 'complete';

export interface GraphNode {
  id: string;
  label: string;
  group: 'person' | 'company' | 'contract' | 'campaign' | 'address';
  color?: { background: string; border: string };
  font?: { color: string; size: number; face: string };
  shape?: string;
  size?: number;
  level?: number;
  mass?: number;
}

export interface GraphEdge {
  id?: string;
  from: string;
  to: string;
  label: string;
}

export interface PatternAlert {
  type: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM';
  detail: string;
  confidence: number;
}

export interface AgentStep {
  tool: string;
  message: string;
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  patterns?: PatternAlert[];
  delay: number;
}
