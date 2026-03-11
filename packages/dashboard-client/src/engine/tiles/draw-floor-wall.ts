/**
 * Floor and wall tile renderers
 */

import { MAP_ROWS, WALL_ROWS } from '../sprite-config';
import {
  T, rand, fillCircle,
  FLOOR_COLORS, FLOOR_GRAIN, FLOOR_KNOT, FLOOR_BORDER,
  WALL_COLORS, MORTAR, BRICK_HI, BRICK_SH, WALL_CAP,
  WAINSCOT_BASE, WAINSCOT_HI, WAINSCOT_BEVEL_L, WAINSCOT_BEVEL_D, BASEBOARD,
} from './tile-utils';

export function drawFloorTile(ctx: CanvasRenderingContext2D, x: number, y: number, row: number, col: number) {
  const ci = Math.floor(rand(col, row) * FLOOR_COLORS.length);
  ctx.fillStyle = FLOOR_COLORS[ci];
  ctx.fillRect(x, y, T, T);

  if (rand(col, row, 1) > 0.5) {
    ctx.fillStyle = 'rgba(255,240,200,0.06)';
    ctx.fillRect(x, y, T, T);
  }

  ctx.strokeStyle = FLOOR_GRAIN;
  ctx.lineWidth = 0.5;
  const grainCount = 4 + Math.floor(rand(col, row, 2) * 2);
  for (let i = 0; i < grainCount; i++) {
    const gy = y + 3 + (i * (T - 6)) / grainCount + rand(col, row, i + 10) * 3;
    ctx.globalAlpha = 0.25 + rand(col, row, i + 20) * 0.2;
    ctx.beginPath();
    ctx.moveTo(x + 1, gy);
    const mid = x + T / 2;
    const wave = (rand(col, row, i + 30) - 0.5) * 2;
    ctx.quadraticCurveTo(mid, gy + wave, x + T - 1, gy + wave * 0.5);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  ctx.fillStyle = FLOOR_BORDER;
  ctx.fillRect(x, y + T - 1, T, 1);
  ctx.globalAlpha = 0.5;
  ctx.fillRect(x + T - 1, y, 1, T);
  ctx.globalAlpha = 1;

  if (rand(col, row, 5) > 0.85) {
    const kx = x + 8 + Math.floor(rand(col, row, 6) * (T - 16));
    const ky = y + 8 + Math.floor(rand(col, row, 7) * (T - 16));
    ctx.fillStyle = FLOOR_KNOT;
    ctx.globalAlpha = 0.5;
    fillCircle(ctx, kx, ky, 2);
    ctx.globalAlpha = 0.3;
    fillCircle(ctx, kx, ky, 3.5);
    ctx.globalAlpha = 1;
  }

  if (row === WALL_ROWS) {
    for (let s = 0; s < 10; s++) {
      ctx.fillStyle = `rgba(0,0,0,${0.18 * (1 - s / 10)})`;
      ctx.fillRect(x, y + s, T, 1);
    }
  }
  if (row === MAP_ROWS - 1) {
    ctx.fillStyle = 'rgba(0,0,0,0.04)';
    ctx.fillRect(x, y, T, T);
  }
}

export function drawWallTile(ctx: CanvasRenderingContext2D, x: number, y: number, row: number, col: number) {
  ctx.fillStyle = '#B5A690';
  ctx.fillRect(x, y, T, T);

  const brickH = 8;
  const brickW = 16;

  for (let by = 0; by < T; by += brickH) {
    const brickRow = Math.floor(by / brickH);
    const offset = (brickRow + col) % 2 === 0 ? 0 : brickW / 2;

    for (let bx = -brickW; bx < T + brickW; bx += brickW) {
      const abx = bx + offset;
      const left = Math.max(0, abx);
      const right = Math.min(T, abx + brickW);
      if (left >= right) continue;

      const ci = Math.floor(rand(col * 4 + brickRow, Math.floor(abx / brickW), 50) * WALL_COLORS.length);
      ctx.fillStyle = WALL_COLORS[ci];
      ctx.fillRect(x + left, y + by, right - left, brickH);

      ctx.fillStyle = BRICK_HI;
      ctx.fillRect(x + left, y + by, right - left, 1);
      ctx.fillRect(x + left, y + by, 1, brickH);

      ctx.fillStyle = BRICK_SH;
      ctx.fillRect(x + left, y + by + brickH - 1, right - left, 1);
      ctx.fillRect(x + right - 1, y + by, 1, brickH);
    }

    ctx.fillStyle = MORTAR;
    ctx.globalAlpha = 0.6;
    ctx.fillRect(x, y + by, T, 1);
    ctx.globalAlpha = 1;
  }

  for (let by = 0; by < T; by += brickH) {
    const brickRow = Math.floor(by / brickH);
    const offset = (brickRow + col) % 2 === 0 ? 0 : brickW / 2;
    for (let bx = offset; bx < T; bx += brickW) {
      ctx.fillStyle = MORTAR;
      ctx.globalAlpha = 0.5;
      ctx.fillRect(x + bx, y + by, 1, brickH);
      ctx.globalAlpha = 1;
    }
  }

  if (row === 0) {
    ctx.fillStyle = WALL_CAP;
    ctx.fillRect(x, y, T, 4);
    ctx.fillStyle = 'rgba(255,255,255,0.1)';
    ctx.fillRect(x, y, T, 1);
  }

  if (row === WALL_ROWS - 1) {
    const wy = y + T - 14;
    ctx.fillStyle = WAINSCOT_BASE;
    ctx.fillRect(x, wy, T, 14);
    ctx.fillStyle = WALL_CAP;
    ctx.fillRect(x, wy, T, 2);
    ctx.fillStyle = 'rgba(255,255,255,0.15)';
    ctx.fillRect(x, wy, T, 1);

    const panelW = T - 4;
    const px = x + 2;
    const py = wy + 3;
    const panelH = 8;
    ctx.fillStyle = WAINSCOT_BEVEL_L;
    ctx.fillRect(px, py, panelW, 1);
    ctx.fillRect(px, py, 1, panelH);
    ctx.fillStyle = WAINSCOT_BEVEL_D;
    ctx.fillRect(px, py + panelH - 1, panelW, 1);
    ctx.fillRect(px + panelW - 1, py, 1, panelH);
    ctx.fillStyle = WAINSCOT_HI;
    ctx.fillRect(px + 1, py + 1, panelW - 2, panelH - 2);

    ctx.fillStyle = BASEBOARD;
    ctx.fillRect(x, y + T - 3, T, 3);
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    ctx.fillRect(x, y + T - 3, T, 1);
  }
}
