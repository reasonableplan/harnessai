import { useOfficeStore } from '@/stores/office-store';

const TYPE_STYLES: Record<string, { color: string; icon: string }> = {
  'agent.status': { color: 'text-amber-400', icon: '[A]' },
  'board.move': { color: 'text-yellow-400', icon: '[B]' },
  'review.request': { color: 'text-purple-400', icon: '[R]' },
  'epic.progress': { color: 'text-green-400', icon: '[E]' },
  'task.update': { color: 'text-blue-400', icon: '[T]' },
  error: { color: 'text-red-400', icon: '[!]' },
  info: { color: 'text-gray-400', icon: '[i]' },
  success: { color: 'text-green-400', icon: '[+]' },
  message: { color: 'text-gray-300', icon: '[>]' },
};

function getStyle(type: string) {
  return TYPE_STYLES[type] ?? TYPE_STYLES.info;
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '--:--:--';
  }
}

function truncateContent(content: string, max: number = 60): string {
  if (content.length <= max) return content;
  return content.slice(0, max - 2) + '..';
}

export default function ActivityLog() {
  const messages = useOfficeStore((s) => s.messages);

  return (
    <div className="flex flex-col h-full bg-[#3A2410] border-l-2 border-[#5C3A1A]">
      {/* Header */}
      <div className="px-3 py-2 border-b border-[#5C3A1A]">
        <span className="font-pixel text-[8px] text-amber-300 pixel-text-shadow">ACTIVITY LOG</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
        {messages.length === 0 && (
          <div className="text-gray-600 font-pixel text-[6px] py-4 text-center">
            No activity yet...
          </div>
        )}
        {messages.map((msg) => {
          const style = getStyle(msg.type);
          return (
            <div key={msg.id} className="flex items-start gap-1 py-0.5 border-b border-[#3A2410]/50">
              <span className="text-gray-600 font-pixel text-[5px] whitespace-nowrap pt-0.5">
                {formatTimestamp(msg.timestamp)}
              </span>
              <span className={`${style.color} font-pixel text-[6px] whitespace-nowrap`}>
                {style.icon}
              </span>
              <span className="text-gray-500 font-pixel text-[5px] whitespace-nowrap">
                {msg.from}:
              </span>
              <span className="text-gray-300 font-pixel text-[5px] break-all leading-relaxed">
                {truncateContent(
                  typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
