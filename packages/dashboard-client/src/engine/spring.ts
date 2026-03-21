/**
 * 공통 spring physics — OfficeCanvas와 CharacterOverlay에서 공유.
 */

export const SPRING_STIFFNESS = 0.04;
export const SPRING_DAMPING = 0.82;
export const SNAP_THRESHOLD = 0.5;

export interface SpringState {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

/**
 * spring 물리 업데이트. targetX/targetY를 향해 수렴한다.
 * dt는 밀리초 단위 (requestAnimationFrame timestamp 차이).
 */
export function updateSpring(
  s: SpringState,
  targetX: number,
  targetY: number,
  dt: number,
): void {
  const factor = Math.min(dt / 16, 3); // normalize to ~60fps, cap at 3x
  const dx = targetX - s.x;
  const dy = targetY - s.y;
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
    s.x = targetX;
    s.y = targetY;
    s.vx = 0;
    s.vy = 0;
  }
}
