/**
 * Desk furniture renderer — Stardew Valley rustic wooden desk
 * Warm wood tones, handcrafted feel
 */

import { T, hash } from './tile-utils';

export function drawDesk(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  const pw = w * T;
  const ph = h * T;

  // ---- Wooden chair (rustic) ----
  const chairX = x + pw / 2;
  const chairY = y + ph + 2;

  // Chair legs (wooden)
  ctx.fillStyle = '#6B4A28';
  ctx.fillRect(chairX - 7, chairY + 10, 2, 6);
  ctx.fillRect(chairX + 5, chairY + 10, 2, 6);
  ctx.fillRect(chairX - 5, chairY + 12, 2, 4);
  ctx.fillRect(chairX + 3, chairY + 12, 2, 4);

  // Chair seat (warm wood)
  ctx.fillStyle = '#8B6840';
  ctx.fillRect(chairX - 8, chairY + 4, 16, 6);
  ctx.fillStyle = '#A07848';
  ctx.fillRect(chairX - 7, chairY + 5, 14, 4);
  // Seat highlight
  ctx.fillStyle = '#B08850';
  ctx.fillRect(chairX - 6, chairY + 5, 12, 1);

  // Chair back (wooden slats)
  ctx.fillStyle = '#7A5A30';
  ctx.fillRect(chairX - 7, chairY - 8, 14, 12);
  ctx.fillStyle = '#8B6840';
  // Two slats with gap
  ctx.fillRect(chairX - 6, chairY - 7, 5, 10);
  ctx.fillRect(chairX + 1, chairY - 7, 5, 10);
  // Top rail
  ctx.fillStyle = '#7A5A30';
  ctx.fillRect(chairX - 7, chairY - 8, 14, 2);
  ctx.fillStyle = '#9A7848';
  ctx.fillRect(chairX - 6, chairY - 8, 12, 1);

  // ---- Desk surface (warm rustic wood) ----
  // Shadow
  ctx.fillStyle = 'rgba(40,25,10,0.12)';
  ctx.fillRect(x + 4, y + ph, pw - 4, 3);

  // Main desk body
  ctx.fillStyle = '#7A5528';
  ctx.fillRect(x + 2, y + 6, pw - 4, ph - 6);
  ctx.fillStyle = '#8B6838';
  ctx.fillRect(x + 3, y + 7, pw - 6, ph - 8);

  // Wood grain texture
  ctx.strokeStyle = '#6A4820';
  ctx.lineWidth = 0.5;
  ctx.globalAlpha = 0.25;
  for (let i = 0; i < 6; i++) {
    const gy = y + 10 + i * ((ph - 14) / 6);
    ctx.beginPath();
    ctx.moveTo(x + 4, gy);
    ctx.lineTo(x + pw - 4, gy);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  // Desktop surface (top edge highlight)
  ctx.fillStyle = '#A07840';
  ctx.fillRect(x + 2, y + 6, pw - 4, 3);
  // Front edge shadow
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(x + 2, y + ph - 3, pw - 4, 3);
  // Right edge shadow
  ctx.fillStyle = '#6A4220';
  ctx.fillRect(x + pw - 4, y + 6, 2, ph - 6);

  // Desk legs (sturdy wooden)
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(x + 4, y + ph - 2, 4, 6);
  ctx.fillRect(x + pw - 8, y + ph - 2, 4, 6);
  ctx.fillStyle = '#7A5A2A';
  ctx.fillRect(x + 4, y + ph - 2, 1, 6);
  ctx.fillRect(x + pw - 8, y + ph - 2, 1, 6);

  // ---- Monitor (warm-framed) ----
  const monW = 24;
  const monH = 18;
  const monX = x + pw / 2 - monW / 2;
  const monY = y + 8;

  // Frame (warm dark wood)
  ctx.fillStyle = '#3A2A1A';
  ctx.fillRect(monX - 2, monY - 2, monW + 4, monH + 4);
  // Screen
  ctx.fillStyle = '#0D1117';
  ctx.fillRect(monX, monY, monW, monH);
  // Code lines (warm-toned)
  const codeColors = ['#7CC46A', '#5CE0D0', '#FFD54F', '#FF8C55', '#D4A0FF'];
  for (let i = 0; i < 5; i++) {
    ctx.fillStyle = codeColors[i];
    const lineW = 6 + Math.floor((hash(w, i) & 0xf) % 12);
    const indent = i === 1 || i === 3 ? 4 : 2;
    ctx.fillRect(monX + indent, monY + 2 + i * 3, Math.min(lineW, monW - indent - 2), 1.5);
  }
  // Screen glow
  ctx.fillStyle = 'rgba(100,200,160,0.03)';
  ctx.fillRect(monX, monY, monW, monH);

  // Monitor stand (wood)
  ctx.fillStyle = '#4A3420';
  ctx.fillRect(monX + monW / 2 - 2, monY + monH + 2, 4, 4);
  ctx.fillRect(monX + monW / 2 - 6, monY + monH + 5, 12, 2);
  ctx.fillStyle = '#5A4428';
  ctx.fillRect(monX + monW / 2 - 6, monY + monH + 5, 12, 1);

  // ---- Keyboard ----
  const kbX = monX + 1;
  const kbY = monY + monH + 10;
  ctx.fillStyle = '#3A3028';
  ctx.fillRect(kbX, kbY, 20, 8);
  ctx.fillStyle = '#4A4038';
  ctx.fillRect(kbX + 1, kbY + 1, 18, 6);
  ctx.fillStyle = '#5A5048';
  for (let kr = 0; kr < 3; kr++) {
    for (let kc = 0; kc < 6; kc++) {
      ctx.fillRect(kbX + 2 + kc * 3, kbY + 1.5 + kr * 2, 2, 1.5);
    }
  }

  // ---- Mouse + mousepad ----
  const mouseX = monX + monW + 2;
  const mouseY = kbY + 1;
  ctx.fillStyle = '#3A3028';
  ctx.fillRect(mouseX - 1, mouseY - 1, 10, 10);
  ctx.fillStyle = '#5A5040';
  ctx.fillRect(mouseX + 2, mouseY + 2, 4, 6);
  ctx.fillStyle = '#6A6050';
  ctx.fillRect(mouseX + 2, mouseY + 2, 4, 2);
  ctx.fillStyle = '#4A4030';
  ctx.fillRect(mouseX + 3.5, mouseY + 2, 1, 3);

  // ---- Coffee mug (ceramic, warm) ----
  const cupX = x + 6;
  const cupY = y + 14;
  // Saucer
  ctx.fillStyle = '#E8D8C0';
  ctx.fillRect(cupX - 1, cupY + 6, 10, 2);
  // Cup body
  ctx.fillStyle = '#E0C8A0';
  ctx.fillRect(cupX, cupY, 8, 7);
  ctx.fillStyle = '#D4B888';
  ctx.fillRect(cupX + 1, cupY, 6, 1);
  // Coffee inside
  ctx.fillStyle = '#6B3A18';
  ctx.fillRect(cupX + 1, cupY + 1, 6, 3);
  // Handle
  ctx.fillStyle = '#D4B888';
  ctx.fillRect(cupX + 8, cupY + 2, 2, 4);
  ctx.fillRect(cupX + 9, cupY + 1, 1, 1);
  ctx.fillRect(cupX + 9, cupY + 5, 1, 1);
  // Steam wisps (warm)
  ctx.globalAlpha = 0.2;
  ctx.fillStyle = '#F0E0C0';
  ctx.fillRect(cupX + 2, cupY - 3, 1, 2);
  ctx.fillRect(cupX + 4, cupY - 4, 1, 3);
  ctx.fillRect(cupX + 6, cupY - 2, 1, 2);
  ctx.globalAlpha = 1;

  // ---- Papers (parchment colored) ----
  const papX = x + pw - 18;
  const papY = y + 12;
  ctx.fillStyle = '#F5ECD8';
  ctx.fillRect(papX, papY, 12, 14);
  ctx.fillStyle = '#C8B898';
  for (let i = 0; i < 4; i++) {
    ctx.fillRect(papX + 2, papY + 2 + i * 3, 8, 1);
  }
  ctx.fillStyle = '#FAF0E0';
  ctx.fillRect(papX + 3, papY + 2, 10, 12);
  ctx.fillStyle = '#B8A888';
  for (let i = 0; i < 3; i++) {
    ctx.fillRect(papX + 5, papY + 4 + i * 3, 6, 1);
  }
}
