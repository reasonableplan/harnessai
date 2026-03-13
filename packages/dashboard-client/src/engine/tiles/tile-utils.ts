/**
 * Tile rendering utilities: seeded random, circle helper, color palettes
 * Stardew Valley-inspired warm, cozy palette
 */

import { TILE_SIZE } from '../sprite-config';

export const T = TILE_SIZE;

/* Seeded pseudo-random for deterministic per-tile variation */
export function hash(a: number, b: number): number {
  let h = (a * 2654435761) ^ (b * 2246822519);
  h = ((h >>> 16) ^ h) * 0x45d9f3b;
  h = ((h >>> 16) ^ h) * 0x45d9f3b;
  return ((h >>> 16) ^ h) >>> 0;
}

export function rand(col: number, row: number, seed = 0): number {
  return (hash(col + seed * 137, row + seed * 311) & 0xffff) / 0x10000;
}

/* Draw a small filled circle */
export function fillCircle(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
}

/* Color palettes — Stardew Valley warm wood & stone */
export const FLOOR_COLORS = ['#C8A66B', '#CCAA70', '#C2A065', '#D2B478'];
export const FLOOR_GRAIN = '#A08050';
export const FLOOR_KNOT = '#8A6A3A';
export const FLOOR_BORDER = '#A08555';

export const WALL_COLORS = ['#8B7355', '#836C4E', '#937B5D', '#7B6448'];
export const BRICK_HI = 'rgba(255,240,200,0.18)';
export const BRICK_SH = 'rgba(0,0,0,0.12)';
export const WALL_CAP = '#5A4530';
export const WAINSCOT_BASE = '#6B5030';
export const WAINSCOT_HI = '#8A6840';
export const WAINSCOT_BEVEL_L = '#9A7850';
export const WAINSCOT_BEVEL_D = '#4A3820';
export const BASEBOARD = '#3E2E1E';
