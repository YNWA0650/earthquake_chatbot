import { useRef, type KeyboardEvent } from 'react';

interface InputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onNewChat: () => void;
  isLoading: boolean;
}

export function InputBar({ value, onChange, onSend, onNewChat, isLoading }: InputBarProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading && value.trim()) {
        onSend();
      }
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const canSend = !isLoading && value.trim().length > 0;

  return (
    <div className="input-bar">
      <button
        className="btn btn--secondary"
        onClick={onNewChat}
        disabled={isLoading}
        title="Start a new conversation"
        aria-label="New chat"
      >
        <NewChatIcon />
        <span>New chat</span>
      </button>

      <div className="input-field-wrap">
        <textarea
          ref={textareaRef}
          className="input-field"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder="Ask about earthquakes… (Enter to send)"
          disabled={isLoading}
          rows={1}
          aria-label="Message input"
        />
      </div>

      <button
        className="btn btn--primary"
        onClick={onSend}
        disabled={!canSend}
        title="Send message"
        aria-label="Send"
      >
        <SendIcon />
        <span>Send</span>
      </button>
    </div>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
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
