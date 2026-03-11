/**
 * Floor cable rendering between desks
 */

import { T } from './tile-utils';

export function drawFloorCables(ctx: CanvasRenderingContext2D) {
  ctx.save();
  ctx.strokeStyle = '#333';
  ctx.lineWidth = 2;
  ctx.globalAlpha = 0.5;
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

  ctx.strokeStyle = '#2A2A2A';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(20 * T, 11 * T);
  ctx.quadraticCurveTo(22 * T, 9 * T, 23 * T, 7 * T);
  ctx.stroke();

  ctx.restore();
}
