import { useEffect, useRef } from 'react';
import type { Message } from '../types';
import { MessageBubble } from './MessageBubble';

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
  onSuggestion?: (text: string) => void;
}

const SUGGESTIONS = [
  'What major earthquakes happened near Tokyo in the last year?',
  'How many M6+ earthquakes occurred globally this month?',
  'What was the strongest earthquake in California in 2024?',
  'Show recent seismic activity near Turkey',
];

export function ChatWindow({ messages, isLoading, onSuggestion }: ChatWindowProps) {
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
            Ask me about seismic activity anywhere in the world.
          </p>
          {onSuggestion && (
            <div className="suggestion-chips">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className="suggestion-chip"
                  onClick={() => onSuggestion(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="chat-messages">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {isLoading && (
            <div className="message-row message-row--assistant">
              <div className="ai-avatar">
                <WaveformIcon />
              </div>
              <div className="message-bubble message-bubble--assistant message-bubble--loading">
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
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="2,12 5,9 8,13 11,6 14,10 17,8 22,12" />
    </svg>
  );
}

function WaveformIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="2,12 5,9 8,13 11,6 14,10 17,8 22,12" />
    </svg>
  );
}
