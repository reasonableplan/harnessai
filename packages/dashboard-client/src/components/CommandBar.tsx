import { useState, useRef, useCallback, useEffect } from 'react';

interface CommandBarProps {
  onSend: (command: string) => void;
}

const SLASH_COMMANDS = [
  '/plan',
  '/status',
  '/pause',
  '/resume',
  '/retry',
  '/assign',
  '/cancel',
  '/help',
];

const AGENT_MENTIONS = ['@director', '@git', '@frontend', '@backend', '@docs'];

export default function CommandBar({ onSend }: CommandBarProps) {
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [selectedSuggestion, setSelectedSuggestion] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const updateSuggestions = useCallback((value: string) => {
    if (!value) {
      setSuggestions([]);
      return;
    }

    const words = value.split(/\s+/);
    const lastWord = words[words.length - 1];

    if (lastWord.startsWith('/')) {
      const matches = SLASH_COMMANDS.filter((c) => c.startsWith(lastWord.toLowerCase()));
      setSuggestions(matches);
      setSelectedSuggestion(0);
    } else if (lastWord.startsWith('@')) {
      const matches = AGENT_MENTIONS.filter((m) => m.startsWith(lastWord.toLowerCase()));
      setSuggestions(matches);
      setSelectedSuggestion(0);
    } else {
      setSuggestions([]);
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInput(val);
    setHistoryIdx(-1);
    updateSuggestions(val);
  };

  const applySuggestion = (suggestion: string) => {
    const words = input.split(/\s+/);
    words[words.length - 1] = suggestion;
    const newVal = words.join(' ') + ' ';
    setInput(newVal);
    setSuggestions([]);
    inputRef.current?.focus();
  };

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed) return;

    onSend(trimmed);
    setHistory((prev) => [trimmed, ...prev].slice(0, 50));
    setInput('');
    setSuggestions([]);
    setHistoryIdx(-1);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (suggestions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedSuggestion((prev) => (prev < suggestions.length - 1 ? prev + 1 : 0));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedSuggestion((prev) => (prev > 0 ? prev - 1 : suggestions.length - 1));
        return;
      }
      if (e.key === 'Tab' || e.key === 'Enter') {
        if (suggestions.length > 0 && e.key === 'Tab') {
          e.preventDefault();
          applySuggestion(suggestions[selectedSuggestion]);
          return;
        }
      }
      if (e.key === 'Escape') {
        setSuggestions([]);
        return;
      }
    }

    if (e.key === 'Enter') {
      handleSubmit();
      return;
    }

    if (e.key === 'ArrowUp' && suggestions.length === 0) {
      e.preventDefault();
      if (history.length === 0) return;
      const newIdx = historyIdx < history.length - 1 ? historyIdx + 1 : historyIdx;
      setHistoryIdx(newIdx);
      setInput(history[newIdx]);
    }

    if (e.key === 'ArrowDown' && suggestions.length === 0) {
      e.preventDefault();
      if (historyIdx <= 0) {
        setHistoryIdx(-1);
        setInput('');
      } else {
        const newIdx = historyIdx - 1;
        setHistoryIdx(newIdx);
        setInput(history[newIdx]);
      }
    }
  };

  useEffect(() => {
    const handleGlobalKey = (e: KeyboardEvent) => {
      // Only intercept '/' when no input/textarea/select is focused
      const tag = (document.activeElement as HTMLElement)?.tagName;
      if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') {
        e.preventDefault();
        inputRef.current?.focus();
        setInput('/');
        updateSuggestions('/');
      }
    };
    window.addEventListener('keydown', handleGlobalKey);
    return () => window.removeEventListener('keydown', handleGlobalKey);
  }, [updateSuggestions]);

  return (
    <div className="relative px-4 py-2 bg-[#3A2410] border-t-2 border-[#5C3A1A]">
      {/* Suggestions dropdown */}
      {suggestions.length > 0 && (
        <div className="absolute bottom-full left-4 mb-1 bg-[#2D1B0E] border-2 border-[#5C3A1A] min-w-[180px] z-50">
          {suggestions.map((s, i) => (
            <div
              key={s}
              className={`px-3 py-1.5 font-pixel text-[8px] cursor-pointer ${
                i === selectedSuggestion
                  ? 'bg-[#5C3A1A] text-amber-300'
                  : 'text-gray-400 hover:bg-[#5C3A1A] hover:text-gray-200'
              }`}
              onMouseDown={(e) => {
                e.preventDefault();
                applySuggestion(s);
              }}
            >
              {s}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        <span className="font-pixel text-[8px] text-amber-400 select-none">&gt;</span>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Type a command... ( / for commands, @ for agents )"
          className="pixel-input flex-1 text-[8px]"
          autoComplete="off"
          spellCheck={false}
        />
        <button
          onClick={handleSubmit}
          disabled={!input.trim()}
          className="pixel-btn text-[7px] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          SEND
        </button>
      </div>
    </div>
  );
}
