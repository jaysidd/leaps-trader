/**
 * AI Copilot Chat - Interactive chat panel for market assistance
 */
import { useState, useRef, useEffect } from 'react';
import { chatWithCopilot } from '../../api/commandCenter';

const ChatMessage = ({ message, isUser }) => {
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`max-w-[80%] rounded-lg p-3 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-gray-700 text-gray-100'
        }`}
      >
        {!isUser && (
          <div className="flex items-center gap-2 mb-1 text-xs text-gray-400">
            <span>🤖</span>
            <span>AI Copilot</span>
          </div>
        )}
        <div className="text-sm whitespace-pre-wrap">{message.content}</div>
      </div>
    </div>
  );
};

const SuggestedQuestions = ({ onSelect }) => {
  const suggestions = [
    "What should I focus on today?",
    "Explain the current VIX level",
    "Which sectors are showing strength?",
    "Is now a good time for LEAPS?",
  ];

  return (
    <div className="space-y-2">
      <div className="text-xs text-gray-500 mb-2">Suggested questions:</div>
      {suggestions.map((question, idx) => (
        <button
          key={idx}
          onClick={() => onSelect(question)}
          className="block w-full text-left text-sm text-gray-300 bg-gray-700/50 hover:bg-gray-700 rounded-lg p-2 transition-colors"
        >
          {question}
        </button>
      ))}
    </div>
  );
};

export default function CopilotChat({ isOpen, onClose, context, isAvailable }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  const handleSend = async (messageText = input) => {
    if (!messageText.trim() || isLoading) return;

    const userMessage = { role: 'user', content: messageText.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await chatWithCopilot(
        messageText,
        context,
        messages.map((m) => ({ role: m.role, content: m.content }))
      );

      if (response.success && response.response) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: response.response },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: response.error || 'Sorry, I could not process your request.',
          },
        ]);
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, there was an error connecting to the AI service.',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-4 right-4 w-96 h-[500px] bg-gray-800 rounded-lg shadow-2xl border border-gray-700 flex flex-col z-50">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <span className="text-xl">🤖</span>
          <div>
            <h3 className="text-white font-semibold">AI Copilot</h3>
            <p className="text-xs text-gray-400">
              {isAvailable ? 'Powered by Claude' : 'AI not configured'}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-white transition-colors"
        >
          ✕
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div>
            <div className="text-center text-gray-400 mb-4">
              <span className="text-4xl block mb-2">👋</span>
              <p className="text-sm">
                Hi! I'm your trading assistant. Ask me anything about the markets.
              </p>
            </div>
            <SuggestedQuestions onSelect={handleSend} />
          </div>
        ) : (
          <>
            {messages.map((msg, idx) => (
              <ChatMessage key={idx} message={msg} isUser={msg.role === 'user'} />
            ))}
            {isLoading && (
              <div className="flex justify-start mb-3">
                <div className="bg-gray-700 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-gray-400">
                    <span className="animate-pulse">🤖</span>
                    <span className="text-sm">Thinking...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-700">
        {!isAvailable ? (
          <div className="text-center text-gray-500 text-sm py-2">
            Configure ANTHROPIC_API_KEY in Settings to enable AI chat
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask about markets, stocks, or strategies..."
              className="flex-1 bg-gray-700 text-white rounded-lg p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={1}
              disabled={isLoading}
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isLoading}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg p-3 transition-colors"
            >
              ➤
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
