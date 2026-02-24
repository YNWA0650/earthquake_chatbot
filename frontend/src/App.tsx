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

  const handleSuggestion = useCallback((text: string) => {
    setInputValue(text);
  }, []);

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
          <div className="header-left">
            <div className="app-logo">
              <SeismographIcon />
            </div>
            <h1 className="app-title">Earthquake Agent</h1>
          </div>

          <div className="header-center">
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

          <div className="header-right">
            <button
              className="btn btn--secondary btn--sm"
              onClick={handleNewChat}
              disabled={isLoading}
              title="Start a new conversation"
              aria-label="New chat"
            >
              <NewChatIcon />
              <span>New chat</span>
            </button>
          </div>
        </div>
      </header>

      <main className="app-main">
        {error && (
          <div className="error-banner" role="alert">
            <strong>Error:</strong> {error}
          </div>
        )}
        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          onSuggestion={handleSuggestion}
        />
      </main>

      <footer className="app-footer">
        <InputBar
          value={inputValue}
          onChange={setInputValue}
          onSend={handleSend}
          isLoading={isLoading}
        />
      </footer>
    </div>
  );
}

function NewChatIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
    </svg>
  );
}

function SeismographIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="2,12 5,9 8,13 11,6 14,10 17,8 22,12" />
    </svg>
  );
}
