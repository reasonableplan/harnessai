/**
 * OfficeCanvas — Canvas-based LPC office scene with render loop
 * Handles: background rendering, character animation, movement interpolation, click hit-testing
 */

import { useRef, useEffect, useCallback } from 'react';
import { useOfficeStore, type AgentState } from '@/stores/office-store';
import { createBackgroundBuffer } from './tile-renderer';
import { prerenderCharacters } from './character-renderer';
import {
  CANVAS_W,
  CANVAS_H,
  CHAR_W,
  CHAR_H,
  DOMAIN_LABELS,
  AGENT_COLORS,
  getAgentPixelPosition,
} from './sprite-config';

// ---- Spring physics for smooth movement ----
interface SpringState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  targetX: number;
  targetY: number;
}

const SPRING_STIFFNESS = 0.04;
const SPRING_DAMPING = 0.82;
const SNAP_THRESHOLD = 0.5;

function updateSpring(s: SpringState, dt: number): void {
  const factor = Math.min(dt / 16, 3); // normalize to ~60fps, cap at 3x
  const dx = s.targetX - s.x;
  const dy = s.targetY - s.y;
  s.vx = (s.vx + dx * SPRING_STIFFNESS * factor) * SPRING_DAMPING;
  s.vy = (s.vy + dy * SPRING_STIFFNESS * factor) * SPRING_DAMPING;
  s.x += s.vx * factor;
  s.y += s.vy * factor;

  // Snap when close enough
  if (Math.abs(dx) < SNAP_THRESHOLD && Math.abs(dy) < SNAP_THRESHOLD &&
      Math.abs(s.vx) < SNAP_THRESHOLD && Math.abs(s.vy) < SNAP_THRESHOLD) {
    s.x = s.targetX;
    s.y = s.targetY;
    s.vx = 0;
    s.vy = 0;
  }
}

// ---- Animation state per agent ----
interface AgentAnimState {
  spring: SpringState;
  walkFrame: number;
  walkTimer: number;
  armFrame: number;
  armTimer: number;
  blinkTimer: number;
  isBlinking: boolean;
}

const WALK_FRAME_DURATION = 180; // ms per walk frame
const ARM_FRAME_DURATION = 250;  // ms per arm frame
const BLINK_INTERVAL = 3500;     // ms between blinks
const BLINK_DURATION = 150;      // ms blink lasts

function createAgentAnimState(domain: string): AgentAnimState {
  const pos = getAgentPixelPosition(domain, 'idle');
  return {
    spring: { x: pos.x, y: pos.y, vx: 0, vy: 0, targetX: pos.x, targetY: pos.y },
    walkFrame: 0,
    walkTimer: 0,
    armFrame: 0,
    armTimer: 0,
    blinkTimer: Math.random() * BLINK_INTERVAL, // stagger blinks
    isBlinking: false,
  };
}

// ---- Hit testing ----
function hitTest(
  canvasX: number,
  canvasY: number,
  animStates: Map<string, AgentAnimState>,
): string | null {
  // Check agents in reverse Y-order (front-most first)
  const entries = [...animStates.entries()].sort((a, b) => b[1].spring.y - a[1].spring.y);
  const padX = (CHAR_W + 8) / 2;
  const padY = CHAR_H + 8;

  for (const [id, state] of entries) {
    const cx = state.spring.x;
    const cy = state.spring.y;
    // Hit box around character
    if (canvasX >= cx - padX && canvasX <= cx + padX &&
        canvasY >= cy - padY && canvasY <= cy + 8) {
      return id;
    }
  }
  return null;
}

// ---- Name badge drawing ----
function drawNameBadge(ctx: CanvasRenderingContext2D, x: number, y: number, domain: string) {
  const label = DOMAIN_LABELS[domain] ?? domain.slice(0, 3).toUpperCase();
  const colors = AGENT_COLORS[domain];
  const accent = colors?.accent ?? '#FFFFFF';

  const badgeW = 22;
  const badgeH = 10;
  const bx = x - badgeW / 2;
  const by = y;

  // Background
  ctx.fillStyle = 'rgba(0,0,0,0.75)';
  ctx.fillRect(bx, by, badgeW, badgeH);
  // Accent top line
  ctx.fillStyle = accent;
  ctx.fillRect(bx, by, badgeW, 2);
  // Text
  ctx.fillStyle = accent;
  ctx.font = '5px "Press Start 2P", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, x, by + badgeH / 2 + 1);
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
}

