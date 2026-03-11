import { motion } from 'framer-motion';

interface SpeechBubbleProps {
  x: number;
  y: number;
  content: string;
  type: 'task' | 'thinking' | 'info' | 'error';
}

const TYPE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  task: { bg: '#FFFFFF', border: '#333333', text: '#222222' },
  thinking: { bg: '#FFF8DC', border: '#DAA520', text: '#555555' },
  info: { bg: '#E0F0FF', border: '#4A90D9', text: '#333333' },
  error: { bg: '#FFE0E0', border: '#CC3333', text: '#AA0000' },
};

export default function SpeechBubble({ x, y, content, type }: SpeechBubbleProps) {
  const colors = TYPE_COLORS[type] ?? TYPE_COLORS.info;
  const truncated = content.length > 24 ? content.slice(0, 22) + '..' : content;

  const textLen = truncated.length;
  const bubbleW = Math.max(60, textLen * 7 + 16);
  const bubbleH = 24;
  const bx = x - bubbleW / 2;
  const by = y - bubbleH - 8;

  return (
    <motion.g
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.3 }}
    >
      {/* Bubble body */}
      <rect
        x={bx}
        y={by}
        width={bubbleW}
        height={bubbleH}
        rx={4}
        ry={4}
        fill={colors.bg}
        stroke={colors.border}
        strokeWidth={2}
        shapeRendering="crispEdges"
      />
      {/* Pointer triangle */}
      <polygon
        points={`${x - 5},${by + bubbleH} ${x + 5},${by + bubbleH} ${x},${by + bubbleH + 7}`}
        fill={colors.bg}
        stroke={colors.border}
        strokeWidth={2}
        shapeRendering="crispEdges"
      />
      {/* Cover the border between bubble and triangle */}
      <rect
        x={x - 4}
        y={by + bubbleH - 1}
        width={8}
        height={3}
        fill={colors.bg}
        shapeRendering="crispEdges"
      />
      {/* Text */}
      <text
        x={x}
        y={by + bubbleH / 2 + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={colors.text}
        fontSize={8}
        fontFamily="'Press Start 2P', monospace"
      >
        {truncated}
      </text>
    </motion.g>
  );
}
