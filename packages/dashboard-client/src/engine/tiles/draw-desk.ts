/**
 * Desk furniture renderer — L-shape desk, monitor, keyboard, mouse, coffee, papers, chair
 */

import { T, hash, fillCircle } from './tile-utils';

export function drawDesk(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  // ---- Office chair (BEHIND desk) ----
  const chairX = x + pw / 2;
  const chairY = y + ph + 2;

  // 5-star wheel base
  ctx.fillStyle = '#2A2A2A';
  for (let i = 0; i < 5; i++) {
    const angle = (i * Math.PI * 2) / 5 - Math.PI / 2;
    const wx = chairX + Math.cos(angle) * 7;
    const wy = chairY + 14 + Math.sin(angle) * 4;
    fillCircle(ctx, wx, wy, 1.5);
    ctx.beginPath();
    ctx.moveTo(chairX, chairY + 12);
    ctx.lineTo(wx, wy);
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  // Central pole
  ctx.fillStyle = '#444';
  ctx.fillRect(chairX - 1, chairY + 4, 2, 10);

  // Chair seat
  ctx.fillStyle = '#3A3A44';
  ctx.fillRect(chairX - 8, chairY + 2, 16, 6);
  ctx.fillStyle = '#4A4A55';
  ctx.fillRect(chairX - 7, chairY + 3, 14, 4);

  // Armrests
  ctx.fillStyle = '#333';
  ctx.fillRect(chairX - 9, chairY, 2, 6);
  ctx.fillRect(chairX + 7, chairY, 2, 6);

  // Chair back
  ctx.fillStyle = '#3A3A44';
  ctx.fillRect(chairX - 7, chairY - 10, 14, 12);
  ctx.fillStyle = '#4A4A55';
  ctx.fillRect(chairX - 6, chairY - 9, 12, 10);
  ctx.strokeStyle = '#3A3A44';
  ctx.lineWidth = 0.5;
  for (let i = 0; i < 4; i++) {
    ctx.beginPath();
    ctx.moveTo(chairX - 5, chairY - 8 + i * 3);
    ctx.lineTo(chairX + 5, chairY - 8 + i * 3);
    ctx.stroke();
  }

  // ---- Desk surface ----
  ctx.fillStyle = 'rgba(0,0,0,0.12)';
  ctx.fillRect(x + 4, y + ph, pw - 4, 3);

  ctx.fillStyle = '#5A3318';
  ctx.fillRect(x + 2, y + 6, pw - 4, ph - 6);
  ctx.fillStyle = '#6B4226';
  ctx.fillRect(x + 3, y + 7, pw - 6, ph - 8);

  ctx.strokeStyle = '#5A3820';
  ctx.lineWidth = 0.5;
  ctx.globalAlpha = 0.3;
  for (let i = 0; i < 6; i++) {
    const gy = y + 10 + i * ((ph - 14) / 6);
    ctx.beginPath();
    ctx.moveTo(x + 4, gy);
    ctx.lineTo(x + pw - 4, gy);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  ctx.fillStyle = '#8B6240';
  ctx.fillRect(x + 2, y + 6, pw - 4, 3);
  ctx.fillStyle = '#3E2210';
  ctx.fillRect(x + 2, y + ph - 3, pw - 4, 3);
  ctx.fillStyle = '#4A2A16';
  ctx.fillRect(x + pw - 4, y + 6, 2, ph - 6);

  // Desk legs
  ctx.fillStyle = '#3E2210';
  ctx.fillRect(x + 4, y + ph - 2, 4, 6);
  ctx.fillRect(x + pw - 8, y + ph - 2, 4, 6);
  ctx.fillStyle = '#5A3A1A';
  ctx.fillRect(x + 4, y + ph - 2, 1, 6);
  ctx.fillRect(x + pw - 8, y + ph - 2, 1, 6);

  // ---- Monitor ----
  const monW = 24;
  const monH = 18;
  const monX = x + pw / 2 - monW / 2;
  const monY = y + 8;

  ctx.fillStyle = '#1A1A1A';
  ctx.fillRect(monX - 2, monY - 2, monW + 4, monH + 4);
  ctx.fillStyle = '#0D1117';
  ctx.fillRect(monX, monY, monW, monH);
  const codeColors = ['#44CC44', '#61DAFB', '#FFD700', '#FF7B72', '#D2A8FF'];
  for (let i = 0; i < 5; i++) {
    ctx.fillStyle = codeColors[i];
    const lineW = 6 + Math.floor((hash(w, i) & 0xf) % 12);
    const indent = (i === 1 || i === 3) ? 4 : 2;
    ctx.fillRect(monX + indent, monY + 2 + i * 3, Math.min(lineW, monW - indent - 2), 1.5);
  }
  ctx.fillStyle = 'rgba(100,200,255,0.03)';
  ctx.fillRect(monX, monY, monW, monH);

  // Monitor stand
  ctx.fillStyle = '#333';
  ctx.fillRect(monX + monW / 2 - 2, monY + monH + 2, 4, 4);
  ctx.fillStyle = '#2A2A2A';
  ctx.fillRect(monX + monW / 2 - 6, monY + monH + 5, 12, 2);
  ctx.fillStyle = '#444';
  ctx.fillRect(monX + monW / 2 - 6, monY + monH + 5, 12, 1);

  // ---- Keyboard ----
  const kbX = monX + 1;
  const kbY = monY + monH + 10;
  ctx.fillStyle = '#2A2A2A';
  ctx.fillRect(kbX, kbY, 20, 8);
  ctx.fillStyle = '#3A3A3A';
  ctx.fillRect(kbX + 1, kbY + 1, 18, 6);
  ctx.fillStyle = '#4A4A4A';
  for (let kr = 0; kr < 3; kr++) {
    for (let kc = 0; kc < 6; kc++) {
      ctx.fillRect(kbX + 2 + kc * 3, kbY + 1.5 + kr * 2, 2, 1.5);
    }
  }

  // ---- Mouse + mousepad ----
  const mouseX = monX + monW + 2;
  const mouseY = kbY + 1;
  ctx.fillStyle = '#2A2A3A';
  ctx.fillRect(mouseX - 1, mouseY - 1, 10, 10);
  ctx.fillStyle = '#444';
  ctx.fillRect(mouseX + 2, mouseY + 2, 4, 6);
  ctx.fillStyle = '#555';
  ctx.fillRect(mouseX + 2, mouseY + 2, 4, 2);
  ctx.fillStyle = '#333';
  ctx.fillRect(mouseX + 3.5, mouseY + 2, 1, 3);

  // ---- Coffee cup ----
  const cupX = x + 6;
  const cupY = y + 14;
  ctx.fillStyle = '#DDD';
  ctx.fillRect(cupX - 1, cupY + 6, 10, 2);
  ctx.fillStyle = '#F0F0F0';
  ctx.fillRect(cupX, cupY, 8, 7);
  ctx.fillStyle = '#E0E0E0';
  ctx.fillRect(cupX + 1, cupY, 6, 1);
  ctx.fillStyle = '#5C3317';
  ctx.fillRect(cupX + 1, cupY + 1, 6, 3);
  ctx.fillStyle = '#E8E8E8';
  ctx.fillRect(cupX + 8, cupY + 2, 2, 4);
  ctx.fillRect(cupX + 9, cupY + 1, 1, 1);
  ctx.fillRect(cupX + 9, cupY + 5, 1, 1);
  ctx.globalAlpha = 0.25;
  ctx.fillStyle = '#DDD';
  ctx.fillRect(cupX + 2, cupY - 3, 1, 2);
  ctx.fillRect(cupX + 4, cupY - 4, 1, 3);
  ctx.fillRect(cupX + 6, cupY - 2, 1, 2);
  ctx.globalAlpha = 1;

  // ---- Papers ----
  const papX = x + pw - 18;
  const papY = y + 12;
  ctx.fillStyle = '#F8F8F0';
  ctx.fillRect(papX, papY, 12, 14);
  ctx.fillStyle = '#CCC';
  for (let i = 0; i < 4; i++) {
    ctx.fillRect(papX + 2, papY + 2 + i * 3, 8, 1);
  }
  ctx.fillStyle = '#FFF8E8';
  ctx.fillRect(papX + 3, papY + 2, 10, 12);
  ctx.fillStyle = '#BBB';
  for (let i = 0; i < 3; i++) {
    ctx.fillRect(papX + 5, papY + 4 + i * 3, 6, 1);
  }
}
