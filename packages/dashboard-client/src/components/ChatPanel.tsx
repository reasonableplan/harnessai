import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useOfficeStore } from '@/stores/office-store';

interface ChatPanelProps {
  targetAgent: string | null;
  onClose: () => void;
  onSend: (content: string) => void;
}

export default function ChatPanel({ targetAgent, onClose, onSend }: ChatPanelProps) {
  const chatMessages = useOfficeStore((s) => s.chatMessages);
  const activePlan = useOfficeStore((s) => s.activePlan);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setInput('');
  };

  const planStage = activePlan?.stage as string | undefined;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="fixed bottom-16 right-4 w-96 h-[480px] bg-[#3A2410] border-2 border-[#5C3A1A] flex flex-col z-40 shadow-2xl"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#5C3A1A]">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
          <span className="font-pixel text-[8px] text-amber-300">
            CHAT: {targetAgent?.toUpperCase() ?? 'DIRECTOR'}
          </span>
          {planStage && (
            <span className="font-pixel text-[6px] text-gray-500 bg-[#2D1B0E] px-1.5 py-0.5">
              {planStage.toUpperCase()}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="font-pixel text-[10px] text-gray-500 hover:text-gray-200 px-1"
        >
          X
        </button>
      </div>

      {/* Plan Summary (if active) */}
      {activePlan && planStage && planStage !== 'committed' && (
        <div className="px-3 py-1.5 border-b border-[#5C3A1A]/50 bg-[#2D1B0E]">
          <div className="flex items-center justify-between">
            <span className="font-pixel text-[6px] text-gray-500">PLAN</span>
            <span className="font-pixel text-[6px] text-amber-400">
              {(activePlan as Record<string, unknown>).epic_title as string || 'Draft'}
            </span>
          </div>
          {Array.isArray((activePlan as Record<string, unknown>).tasks) && (
            <span className="font-pixel text-[5px] text-gray-500">
              {((activePlan as Record<string, unknown>).tasks as unknown[]).length} tasks
            </span>
          )}
          {/* Plan action buttons */}
          {(planStage === 'structuring' || planStage === 'confirming') && (
            <div className="flex gap-1.5 mt-1">
              <button
                className="pixel-btn text-[5px] flex-1 !bg-green-800 hover:!bg-green-700"
                onClick={() => {
                  const action = planStage === 'confirming' ? 'plan.commit' : 'plan.approve';
                  window.dispatchEvent(new CustomEvent('ws-send', { detail: { type: action } }));
                }}
              >
                {planStage === 'confirming' ? 'COMMIT' : 'APPROVE'}
              </button>
              <button
                className="pixel-btn text-[5px] flex-1 !bg-yellow-800 hover:!bg-yellow-700"
                onClick={() => {
                  window.dispatchEvent(new CustomEvent('ws-send', {
                    detail: { type: 'plan.revise', content: '' },
                  }));
                }}
              >
                REVISE
              </button>
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {chatMessages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <span className="font-pixel text-[6px] text-gray-600">
              Start a conversation...
            </span>
          </div>
        )}
        {chatMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] px-2.5 py-1.5 ${
                msg.role === 'user'
                  ? 'bg-blue-900/60 border border-blue-700/50'
                  : 'bg-[#2D1B0E] border border-[#5C3A1A]'
              }`}
            >
              <span className="font-pixel text-[6px] text-gray-200 whitespace-pre-wrap break-words">
                {msg.content}
              </span>
              <div className="mt-0.5">
                <span className="font-pixel text-[4px] text-gray-600">
                  {new Date(msg.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="px-3 py-2 border-t border-[#5C3A1A]">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message..."
            className="flex-1 bg-[#2D1B0E] border border-[#5C3A1A] text-gray-200 font-pixel text-[7px] px-2 py-1.5 focus:outline-none focus:border-amber-500"
          />
          <button
            type="submit"
            disabled={!input.trim()}
            className="pixel-btn text-[6px] px-3 !bg-blue-800 hover:!bg-blue-700 disabled:opacity-50"
          >
            SEND
          </button>
        </div>
      </form>
    </motion.div>
  );
}
