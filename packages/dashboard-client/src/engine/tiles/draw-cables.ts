/**
 * Floor detail rendering — vine-like cable paths between desks (Stardew style)
 */

import { T, fillCircle } from './tile-utils';

export function drawFloorCables(ctx: CanvasRenderingContext2D) {
  ctx.save();
  // Warm-toned cables that look like worn paths / vines
  ctx.strokeStyle = '#8A7A5A';
  ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.35;
  ctx.lineCap = 'round';

  ctx.beginPath();
  ctx.moveTo(3 * T + 10, 10 * T);
  ctx.quadraticCurveTo(2 * T, 7 * T, 1 * T, 5 * T);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(9 * T, 11 * T);
  ctx.quadraticCurveTo(12 * T, 11.5 * T, 15 * T + 10, 10 * T);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(12 * T + 10, 7 * T);
  ctx.quadraticCurveTo(11 * T, 5.5 * T, 10 * T, 5 * T);
  ctx.stroke();

  ctx.strokeStyle = '#7A6A4A';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(20 * T, 11 * T);
  ctx.quadraticCurveTo(22 * T, 9 * T, 23 * T, 7 * T);
  ctx.stroke();

  // Small leaf accents along paths
  ctx.globalAlpha = 0.25;
  ctx.fillStyle = '#6A8A4A';
  fillCircle(ctx, 2.5 * T, 8 * T, 1.5);
  fillCircle(ctx, 11 * T, 11.2 * T, 1.5);
  fillCircle(ctx, 21 * T, 10 * T, 1.5);

  ctx.restore();
}
