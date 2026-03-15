/**
 * OfficeCanvas — Canvas-based LPC office scene with render loop
 * Handles: background rendering, character animation, movement interpolation, click hit-testing
 */

import { useRef, useEffect, useCallback } from 'react';
import { useOfficeStore, type AgentState } from '@/stores/office-store';
import { createBackgroundBuffer, createBackgroundBufferAsync } from './tile-renderer';
import { prerenderCharacters, prerenderCharactersAsync, rebuildCache } from './character-renderer';
import {
  CANVAS_W,
  CANVAS_H,
  CHAR_W,
  CHAR_H,
  RENDER_SCALE,
  AGENT_COLORS,
  getAgentPixelPosition,
  getAgentLabel,
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
  if (
    Math.abs(dx) < SNAP_THRESHOLD &&
    Math.abs(dy) < SNAP_THRESHOLD &&
    Math.abs(s.vx) < SNAP_THRESHOLD &&
    Math.abs(s.vy) < SNAP_THRESHOLD
  ) {
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
const ARM_FRAME_DURATION = 250; // ms per arm frame
const BLINK_INTERVAL = 3500; // ms between blinks
const BLINK_DURATION = 150; // ms blink lasts

function createAgentAnimState(slot: number): AgentAnimState {
  const pos = getAgentPixelPosition(slot, 'idle');
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

// ---- Hit testing (works in logical coords) ----
function hitTest(
  logicalX: number,
  logicalY: number,
  animStates: Map<string, AgentAnimState>,
): string | null {
  // Check agents in reverse Y-order (front-most first)
  const entries = [...animStates.entries()].sort((a, b) => b[1].spring.y - a[1].spring.y);
  const padX = (CHAR_W + 16) / 2;
  const padY = CHAR_H + 16;

  for (const [id, state] of entries) {
    const cx = state.spring.x;
    const cy = state.spring.y;
    // Hit box around character (logical coords)
    if (
      logicalX >= cx - padX &&
      logicalX <= cx + padX &&
      logicalY >= cy - padY &&
      logicalY <= cy + 16
    ) {
      return id;
    }
  }
  return null;
}

// ---- Name badge drawing (receives physical coords) ----
function drawNameBadge(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  agentId: string,
  domain: string,
) {
  const label = getAgentLabel(agentId, domain);
  const colors = AGENT_COLORS[domain];
  const accent = colors?.accent ?? '#FFFFFF';

  const S = RENDER_SCALE;
  const badgeW = 22 * S;
  const badgeH = 10 * S;
  const bx = x - badgeW / 2;
  const by = y;

  // Background (warm wood)
  ctx.fillStyle = 'rgba(45,27,14,0.85)';
  ctx.fillRect(bx, by, badgeW, badgeH);
  // Border
  ctx.strokeStyle = 'rgba(140,100,50,0.6)';
  ctx.lineWidth = S;
  ctx.strokeRect(bx, by, badgeW, badgeH);
  // Accent top line
  ctx.fillStyle = accent;
  ctx.fillRect(bx, by, badgeW, 2 * S);
  // Text
  ctx.fillStyle = accent;
  ctx.font = `${5 * S}px "Press Start 2P", monospace`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, x, by + badgeH / 2 + S);
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
}

// ---- Status indicator drawing (receives physical coords) ----
function drawStatusIndicator(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  status: string,
  time: number,
) {
  const S = RENDER_SCALE;
  if (status === 'error') {
    const alpha = 0.5 + 0.5 * Math.sin(time * 0.008);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = '#CC3333';
    ctx.beginPath();
    ctx.arc(x + 10 * S, y - 4 * S, 5 * S, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#FFFFFF';
    ctx.font = `bold ${6 * S}px monospace`;
    ctx.textAlign = 'center';
    ctx.fillText('!', x + 10 * S, y - 2 * S);
    ctx.textAlign = 'left';
    ctx.globalAlpha = 1;
  } else if (status === 'working') {
    const alpha = 0.5 + 0.5 * Math.sin(time * 0.005);
    ctx.globalAlpha = alpha;
    ctx.fillStyle = 'rgba(90,140,80,0.6)';
    ctx.fillRect(x - 8 * S, y - 12 * S, 16 * S, 7 * S);
    ctx.fillStyle = '#7CC46A';
    ctx.font = `${4 * S}px monospace`;
    ctx.textAlign = 'center';
    ctx.fillText('</>', x, y - 7 * S);
    ctx.textAlign = 'left';
    ctx.globalAlpha = 1;
  } else if (status === 'thinking') {
    for (let i = 0; i < 3; i++) {
      const dotY = y - 14 * S + Math.sin(time * 0.006 + i * 1.2) * 2 * S;
      const alpha = 0.4 + 0.6 * Math.abs(Math.sin(time * 0.004 + i * 0.8));
      ctx.globalAlpha = alpha;
      ctx.fillStyle = '#E8D8B0';
      ctx.beginPath();
      ctx.arc(x - 4 * S + i * 5 * S, dotY, 2 * S, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
}

// ---- Selection highlight (receives physical coords) ----
function drawSelectionHighlight(ctx: CanvasRenderingContext2D, x: number, y: number, time: number) {
  const S = RENDER_SCALE;
  const alpha = 0.4 + 0.3 * Math.sin(time * 0.004);
  ctx.strokeStyle = '#D4A840';
  ctx.lineWidth = 2 * S;
  ctx.globalAlpha = alpha;
  ctx.setLineDash([4 * S, 3 * S]);
  ctx.strokeRect(x - 20 * S, y - 56 * S, 40 * S, 68 * S);
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
  const retryTimerRef = useRef<ReturnType<typeof window.setTimeout> | number>(0);

  // Subscribe to store
  const agents = useOfficeStore((s) => s.agents);
  const selectedAgent = useOfficeStore((s) => s.selectedAgent);
  const characterVersion = useOfficeStore((s) => s.characterVersion);

  // Keep refs in sync
  agentsRef.current = agents;
  selectedAgentRef.current = selectedAgent;

  // Initialize buffers (no agents dependency — anim state init handled by second useEffect)
  useEffect(() => {
    ctxRef.current = canvasRef.current?.getContext('2d') ?? null;

    // Sync fallbacks: immediately visible while async assets load
    bgBufferRef.current = createBackgroundBuffer();
    charCacheRef.current = prerenderCharacters();

    // Async upgrades: tileset background + image sprites
    let cancelled = false;
    createBackgroundBufferAsync()
      .then((buffer) => { if (!cancelled) bgBufferRef.current = buffer; })
      .catch(() => { /* keep procedural fallback */ });
    prerenderCharactersAsync()
      .then((cache) => { if (!cancelled && cache.size > 0) charCacheRef.current = cache; })
      .catch(() => { /* keep pixel-map fallback */ });

    return () => { cancelled = true; };
  }, []);

  // Rebuild character cache when assignments change
  useEffect(() => {
    if (characterVersion === 0) return; // skip initial mount
    charCacheRef.current = rebuildCache();
  }, [characterVersion]);

  // Ensure anim states exist for new agents
  useEffect(() => {
    for (const agent of Object.values(agents)) {
      if (!animStatesRef.current.has(agent.id)) {
        animStatesRef.current.set(agent.id, createAgentAnimState(agent.slot));
      }
    }
  }, [agents]);

  // ---- Render loop ----
  // deps는 의도적으로 비어있음 — 모든 동적 값은 ref를 통해 접근
  useEffect(() => {
    let lastTime = 0;

    const loop = (time: number) => {
      const dt = lastTime === 0 ? 16 : time - lastTime;
      lastTime = time;

      const ctx = ctxRef.current;
      if (!ctx || !bgBufferRef.current || !charCacheRef.current) {
        // Retry after a short delay to avoid CPU spike during initialization
        retryTimerRef.current = window.setTimeout(() => {
          if (rafRef.current === 0) {
            rafRef.current = requestAnimationFrame(loop);
          }
        }, 100);
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

        const target = getAgentPixelPosition(agent.slot, agent.status);
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

        // Desk animation (working/thinking/waiting — 6-frame idle-anim cycle)
        const isDeskStatus =
          agent.status === 'working' || agent.status === 'thinking' || agent.status === 'waiting';
        if (isDeskStatus) {
          state.armTimer += dt;
          if (state.armTimer >= ARM_FRAME_DURATION) {
            state.armTimer = 0;
            state.armFrame = (state.armFrame + 1) % 6;
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

      // Draw characters (spring positions are in logical coords, scale to physical)
      for (const { agent, state } of sorted) {
        const cx = Math.round(state.spring.x * RENDER_SCALE);
        const cy = Math.round(state.spring.y * RENDER_SCALE);

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
            const walkFrames =
              agent.status === 'delivering' || agent.status === 'searching' ? 4 : 1;
            const deskAnim =
              agent.status === 'working' || agent.status === 'thinking' || agent.status === 'waiting';
            if (deskAnim) {
              frameIdx = state.armFrame;
            } else if (walkFrames > 1) {
              frameIdx = state.walkFrame % walkFrames;
            } else {
              frameIdx = 0;
            }
          }

          const frame = frames[Math.min(frameIdx, frames.length - 1)];
          // Draw centered at (cx, cy) — character bottom at cy
          // Cached canvas is (CHAR_W+16)*SCALE wide, (CHAR_H+16)*SCALE tall
          ctx.drawImage(
            frame,
            cx - ((CHAR_W + 16) * RENDER_SCALE) / 2,
            cy - (CHAR_H + 16) * RENDER_SCALE,
          );
        }

        // Status indicator & name badge drawn in physical coords
        if (!agent.bubble) {
          drawStatusIndicator(ctx, cx, cy - CHAR_H * RENDER_SCALE, agent.status, time);
        }

        drawNameBadge(ctx, cx, cy + 4 * RENDER_SCALE, agent.id, agent.domain);
      }

      rafRef.current = requestAnimationFrame(loop);
    };

    rafRef.current = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(rafRef.current);
      clearTimeout(retryTimerRef.current);
    };
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
      // Convert to logical coords (divide by RENDER_SCALE) for hit testing
      const canvasX = (((e.clientX - rect.left - offsetX) / renderW) * CANVAS_W) / RENDER_SCALE;
      const canvasY = (((e.clientY - rect.top - offsetY) / renderH) * CANVAS_H) / RENDER_SCALE;

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
