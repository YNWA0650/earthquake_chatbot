export interface APICallLog {
  url: string;
  retrieved_at_utc: string;
  result_type: string;
  total_available: number | null;
  returned: number | null;
  count: number | null;
}

export interface AgentEnrichedResponse {
  request_id: string;
  title: string;
  parsed_intent: string;
  assumptions: string[];
  api_calls: APICallLog[];
  answer_text: string;
  eval_score: number;
  eval_passed: boolean;
  eval_failure_category: 'misaligned_intent' | 'ungrounded_output' | null;
}

export interface Message {
  id: string;
  role: 'human' | 'assistant';
  content: string;
  timestamp: Date;
  enriched?: AgentEnrichedResponse;
}
