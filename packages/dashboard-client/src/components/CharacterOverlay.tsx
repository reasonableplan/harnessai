/**
 * CharacterOverlay — DOM overlay for speech bubbles, thinking dots, and error indicators
 * Positioned absolutely on top of the Canvas, synced with character positions
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useOfficeStore } from '@/stores/office-store';
import { CANVAS_W, CANVAS_H, RENDER_SCALE, getAgentPixelPosition } from '@/engine/sprite-config';
// Position lookup now uses agent.slot instead of agent.domain

// Spring state mirror (same logic as OfficeCanvas for position sync)
interface PosState {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

const STIFFNESS = 0.04;
const DAMPING = 0.82;

function springStep(s: PosState, tx: number, ty: number, dt: number) {
  const f = Math.min(dt / 16, 3);
  const dx = tx - s.x;
  const dy = ty - s.y;
  s.vx = (s.vx + dx * STIFFNESS * f) * DAMPING;
  s.vy = (s.vy + dy * STIFFNESS * f) * DAMPING;
  s.x += s.vx * f;
  s.y += s.vy * f;
  if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5 && Math.abs(s.vx) < 0.5 && Math.abs(s.vy) < 0.5) {
    s.x = tx;
    s.y = ty;
    s.vx = 0;
    s.vy = 0;
  }
}

// Bubble type colors
const BUBBLE_STYLES: Record<string, { bg: string; border: string; text: string }> = {
  task: { bg: '#FFF8EC', border: '#8A6838', text: '#3A2A10' },
  thinking: { bg: '#FFF8DC', border: '#C4A040', text: '#5A4020' },
  info: { bg: '#E8F0E0', border: '#5A8A48', text: '#2A4020' },
  error: { bg: '#FFE4D8', border: '#C04030', text: '#8A2020' },
  warning: { bg: '#FFF3CD', border: '#C4900A', text: '#6A4A04' },
};

export default function CharacterOverlay() {
  const agents = useOfficeStore((s) => s.agents);
  // Keep agents in a ref so the rAF loop always reads latest value without restarting
  const agentsRef = useRef(agents);
  agentsRef.current = agents;

  const positionsRef = useRef<Map<string, PosState>>(new Map());
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map());
  const renderedPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const rafRef = useRef<number>(0);

  // Check if any agent has a bubble — skip rAF when none
  const hasBubbles = useMemo(() => Object.values(agents).some((a) => a.bubble !== null), [agents]);

  // Sync spring positions with animation frame (only when bubbles exist)
  // agents dep removed — always read from agentsRef inside loop to avoid rAF restarts
  useEffect(() => {
    // Always init positions for new agents (so they're ready when bubbles appear)
    for (const agent of Object.values(agentsRef.current)) {
      if (!positionsRef.current.has(agent.id)) {
        const pos = getAgentPixelPosition(agent.slot, agent.status);
        positionsRef.current.set(agent.id, { x: pos.x, y: pos.y, vx: 0, vy: 0 });
      }
    }

    if (!hasBubbles) return undefined;

    let lastTime = 0;

    const loop = (time: number) => {
      const dt = lastTime === 0 ? 16 : time - lastTime;
      lastTime = time;

      const newPositions = new Map<string, { x: number; y: number }>();
      let changed = false;
      for (const agent of Object.values(agentsRef.current)) {
        if (!agent.bubble) continue; // only track agents with bubbles
        let s = positionsRef.current.get(agent.id);
        if (!s) {
          // Initialize spring for dynamically added agents
          const pos = getAgentPixelPosition(agent.slot, agent.status);
          s = { x: pos.x, y: pos.y, vx: 0, vy: 0 };
          positionsRef.current.set(agent.id, s);
        }
        const target = getAgentPixelPosition(agent.slot, agent.status);
        springStep(s, target.x, target.y, dt);
        const nx = Math.round(s.x * RENDER_SCALE);
        const ny = Math.round(s.y * RENDER_SCALE);
        newPositions.set(agent.id, { x: nx, y: ny });
        const prev = renderedPositionsRef.current.get(agent.id);
        if (!prev || prev.x !== nx || prev.y !== ny) changed = true;
      }
      if (changed || newPositions.size !== renderedPositionsRef.current.size) {
        renderedPositionsRef.current = newPositions;
        setPositions(newPositions);
      }

      rafRef.current = requestAnimationFrame(loop);
    };

    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [hasBubbles]);

  // The overlay is sized to match the canvas internal resolution (CANVAS_W x CANVAS_H)
  // by the parent wrapper, which uses CSS transform to scale it to the actual canvas display size.
  // So we can position bubbles directly in canvas pixel coordinates.

  return (
    <div
      className="pointer-events-none overflow-hidden"
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        width: CANVAS_W,
        height: CANVAS_H,
        imageRendering: 'auto',
      }}
    >
      <AnimatePresence>
        {Object.values(agents).map((agent) => {
          const pos = positions.get(agent.id);
          if (!pos) return null;

          const bubble = agent.bubble;
          if (!bubble) return null;

          const style = BUBBLE_STYLES[bubble.type] ?? BUBBLE_STYLES.info;
          const truncated =
            bubble.content.length > 24 ? bubble.content.slice(0, 22) + '..' : bubble.content;

          return (
            <motion.div
              key={`bubble-${agent.id}`}
              initial={{ opacity: 0, y: 4, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.9 }}
              transition={{ duration: 0.25 }}
              className="absolute"
              style={{
                left: pos.x + 24 * RENDER_SCALE,
                top: pos.y - 80 * RENDER_SCALE,
                transform: 'translateY(-100%)',
              }}
            >
              {/* Bubble body */}
              <div
                className="rounded whitespace-nowrap font-pixel"
                style={{
                  backgroundColor: style.bg,
                  border: `${2 * RENDER_SCALE}px solid ${style.border}`,
                  padding: `${RENDER_SCALE * 4}px ${RENDER_SCALE * 8}px`,
                  color: style.text,
                  fontSize: `${7 * RENDER_SCALE}px`,
                  lineHeight: `${10 * RENDER_SCALE}px`,
                  boxShadow: `${2 * RENDER_SCALE}px ${2 * RENDER_SCALE}px 0px rgba(0,0,0,0.3)`,
                }}
              >
                {truncated}
              </div>
              {/* Triangle pointer — bottom-left, pointing down toward character */}
              <div
                className="w-0 h-0"
                style={{
                  marginLeft: `${4 * RENDER_SCALE}px`,
                  borderLeft: `${5 * RENDER_SCALE}px solid transparent`,
                  borderRight: `${5 * RENDER_SCALE}px solid transparent`,
                  borderTop: `${5 * RENDER_SCALE}px solid ${style.border}`,
                }}
              />
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
