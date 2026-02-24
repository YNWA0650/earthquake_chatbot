import { useState, useCallback, useEffect } from 'react';
import { createThread, sendMessage } from './api';
import { ChatWindow } from './components/ChatWindow';
import { InputBar } from './components/InputBar';
import type { Message } from './types';

export default function App() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initThread = useCallback(async () => {
    try {
      const id = await createThread();
      setThreadId(id);
      setError(null);
    } catch (err) {
      setError('Could not connect to the LangGraph server. Make sure `langgraph dev` is running on port 2024.');
      console.error(err);
    }
  }, []);

  useEffect(() => {
    initThread();
  }, [initThread]);

  const handleNewChat = useCallback(async () => {
    setMessages([]);
    setInputValue('');
    setError(null);
    await initThread();
  }, [initThread]);

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading || !threadId) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'human',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setError(null);

    try {
      const { content, enriched } = await sendMessage(threadId, userMessage.content);

      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content,
        timestamp: new Date(),
        enriched: enriched ?? undefined,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'An unexpected error occurred.';
      setError(msg);
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, isLoading, threadId]);

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-logo">
            <WaveformIcon />
          </div>
          <h1 className="app-title">Earthquake Agent</h1>
          {threadId && !error && (
            <span className="app-status app-status--connected">Connected</span>
          )}
          {!threadId && !error && (
            <span className="app-status app-status--connecting">Connecting…</span>
          )}
          {error && (
            <span className="app-status app-status--error">Disconnected</span>
          )}
        </div>
      </header>

      <main className="app-main">
        {error && (
          <div className="error-banner" role="alert">
            <strong>Error:</strong> {error}
          </div>
        )}
        <ChatWindow messages={messages} isLoading={isLoading} />
      </main>

      <footer className="app-footer">
        <InputBar
          value={inputValue}
          onChange={setInputValue}
          onSend={handleSend}
          onNewChat={handleNewChat}
          isLoading={isLoading}
        />
      </footer>
    </div>
  );
}

function WaveformIcon() {
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M4 20 L8 14 L12 18 L16 8 L20 16 L24 12 L28 20" />
    </svg>
  );
}
