import ReactMarkdown from 'react-markdown';
import type { Message } from '../types';

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isHuman = message.role === 'human';
  const enriched = message.enriched;

  if (!isHuman && enriched) {
    return (
      <div className="message-row message-row--assistant">
        <div className="message-bubble message-bubble--assistant message-bubble--enriched">
          <span className="message-label">Earthquake Agent</span>

          <h3 className="enriched-title">{enriched.title}</h3>

          <div className="enriched-answer">
            <ReactMarkdown
              components={{
                a: ({ href, children }) => (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {enriched.answer_text}
            </ReactMarkdown>
          </div>

          <details className="explainability">
            <summary className="explainability-toggle">
              <span className="explainability-toggle-icon" aria-hidden />
              How this was derived
            </summary>
            <div className="explainability-body">

              {enriched.assumptions.length > 0 && (
                <div className="explainability-section">
                  <h4 className="explainability-heading">Assumptions applied</h4>
                  <ul className="explainability-list">
                    {enriched.assumptions.map((assumption, i) => (
                      <li key={i}>{assumption}</li>
                    ))}
                  </ul>
                </div>
              )}

              {enriched.api_calls.map((call, i) => (
                <div key={i} className="explainability-section">
                  <h4 className="explainability-heading">
                    {enriched.api_calls.length > 1 ? `API call ${i + 1}` : 'API call'}
                  </h4>
                  <div className="api-call-meta">
                    <div className="api-call-row">
                      <span className="api-call-label">Result type</span>
                      <span className={`api-call-badge api-call-badge--${call.result_type}`}>
                        {call.result_type}
                      </span>
                    </div>
                    {call.returned != null && (
                      <div className="api-call-row">
                        <span className="api-call-label">Returned</span>
                        <span className="api-call-value">
                          {call.returned}
                          {call.total_available != null
                            ? ` of ${call.total_available.toLocaleString()} available`
                            : ' events'}
                        </span>
                      </div>
                    )}
                    {call.count != null && (
                      <div className="api-call-row">
                        <span className="api-call-label">Count</span>
                        <span className="api-call-value">{call.count.toLocaleString()}</span>
                      </div>
                    )}
                    <div className="api-call-row">
                      <span className="api-call-label">Retrieved</span>
                      <span className="api-call-value">{call.retrieved_at_utc}</span>
                    </div>
                    <div className="api-call-row api-call-row--url">
                      <span className="api-call-label">URL</span>
                      <a
                        href={call.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="api-call-url"
                        title={call.url}
                      >
                        {call.url}
                      </a>
                    </div>
                  </div>
                </div>
              ))}

              <div className="explainability-footer">
                Request ID: <code className="request-id">{enriched.request_id}</code>
              </div>
            </div>
          </details>

          <span className="message-time">
            {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className={`message-row message-row--${message.role}`}>
      <div className={`message-bubble message-bubble--${message.role}`}>
        {!isHuman && (
          <span className="message-label">Earthquake Agent</span>
        )}
        <p className="message-content">{message.content}</p>
        <span className="message-time">
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  );
}
