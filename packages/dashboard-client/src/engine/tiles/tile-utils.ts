/**
 * Tile rendering utilities: seeded random, circle helper, color palettes
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

/* Color palettes */
export const FLOOR_COLORS = ['#9E7E56', '#A08558', '#96794E', '#A88D60'];
export const FLOOR_GRAIN = '#7A6040';
export const FLOOR_KNOT = '#6A5030';
export const FLOOR_BORDER = '#6E5538';

export const WALL_COLORS = ['#B5A08A', '#B0988A', '#B8A490', '#AA9880'];
export const MORTAR = '#C8BEB0';
export const BRICK_HI = 'rgba(255,255,255,0.15)';
export const BRICK_SH = 'rgba(0,0,0,0.12)';
export const WALL_CAP = '#5A4A3A';
export const WAINSCOT_BASE = '#6B5030';
export const WAINSCOT_HI = '#8A6840';
export const WAINSCOT_BEVEL_L = '#9A7850';
export const WAINSCOT_BEVEL_D = '#4A3820';
export const BASEBOARD = '#3E2E1E';
