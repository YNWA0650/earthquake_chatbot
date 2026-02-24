import { useEffect, useRef } from 'react';
import type { Message } from '../types';
import { MessageBubble } from './MessageBubble';

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
}

export function ChatWindow({ messages, isLoading }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const isEmpty = messages.length === 0 && !isLoading;

  return (
    <div className="chat-window">
      {isEmpty ? (
        <div className="chat-empty">
          <div className="chat-empty-icon">
            <EarthquakeIcon />
          </div>
          <h2 className="chat-empty-title">Earthquake Query Agent</h2>
          <p className="chat-empty-subtitle">
            Ask me about earthquakes anywhere in the world. Try:<br />
            <em>"What major earthquakes happened near Tokyo in the last year?"</em>
          </p>
        </div>
      ) : (
        <div className="chat-messages">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {isLoading && (
            <div className="message-row message-row--assistant">
              <div className="message-bubble message-bubble--assistant message-bubble--loading">
                <span className="message-label">Earthquake Agent</span>
                <div className="loading-dots">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

function EarthquakeIcon() {
  return (
    <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 40 L16 28 L24 36 L32 16 L40 32 L48 24 L56 40" />
      <line x1="2" y1="40" x2="62" y2="40" />
    </svg>
  );
}
