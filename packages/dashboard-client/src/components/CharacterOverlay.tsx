/**
 * CharacterOverlay — DOM overlay for speech bubbles, thinking dots, and error indicators
 * Positioned absolutely on top of the Canvas, synced with character positions
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useOfficeStore } from '@/stores/office-store';
import { CANVAS_W, CANVAS_H, getAgentPixelPosition } from '@/engine/sprite-config';

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
  task: { bg: '#FFFFFF', border: '#333333', text: '#222222' },
  thinking: { bg: '#FFF8DC', border: '#DAA520', text: '#555555' },
  info: { bg: '#E0F0FF', border: '#4A90D9', text: '#333333' },
  error: { bg: '#FFE0E0', border: '#CC3333', text: '#AA0000' },
};

export default function CharacterOverlay() {
  const agents = useOfficeStore((s) => s.agents);
  const positionsRef = useRef<Map<string, PosState>>(new Map());
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map());

  // Check if any agent has a bubble — skip rAF when none
  const hasBubbles = useMemo(
    () => Object.values(agents).some((a) => a.bubble !== null),
    [agents],
  );

  // Sync spring positions with animation frame (only when bubbles exist)
  useEffect(() => {
    // Always init positions for new agents (so they're ready when bubbles appear)
    for (const agent of Object.values(agents)) {
      if (!positionsRef.current.has(agent.id)) {
        const pos = getAgentPixelPosition(agent.domain, agent.status);
        positionsRef.current.set(agent.id, { x: pos.x, y: pos.y, vx: 0, vy: 0 });
      }
    }

    if (!hasBubbles) return;

    let lastTime = 0;
    let raf = 0;

    const loop = (time: number) => {
      const dt = lastTime === 0 ? 16 : time - lastTime;
      lastTime = time;

      const newPositions = new Map<string, { x: number; y: number }>();
      for (const agent of Object.values(agents)) {
        if (!agent.bubble) continue; // only track agents with bubbles
        const s = positionsRef.current.get(agent.id);
        if (!s) continue;
        const target = getAgentPixelPosition(agent.domain, agent.status);
        springStep(s, target.x, target.y, dt);
        newPositions.set(agent.id, { x: s.x, y: s.y });
      }
      setPositions(newPositions);

      raf = requestAnimationFrame(loop);
    };

    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [agents, hasBubbles]);

  // The overlay is sized to match the canvas internal resolution (CANVAS_W x CANVAS_H)
  // by the parent wrapper, which uses CSS transform to scale it to the actual canvas display size.
  // So we can position bubbles directly in canvas pixel coordinates.

  return (
    <div
      className="pointer-events-none overflow-hidden"
      style={{ position: 'absolute', left: 0, top: 0, width: CANVAS_W, height: CANVAS_H, imageRendering: 'auto' }}
    >
      <AnimatePresence>
        {Object.values(agents).map((agent) => {
          const pos = positions.get(agent.id);
          if (!pos) return null;

          const bubble = agent.bubble;
          if (!bubble) return null;

          const style = BUBBLE_STYLES[bubble.type] ?? BUBBLE_STYLES.info;
          const truncated = bubble.content.length > 24
            ? bubble.content.slice(0, 22) + '..'
            : bubble.content;

          return (
            <motion.div
              key={`bubble-${agent.id}`}
              initial={{ opacity: 0, y: 4, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.9 }}
              transition={{ duration: 0.25 }}
              className="absolute -translate-x-1/2 -translate-y-full"
              style={{ left: pos.x, top: pos.y - 48 }}
            >
              {/* Bubble body */}
              <div
                className="px-2 py-1 rounded whitespace-nowrap font-pixel"
                style={{
                  backgroundColor: style.bg,
                  border: `2px solid ${style.border}`,
                  color: style.text,
                  fontSize: '7px',
                  lineHeight: '10px',
                  boxShadow: '2px 2px 0px rgba(0,0,0,0.3)',
                }}
              >
                {truncated}
              </div>
              {/* Triangle pointer */}
              <div
                className="mx-auto w-0 h-0"
                style={{
                  borderLeft: '5px solid transparent',
                  borderRight: '5px solid transparent',
                  borderTop: `5px solid ${style.border}`,
                }}
              />
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