// ---- Status indicator drawing ----
function drawStatusIndicator(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  status: string,
  time: number,
) {
  if (status === 'error') {
    // Flashing red circle with !
    const alpha = 0.5 + 0.5 * Math.sin(time * 0.008);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = '#FF3333';
    ctx.beginPath();
    ctx.arc(x + 10, y - 4, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#FFFFFF';
    ctx.font = 'bold 6px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('!', x + 10, y - 2);
    ctx.textAlign = 'left';
    ctx.globalAlpha = 1;
  } else if (status === 'working') {
    // Small code icon
    const alpha = 0.5 + 0.5 * Math.sin(time * 0.005);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = 'rgba(104,160,99,0.6)';
    ctx.fillRect(x - 8, y - 12, 16, 7);
    ctx.fillStyle = '#68A063';
    ctx.font = '4px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('</>', x, y - 7);
    ctx.textAlign = 'left';
    ctx.globalAlpha = 1;
  } else if (status === 'thinking') {
    // Thinking dots
    for (let i = 0; i < 3; i++) {
      const dotY = y - 14 + Math.sin(time * 0.006 + i * 1.2) * 2;
      const alpha = 0.4 + 0.6 * Math.abs(Math.sin(time * 0.004 + i * 0.8));
      ctx.globalAlpha = alpha;
      ctx.fillStyle = '#CCCCCC';
      ctx.beginPath();
      ctx.arc(x - 4 + i * 5, dotY, 2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
}

// ---- Selection highlight ----
function drawSelectionHighlight(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  time: number,
) {
  const alpha = 0.4 + 0.3 * Math.sin(time * 0.004);
  ctx.strokeStyle = '#FFD700';
  ctx.lineWidth = 2;
  ctx.globalAlpha = alpha;
  ctx.setLineDash([4, 3]);
  ctx.strokeRect(x - 16, y - 38, 32, 50);
  ctx.setLineDash([]);
  ctx.globalAlpha = 1;
}

// ================ COMPONENT ================

interface OfficeCanvasProps {
  onAgentClick: (id: string | null) => void;
}

export default function OfficeCanvas({ onAgentClick }: OfficeCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
  const bgBufferRef = useRef<HTMLCanvasElement | null>(null);
  const charCacheRef = useRef<Map<string, HTMLCanvasElement[]> | null>(null);
  const animStatesRef = useRef<Map<string, AgentAnimState>>(new Map());
  const agentsRef = useRef<Record<string, AgentState>>({});
  const selectedAgentRef = useRef<string | null>(null);
  const rafRef = useRef<number>(0);

  // Subscribe to store
  const agents = useOfficeStore((s) => s.agents);
  const selectedAgent = useOfficeStore((s) => s.selectedAgent);

  // Keep refs in sync
  agentsRef.current = agents;
  selectedAgentRef.current = selectedAgent;

  // Initialize buffers + anim states
  useEffect(() => {
    ctxRef.current = canvasRef.current?.getContext('2d') ?? null;
    bgBufferRef.current = createBackgroundBuffer();
    charCacheRef.current = prerenderCharacters();

    // Init anim states for all agents
    for (const agent of Object.values(agents)) {
      if (!animStatesRef.current.has(agent.id)) {
        animStatesRef.current.set(agent.id, createAgentAnimState(agent.domain));
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Ensure anim states exist for new agents
  useEffect(() => {
    for (const agent of Object.values(agents)) {
      if (!animStatesRef.current.has(agent.id)) {
        animStatesRef.current.set(agent.id, createAgentAnimState(agent.domain));
      }
    }
  }, [agents]);

  // ---- Render loop ----
  useEffect(() => {
    let lastTime = 0;

    const loop = (time: number) => {
      const dt = lastTime === 0 ? 16 : time - lastTime;
      lastTime = time;

      const ctx = ctxRef.current;
      if (!ctx || !bgBufferRef.current || !charCacheRef.current) {
        rafRef.current = requestAnimationFrame(loop);
        return;
      }

      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

      // 1) Draw pre-rendered background
      ctx.drawImage(bgBufferRef.current, 0, 0);

      // 2) Update & draw characters (sorted by Y for depth)
      const currentAgents = agentsRef.current;
      const selected = selectedAgentRef.current;
      const charCache = charCacheRef.current;

      const agentEntries = Object.values(currentAgents);

      // Update animation states
      for (const agent of agentEntries) {
        const state = animStatesRef.current.get(agent.id);
        if (!state) continue;

        const target = getAgentPixelPosition(agent.domain, agent.status);
        state.spring.targetX = target.x;
        state.spring.targetY = target.y;
        updateSpring(state.spring, dt);

        const isMoving = Math.abs(state.spring.vx) > 1 || Math.abs(state.spring.vy) > 1;
        const isWalkStatus = agent.status === 'delivering' || agent.status === 'searching';

        // Walk animation
        if (isMoving || isWalkStatus) {
          state.walkTimer += dt;
          if (state.walkTimer >= WALK_FRAME_DURATION) {
            state.walkTimer = 0;
            state.walkFrame = (state.walkFrame + 1) % 4;
          }
        } else {
          state.walkFrame = 0;
          state.walkTimer = 0;
        }

        // Arm animation (working)
        if (agent.status === 'working') {
          state.armTimer += dt;
          if (state.armTimer >= ARM_FRAME_DURATION) {
            state.armTimer = 0;
            state.armFrame = (state.armFrame + 1) % 2;
          }
        } else {
          state.armFrame = 0;
          state.armTimer = 0;
        }

        // Blink
        state.blinkTimer += dt;
        if (state.isBlinking) {
          if (state.blinkTimer >= BLINK_DURATION) {
            state.isBlinking = false;
            state.blinkTimer = 0;
          }
        } else if (state.blinkTimer >= BLINK_INTERVAL) {
          state.isBlinking = true;
          state.blinkTimer = 0;
        }
      }

      // Sort by Y for depth
      const sorted = agentEntries
        .map((a) => ({ agent: a, state: animStatesRef.current.get(a.id)! }))
        .filter((e) => e.state)
        .sort((a, b) => a.state.spring.y - b.state.spring.y);

      // Draw characters
      for (const { agent, state } of sorted) {
        const cx = Math.round(state.spring.x);
        const cy = Math.round(state.spring.y);

        // Selection highlight (behind character)
        if (agent.id === selected) {
          drawSelectionHighlight(ctx, cx, cy, time);
        }

        // Pick the right cached frame
        const cacheKey = `${agent.domain}:${agent.status}`;
        const frames = charCache.get(cacheKey);
        if (frames && frames.length > 0) {
          let frameIdx: number;
          if (state.isBlinking) {
            frameIdx = frames.length - 1; // last frame is blink
          } else {
            const walkFrames = (agent.status === 'delivering' || agent.status === 'searching') ? 4 : 1;
            const armFrames = agent.status === 'working' ? 2 : 1;
            if (armFrames > 1) {
              frameIdx = state.armFrame;
            } else if (walkFrames > 1) {
              frameIdx = state.walkFrame % walkFrames;
            } else {
              frameIdx = 0;
            }
          }

          const frame = frames[Math.min(frameIdx, frames.length - 1)];
          // Draw centered at (cx, cy) — character bottom at cy
          // Canvas is CHAR_W+8 wide, CHAR_H+12 tall, char drawn at translate(4,8)
          ctx.drawImage(
            frame,
            cx - (CHAR_W + 8) / 2,
            cy - CHAR_H - 8,
          );
        }

        // Status indicator
        if (!agent.bubble) {
          drawStatusIndicator(ctx, cx, cy - CHAR_H, agent.status, time);
        }

        // Name badge below character
        drawNameBadge(ctx, cx, cy + 4, agent.domain);
      }

      rafRef.current = requestAnimationFrame(loop);
    };

    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // ---- Click handler ----
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      // Account for object-fit: contain letterbox/pillarbox
      const canvasAspect = CANVAS_W / CANVAS_H;
      const elemAspect = rect.width / rect.height;
      let renderW: number, renderH: number, offsetX: number, offsetY: number;
      if (elemAspect > canvasAspect) {
        // Pillarboxed (element wider than canvas aspect)
        renderH = rect.height;
        renderW = rect.height * canvasAspect;
        offsetX = (rect.width - renderW) / 2;
        offsetY = 0;
      } else {
        // Letterboxed (element taller than canvas aspect)
        renderW = rect.width;
        renderH = rect.width / canvasAspect;
        offsetX = 0;
        offsetY = (rect.height - renderH) / 2;
      }
      const canvasX = ((e.clientX - rect.left - offsetX) / renderW) * CANVAS_W;
      const canvasY = ((e.clientY - rect.top - offsetY) / renderH) * CANVAS_H;

      const hitId = hitTest(canvasX, canvasY, animStatesRef.current);
      onAgentClick(hitId);
    },
    [onAgentClick],
  );

  return (
    <canvas
      ref={canvasRef}
      width={CANVAS_W}
      height={CANVAS_H}
      onClick={handleClick}
      style={{
        width: '100%',
        height: '100%',
        imageRendering: 'pixelated',
        cursor: 'pointer',
        objectFit: 'contain',
      }}
    />
  );
}
