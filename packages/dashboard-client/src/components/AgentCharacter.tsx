import { motion } from 'framer-motion';
import type { AgentState } from '@/stores/office-store';
import SpeechBubble from './SpeechBubble';

interface AgentCharacterProps {
  agent: AgentState;
  x: number;
  y: number;
  onClick: () => void;
  isSelected: boolean;
}

const DOMAIN_COLORS: Record<string, { body: string; accent: string; hair: string }> = {
  director: { body: '#2C2C54', accent: '#FFD700', hair: '#4A3728' },
  git: { body: '#F05032', accent: '#FF7854', hair: '#222222' },
  frontend: { body: '#20232A', accent: '#61DAFB', hair: '#8B4513' },
  backend: { body: '#3C873A', accent: '#68A063', hair: '#333333' },
  docs: { body: '#F7DF1E', accent: '#C9B100', hair: '#654321' },
};

const DOMAIN_LABELS: Record<string, string> = {
  director: 'DIR',
  git: 'GIT',
  frontend: 'FE',
  backend: 'BE',
  docs: 'DOC',
};

// Agent desk positions for each domain
export const DESK_POSITIONS: Record<string, { x: number; y: number }> = {
  director: { x: 540, y: 260 },
  git: { x: 180, y: 360 },
  frontend: { x: 420, y: 420 },
  backend: { x: 740, y: 360 },
  docs: { x: 900, y: 420 },
};

const SOFA_POSITIONS: Record<string, { x: number; y: number }> = {
  director: { x: 960, y: 570 },
  git: { x: 920, y: 580 },
  frontend: { x: 1000, y: 570 },
  backend: { x: 1040, y: 580 },
  docs: { x: 1080, y: 570 },
};

const BOOKSHELF_POS = { x: 1050, y: 300 };

export function getAgentPosition(
  agent: AgentState,
): { x: number; y: number } {
  const desk = DESK_POSITIONS[agent.domain] ?? { x: 400, y: 400 };
  switch (agent.status) {
    case 'working':
    case 'thinking':
    case 'error':
    case 'waiting':
      return desk;
    case 'idle':
      return SOFA_POSITIONS[agent.domain] ?? { x: 960, y: 570 };
    case 'searching':
      return BOOKSHELF_POS;
    case 'delivering':
      return { x: (desk.x + 540) / 2, y: (desk.y + 350) / 2 };
    case 'reviewing': {
      // Stand next to the director's desk
      const dirDesk = DESK_POSITIONS.director;
      return { x: dirDesk.x + 50, y: dirDesk.y + 10 };
    }
    default:
      return desk;
  }
}

