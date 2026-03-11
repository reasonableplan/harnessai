/**
 * Color utility helpers and walk cycle functions for character rendering
 */

/** Lighten a hex color by a factor (0-1) */
export function lighten(hex: string, factor: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const lr = Math.min(255, Math.round(r + (255 - r) * factor));
  const lg = Math.min(255, Math.round(g + (255 - g) * factor));
  const lb = Math.min(255, Math.round(b + (255 - b) * factor));
  return `#${lr.toString(16).padStart(2, '0')}${lg.toString(16).padStart(2, '0')}${lb.toString(16).padStart(2, '0')}`;
}

/** Darken a hex color by a factor (0-1) */
export function darken(hex: string, factor: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const dr = Math.round(r * (1 - factor));
  const dg = Math.round(g * (1 - factor));
  const db = Math.round(b * (1 - factor));
  return `#${dr.toString(16).padStart(2, '0')}${dg.toString(16).padStart(2, '0')}${db.toString(16).padStart(2, '0')}`;
}

/** Draw a single pixel */
export function px(ctx: CanvasRenderingContext2D, x: number, y: number, w = 1, h = 1) {
  ctx.fillRect(x, y, w, h);
}

/** Set fill and draw a pixel in one call */
export function cpx(ctx: CanvasRenderingContext2D, color: string, x: number, y: number, w = 1, h = 1) {
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, h);
}

/** Draw a rounded rectangle (pixel art style - cut corners) */
export function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  color: string, cornerSize = 1,
) {
  ctx.fillStyle = color;
  // Main body
  ctx.fillRect(x + cornerSize, y, w - cornerSize * 2, h);
  ctx.fillRect(x, y + cornerSize, w, h - cornerSize * 2);
}

// ---- Walk cycle offsets ----

export function getWalkBob(walkFrame: number): number {
  // Bob pattern: 0, -1, 0, -1
  return walkFrame % 2 === 1 ? -1 : 0;
}

export function getWalkStride(walkFrame: number): { left: number; right: number } {
  // Stride pattern for legs: frame 0=center, 1=left forward, 2=center, 3=right forward
  switch (walkFrame) {
    case 0: return { left: 0, right: 0 };
    case 1: return { left: -2, right: 2 };
    case 2: return { left: 0, right: 0 };
    case 3: return { left: 2, right: -2 };
    default: return { left: 0, right: 0 };
  }
}
