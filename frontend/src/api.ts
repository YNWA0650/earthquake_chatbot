import { Client } from '@langchain/langgraph-sdk';
import type { AgentEnrichedResponse } from './types';

const GRAPH_ID = 'earthquake_agent';
const API_URL = import.meta.env.VITE_LANGGRAPH_URL ?? 'http://localhost:2024';

const client = new Client({ apiUrl: API_URL });

export async function createThread(): Promise<string> {
  const thread = await client.threads.create();
  return thread.thread_id;
}

export interface SendMessageResult {
  content: string;
  enriched: AgentEnrichedResponse | null;
}

export async function sendMessage(
  threadId: string,
  userMessage: string,
): Promise<SendMessageResult> {
  const stream = client.runs.stream(threadId, GRAPH_ID, {
    input: { messages: [{ role: 'human', content: userMessage }] },
    streamMode: 'values',
  });

  // Collect the final state snapshot — values stream emits full state after each node,
  // so the last event is always the most complete.
  let finalState: Record<string, unknown> | null = null;

  for await (const event of stream) {
    if (event.event === 'values') {
      finalState = event.data as Record<string, unknown> | null;
    }
  }

  if (!finalState) {
    return { content: 'The agent returned no response.', enriched: null };
  }

  // The normaliser sets action="build_execute_query" — this is the only path
  // where the full pipeline (normaliser → executor → summariser) ran and
  // enriched_response was freshly populated for THIS turn.
  const action = finalState['action'] as string | undefined;
  const enrichedRaw = finalState['enriched_response'];

  if (action === 'build_execute_query' && enrichedRaw) {
    const enriched = enrichedRaw as AgentEnrichedResponse;
    return {
      content: enriched.answer_text,
      enriched,
    };
  }

  // Supervisor-only path (show_glossary, answer_question): read the last AI message.
  // enriched_response may carry a stale value from a prior turn — do not use it here.
  const messages = (finalState['messages'] ?? []) as Array<{
    type?: string;
    role?: string;
    content?: string;
  }>;

  let content = '';
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (
      (msg.type === 'ai' || msg.role === 'assistant') &&
      typeof msg.content === 'string' &&
      msg.content.trim().length > 0
    ) {
      content = msg.content;
      break;
    }
  }

  return { content: content.trim() || 'The agent returned no response.', enriched: null };
}
