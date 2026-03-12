/**
 * Floor and wall tile renderers — Stardew Valley cozy cabin style
 */

import { MAP_ROWS, WALL_ROWS } from '../sprite-config';
import {
  T,
  rand,
  fillCircle,
  FLOOR_COLORS,
  FLOOR_GRAIN,
  FLOOR_KNOT,
  FLOOR_BORDER,
  WALL_COLORS,
  BRICK_HI,
  BRICK_SH,
  WALL_CAP,
  WAINSCOT_BASE,
  WAINSCOT_HI,
  WAINSCOT_BEVEL_L,
  WAINSCOT_BEVEL_D,
  BASEBOARD,
} from './tile-utils';

export function drawFloorTile(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  row: number,
  col: number,
) {
  // Warm honey wood plank base
  const ci = Math.floor(rand(col, row) * FLOOR_COLORS.length);
  ctx.fillStyle = FLOOR_COLORS[ci];
  ctx.fillRect(x, y, T, T);

  // Warm ambient glow
  if (rand(col, row, 1) > 0.4) {
    ctx.fillStyle = 'rgba(255,220,160,0.06)';
    ctx.fillRect(x, y, T, T);
  }

  // Wood grain lines (wavy, warm)
  ctx.strokeStyle = FLOOR_GRAIN;
  ctx.lineWidth = 0.5;
  const grainCount = 4 + Math.floor(rand(col, row, 2) * 3);
  for (let i = 0; i < grainCount; i++) {
    const gy = y + 3 + (i * (T - 6)) / grainCount + rand(col, row, i + 10) * 3;
    ctx.globalAlpha = 0.2 + rand(col, row, i + 20) * 0.15;
    ctx.beginPath();
    ctx.moveTo(x + 1, gy);
    const mid = x + T / 2;
    const wave = (rand(col, row, i + 30) - 0.5) * 2;
    ctx.quadraticCurveTo(mid, gy + wave, x + T - 1, gy + wave * 0.5);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  // Plank border (subtle warm tone)
  ctx.fillStyle = FLOOR_BORDER;
  ctx.globalAlpha = 0.4;
  ctx.fillRect(x, y + T - 1, T, 1);
  ctx.fillRect(x + T - 1, y, 1, T);
  ctx.globalAlpha = 1;

  // Occasional wood knot
  if (rand(col, row, 5) > 0.82) {
    const kx = x + 8 + Math.floor(rand(col, row, 6) * (T - 16));
    const ky = y + 8 + Math.floor(rand(col, row, 7) * (T - 16));
    ctx.fillStyle = FLOOR_KNOT;
    ctx.globalAlpha = 0.4;
    fillCircle(ctx, kx, ky, 2);
    ctx.globalAlpha = 0.2;
    fillCircle(ctx, kx, ky, 3.5);
    ctx.globalAlpha = 1;
  }

  // Wall-to-floor shadow gradient (warm shadow)
  if (row === WALL_ROWS) {
    for (let s = 0; s < 8; s++) {
      ctx.fillStyle = `rgba(40,25,10,${0.15 * (1 - s / 8)})`;
      ctx.fillRect(x, y + s, T, 1);
    }
  }
  // Bottom row subtle darken
  if (row === MAP_ROWS - 1) {
    ctx.fillStyle = 'rgba(30,20,5,0.04)';
    ctx.fillRect(x, y, T, T);
  }
}

export function drawWallTile(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  row: number,
  col: number,
) {
  // Horizontal wood plank wall (Stardew cabin style, not brick)
  ctx.fillStyle = '#7A6548';
  ctx.fillRect(x, y, T, T);

  const plankH = 8;
  for (let py = 0; py < T; py += plankH) {
    const plankRow = Math.floor(py / plankH);
    const ci = Math.floor(rand(col, plankRow, 50) * WALL_COLORS.length);
    ctx.fillStyle = WALL_COLORS[ci];
    ctx.fillRect(x, y + py, T, plankH);

    // Plank highlight (top edge)
    ctx.fillStyle = BRICK_HI;
    ctx.fillRect(x, y + py, T, 1);

    // Plank shadow (bottom edge)
    ctx.fillStyle = BRICK_SH;
    ctx.fillRect(x, y + py + plankH - 1, T, 1);

    // Wood grain on planks
    ctx.strokeStyle = 'rgba(60,40,20,0.12)';
    ctx.lineWidth = 0.5;
    const grains = 2 + Math.floor(rand(col, plankRow, 55) * 2);
    for (let g = 0; g < grains; g++) {
      const gy = y + py + 2 + g * (plankH - 4) / grains + rand(col, plankRow, g + 60) * 2;
      ctx.globalAlpha = 0.4;
      ctx.beginPath();
      ctx.moveTo(x, gy);
      ctx.lineTo(x + T, gy + (rand(col, plankRow, g + 70) - 0.5) * 1.5);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // Occasional nail/peg
    if (rand(col, plankRow, 80) > 0.85) {
      const nx = x + 4 + Math.floor(rand(col, plankRow, 81) * (T - 8));
      const ny = y + py + plankH / 2;
      ctx.fillStyle = '#555040';
      fillCircle(ctx, nx, ny, 1);
      ctx.fillStyle = 'rgba(255,240,200,0.3)';
      fillCircle(ctx, nx - 0.3, ny - 0.3, 0.5);
    }
  }

  // Top cap (dark beam)
  if (row === 0) {
    ctx.fillStyle = WALL_CAP;
    ctx.fillRect(x, y, T, 4);
    ctx.fillStyle = 'rgba(255,220,160,0.1)';
    ctx.fillRect(x, y, T, 1);
  }

  // Wainscoting (bottom of wall)
  if (row === WALL_ROWS - 1) {
    const wy = y + T - 14;
    ctx.fillStyle = WAINSCOT_BASE;
    ctx.fillRect(x, wy, T, 14);
    ctx.fillStyle = WALL_CAP;
    ctx.fillRect(x, wy, T, 2);
    ctx.fillStyle = 'rgba(255,220,160,0.12)';
    ctx.fillRect(x, wy, T, 1);

    const panelW = T - 4;
    const px = x + 2;
    const panelY = wy + 3;
    const panelHt = 8;
    ctx.fillStyle = WAINSCOT_BEVEL_L;
    ctx.fillRect(px, panelY, panelW, 1);
    ctx.fillRect(px, panelY, 1, panelHt);
    ctx.fillStyle = WAINSCOT_BEVEL_D;
    ctx.fillRect(px, panelY + panelHt - 1, panelW, 1);
    ctx.fillRect(px + panelW - 1, panelY, 1, panelHt);
    ctx.fillStyle = WAINSCOT_HI;
    ctx.fillRect(px + 1, panelY + 1, panelW - 2, panelHt - 2);

    ctx.fillStyle = BASEBOARD;
    ctx.fillRect(x, y + T - 3, T, 3);
    ctx.fillStyle = 'rgba(255,220,160,0.06)';
    ctx.fillRect(x, y + T - 3, T, 1);
  }
}