export default function AgentCharacter({
  agent,
  x,
  y,
  onClick,
  isSelected,
}: AgentCharacterProps) {
  const colors = DOMAIN_COLORS[agent.domain] ?? DOMAIN_COLORS.frontend;
  const label = DOMAIN_LABELS[agent.domain] ?? agent.domain.slice(0, 3).toUpperCase();

  const isWorking = agent.status === 'working';
  const isThinking = agent.status === 'thinking';
  const isError = agent.status === 'error';
  const isWalking = agent.status === 'delivering' || agent.status === 'searching';

  return (
    <motion.g
      animate={{ x, y }}
      transition={{ type: 'spring', stiffness: 80, damping: 15 }}
      onClick={onClick}
      style={{ cursor: 'pointer' }}
    >
      {/* Selection highlight */}
      {isSelected && (
        <motion.rect
          x={-22}
          y={-4}
          width={44}
          height={56}
          rx={4}
          fill="none"
          stroke="#FFD700"
          strokeWidth={2}
          strokeDasharray="4 2"
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 1.5, repeat: Infinity }}
          shapeRendering="crispEdges"
        />
      )}

      {/* Shadow */}
      <ellipse cx={0} cy={50} rx={14} ry={4} fill="rgba(0,0,0,0.2)" />

      {/* Legs */}
      <motion.g
        animate={
          isWalking
            ? { y: [0, -2, 0, 2, 0] }
            : {}
        }
        transition={isWalking ? { duration: 0.5, repeat: Infinity } : {}}
      >
        <rect x={-8} y={36} width={6} height={12} rx={1} fill="#555566" shapeRendering="crispEdges" />
        <motion.rect
          x={2}
          y={36}
          width={6}
          height={12}
          rx={1}
          fill="#555566"
          shapeRendering="crispEdges"
          animate={isWalking ? { y: [36, 34, 36, 38, 36] } : {}}
          transition={isWalking ? { duration: 0.5, repeat: Infinity } : {}}
        />
        {/* Shoes */}
        <rect x={-9} y={46} width={8} height={4} rx={1} fill="#333344" shapeRendering="crispEdges" />
        <rect x={1} y={46} width={8} height={4} rx={1} fill="#333344" shapeRendering="crispEdges" />
      </motion.g>

      {/* Body */}
      <motion.rect
        x={-12}
        y={14}
        width={24}
        height={24}
        rx={2}
        fill={colors.body}
        shapeRendering="crispEdges"
        animate={{ scaleY: [1, 1.015, 1] }}
        transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
        style={{ transformOrigin: '0px 26px' }}
      />

      {/* Shirt detail / collar */}
      <rect x={-4} y={14} width={8} height={4} rx={1} fill={colors.accent} shapeRendering="crispEdges" />

      {/* Arms */}
      <motion.rect
        x={-18}
        y={18}
        width={7}
        height={14}
        rx={2}
        fill={colors.body}
        shapeRendering="crispEdges"
        animate={
          isWorking
            ? { y: [18, 16, 18] }
            : isThinking
              ? { rotate: [0, -10, 0] }
              : {}
        }
        transition={{ duration: 0.4, repeat: Infinity, ease: 'easeInOut' }}
        style={{ transformOrigin: '-14px 18px' }}
      />
      <motion.rect
        x={11}
        y={18}
        width={7}
        height={14}
        rx={2}
        fill={colors.body}
        shapeRendering="crispEdges"
        animate={
          isWorking
            ? { y: [18, 20, 18] }
            : isThinking
              ? { rotate: [0, 10, 0] }
              : {}
        }
        transition={{
          duration: 0.4,
          repeat: Infinity,
          ease: 'easeInOut',
          delay: isWorking ? 0.2 : 0,
        }}
        style={{ transformOrigin: '14px 18px' }}
      />

      {/* Hands (skin) */}
      <rect x={-17} y={30} width={5} height={4} rx={1} fill="#FFCC99" shapeRendering="crispEdges" />
      <rect x={12} y={30} width={5} height={4} rx={1} fill="#FFCC99" shapeRendering="crispEdges" />

      {/* Head */}
      <rect x={-10} y={-2} width={20} height={18} rx={3} fill="#FFCC99" shapeRendering="crispEdges" />

      {/* Hair */}
      <rect x={-11} y={-4} width={22} height={8} rx={2} fill={colors.hair} shapeRendering="crispEdges" />

      {/* Eyes */}
      <motion.g
        animate={{ scaleY: [1, 1, 0.1, 1, 1] }}
        transition={{ duration: 3, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }}
        style={{ transformOrigin: '0px 6px' }}
      >
        <rect x={-7} y={4} width={4} height={4} rx={1} fill="#333333" shapeRendering="crispEdges" />
        <rect x={3} y={4} width={4} height={4} rx={1} fill="#333333" shapeRendering="crispEdges" />
        {/* Tiny eye shine */}
        <rect x={-6} y={5} width={1} height={1} fill="#FFFFFF" shapeRendering="crispEdges" />
        <rect x={4} y={5} width={1} height={1} fill="#FFFFFF" shapeRendering="crispEdges" />
      </motion.g>

      {/* Mouth */}
      {isError ? (
        <rect x={-3} y={11} width={6} height={2} rx={0} fill="#CC3333" shapeRendering="crispEdges" />
      ) : isWorking ? (
        <rect x={-2} y={11} width={4} height={2} rx={0} fill="#AA7755" shapeRendering="crispEdges" />
      ) : (
        <path d="M-2,11 Q0,14 2,11" stroke="#AA7755" strokeWidth={1.5} fill="none" />
      )}

      {/* Domain-specific accessories */}
      {agent.domain === 'director' && (
        /* Crown */
        <g>
          <polygon
            points="-8,-6 -6,-10 -3,-6 0,-12 3,-6 6,-10 8,-6"
            fill="#FFD700"
            stroke="#DAA520"
            strokeWidth={1}
            shapeRendering="crispEdges"
          />
        </g>
      )}
      {agent.domain === 'frontend' && (
        /* Glasses */
        <g>
          <rect x={-9} y={3} width={7} height={6} rx={1} fill="none" stroke="#61DAFB" strokeWidth={1.5} shapeRendering="crispEdges" />
          <rect x={2} y={3} width={7} height={6} rx={1} fill="none" stroke="#61DAFB" strokeWidth={1.5} shapeRendering="crispEdges" />
          <line x1={-2} y1={6} x2={2} y2={6} stroke="#61DAFB" strokeWidth={1} />
        </g>
      )}
      {agent.domain === 'backend' && (
        /* Headphones */
        <g>
          <path d="M-12,4 Q-12,-6 0,-6 Q12,-6 12,4" fill="none" stroke="#68A063" strokeWidth={2.5} />
          <rect x={-14} y={2} width={5} height={8} rx={2} fill="#68A063" shapeRendering="crispEdges" />
          <rect x={9} y={2} width={5} height={8} rx={2} fill="#68A063" shapeRendering="crispEdges" />
        </g>
      )}
      {agent.domain === 'docs' && (
        /* Notebook held in hand */
        <g>
          <rect x={14} y={20} width={8} height={10} rx={1} fill="#F7DF1E" stroke="#C9B100" strokeWidth={1} shapeRendering="crispEdges" />
          <line x1={16} y1={23} x2={20} y2={23} stroke="#888" strokeWidth={0.5} />
          <line x1={16} y1={25} x2={20} y2={25} stroke="#888" strokeWidth={0.5} />
          <line x1={16} y1={27} x2={19} y2={27} stroke="#888" strokeWidth={0.5} />
        </g>
      )}
      {agent.domain === 'git' && (
        /* Git branch icon on shirt */
        <g>
          <circle cx={0} cy={24} r={2} fill="#FF7854" />
          <circle cx={0} cy={32} r={2} fill="#FF7854" />
          <circle cx={5} cy={28} r={2} fill="#FF7854" />
          <line x1={0} y1={24} x2={0} y2={32} stroke="#FF7854" strokeWidth={1} />
          <line x1={0} y1={28} x2={5} y2={28} stroke="#FF7854" strokeWidth={1} />
        </g>
      )}

      {/* Error indicator */}
      {isError && (
        <motion.g
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 0.8, repeat: Infinity }}
        >
          <circle cx={12} cy={-2} r={6} fill="#FF3333" />
          <text x={12} y={1} textAnchor="middle" fill="#FFFFFF" fontSize={8} fontWeight="bold">!</text>
        </motion.g>
      )}

      {/* Name badge */}
      <rect x={-12} y={52} width={24} height={10} rx={2} fill="rgba(0,0,0,0.6)" shapeRendering="crispEdges" />
      <text
        x={0}
        y={59}
        textAnchor="middle"
        fill={colors.accent}
        fontSize={6}
        fontFamily="'Press Start 2P', monospace"
      >
        {label}
      </text>

      {/* Speech bubble */}
      {agent.bubble && (
        <SpeechBubble
          x={0}
          y={-10}
          content={agent.bubble.content}
          type={agent.bubble.type}
        />
      )}

      {/* Thinking dots */}
      {isThinking && !agent.bubble && (
        <g>
          <motion.circle
            cx={-6}
            cy={-14}
            r={2}
            fill="#AAAAAA"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ duration: 1, repeat: Infinity, delay: 0 }}
          />
          <motion.circle
            cx={0}
            cy={-16}
            r={2}
            fill="#AAAAAA"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ duration: 1, repeat: Infinity, delay: 0.2 }}
          />
          <motion.circle
            cx={6}
            cy={-14}
            r={2}
            fill="#AAAAAA"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ duration: 1, repeat: Infinity, delay: 0.4 }}
          />
        </g>
      )}
    </motion.g>
  );
}
