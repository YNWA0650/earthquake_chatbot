import ReactMarkdown from 'react-markdown';
import type { Message } from '../types';

interface MessageBubbleProps {
  message: Message;
}

function WaveformIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="2,12 5,9 8,13 11,6 14,10 17,8 22,12" />
    </svg>
  );
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isHuman = message.role === 'human';
  const enriched = message.enriched;
  const time = message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  if (isHuman) {
    return (
      <div className="message-row message-row--human">
        <div className="message-bubble message-bubble--human">
          <p className="message-content">{message.content}</p>
          <span className="message-time">{time}</span>
        </div>
      </div>
    );
  }

  if (enriched) {
    return (
      <div className="message-row message-row--assistant">
        <div className="ai-avatar">
          <WaveformIcon />
        </div>
        <div className="message-bubble message-bubble--assistant message-bubble--enriched">
          <div className="ai-sender-name">Earthquake Agent</div>

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

          <div className={`eval-badge eval-badge--${enriched.eval_passed ? 'pass' : 'fail'}`}>
            {enriched.eval_passed ? (
              <>
                <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <polyline points="2,6 5,9 10,3" />
                </svg>
                <span>Quality score: {enriched.eval_score}/100</span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M6 2v4M6 9v.5" />
                </svg>
                <span>Quality score: {enriched.eval_score}/100</span>
                {enriched.eval_failure_category && (
                  <span className="eval-badge-category">
                    {enriched.eval_failure_category === 'misaligned_intent' ? 'Misaligned Intent' : 'Ungrounded Output'}
                  </span>
                )}
              </>
            )}
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

          <span className="message-time">{time}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="message-row message-row--assistant">
      <div className="ai-avatar">
        <WaveformIcon />
      </div>
      <div className="message-bubble message-bubble--assistant">
        <div className="ai-sender-name">Earthquake Agent</div>
        <p className="message-content">{message.content}</p>
        <span className="message-time">{time}</span>
      </div>
    </div>
  );
}
