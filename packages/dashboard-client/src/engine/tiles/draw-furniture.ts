/**
 * All furniture renderers except desk:
 * sofa, bookshelf, whiteboard, arcade, fridge, coffee machine,
 * plant, plant-small, cabinet, rug, window, poster, cooler
 */

import { T, rand, fillCircle } from './tile-utils';

/* ================================================================
   SOFA
   ================================================================ */
export function drawSofa(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  ctx.fillStyle = 'rgba(0,0,0,0.1)';
  ctx.fillRect(x + 6, y + ph - 2, pw - 8, 4);
  ctx.fillStyle = '#5A3A1A';
  ctx.fillRect(x + 6, y + ph - 3, 4, 4);
  ctx.fillRect(x + pw - 10, y + ph - 3, 4, 4);

  ctx.fillStyle = '#7A2828';
  ctx.fillRect(x + 4, y, pw - 8, 14);
  ctx.fillStyle = '#6A1E1E';
  ctx.fillRect(x + 4, y, pw - 8, 2);
  ctx.fillStyle = '#8A3232';
  ctx.fillRect(x + 6, y + 3, pw - 12, 9);

  ctx.fillStyle = '#8B3232';
  ctx.fillRect(x + 2, y + 12, pw - 4, ph - 14);

  ctx.fillStyle = '#7A2828';
  ctx.fillRect(x, y + 4, 8, ph - 6);
  ctx.fillRect(x + pw - 8, y + 4, 8, ph - 6);
  ctx.fillStyle = '#9A4040';
  ctx.fillRect(x + 1, y + 5, 6, 2);
  ctx.fillRect(x + pw - 7, y + 5, 6, 2);
  ctx.fillStyle = '#6A2020';
  ctx.fillRect(x + 6, y + 6, 2, ph - 10);
  ctx.fillRect(x + pw - 8, y + 6, 2, ph - 10);

  const cushionW = Math.floor((pw - 20) / 3);
  for (let i = 0; i < 3; i++) {
    const cx = x + 10 + i * cushionW;
    const cy = y + 14;
    const cw = cushionW - 2;
    const ch = ph - 20;
    ctx.fillStyle = '#A04545';
    ctx.fillRect(cx, cy, cw, ch);
    ctx.fillStyle = '#B85555';
    ctx.fillRect(cx + 1, cy, cw - 2, 3);
    ctx.fillStyle = '#883030';
    ctx.fillRect(cx + 1, cy + ch - 2, cw - 2, 2);
    ctx.strokeStyle = '#8A3535';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(cx + 2, cy + ch / 2);
    ctx.lineTo(cx + cw - 2, cy + ch / 2);
    ctx.stroke();
  }

  const pillowX = x + 12;
  const pillowY = y + 14;
  ctx.fillStyle = '#E8C85A';
  ctx.fillRect(pillowX, pillowY, 10, 10);
  ctx.fillStyle = '#D4B440';
  ctx.fillRect(pillowX + 1, pillowY + 1, 8, 8);
  ctx.fillStyle = '#F0D868';
  ctx.fillRect(pillowX + 2, pillowY + 2, 3, 3);
  ctx.fillStyle = '#F8E080';
  ctx.fillRect(pillowX, pillowY, 10, 1);
}

/* ================================================================
   BOOKSHELF
   ================================================================ */
export function drawBookshelf(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  ctx.fillStyle = 'rgba(0,0,0,0.15)';
  ctx.fillRect(x + 3, y + 3, pw, ph);
  ctx.fillStyle = '#4A2A10';
  ctx.fillRect(x, y, pw, ph);
  ctx.fillStyle = '#6A4A2A';
  ctx.fillRect(x + 3, y + 3, pw - 6, ph - 6);

  const shelfCount = 4;
  const shelfH = Math.floor((ph - 6) / shelfCount);

  const bookColors = [
    '#CC3333', '#3366CC', '#33AA33', '#CC9900', '#9933CC',
    '#CC6633', '#339999', '#AA3366', '#668833', '#3355AA',
    '#DD7722', '#5544AA', '#228877', '#BB4455',
  ];

  for (let shelf = 0; shelf < shelfCount; shelf++) {
    const sy = y + 3 + shelf * shelfH;
    ctx.fillStyle = '#5A3A1A';
    ctx.fillRect(x + 3, sy + shelfH - 3, pw - 6, 3);
    ctx.fillStyle = '#7A5A3A';
    ctx.fillRect(x + 3, sy + shelfH - 3, pw - 6, 1);

    let bx = x + 5;
    const maxBx = x + pw - 5;
    const bookBase = sy + 2;
    const maxBookH = shelfH - 6;
    let bookIdx = shelf * 7 + 1;

    while (bx < maxBx - 3) {
      const bw = 3 + Math.floor(rand(bookIdx, shelf, 80) * 4);
      const bh = maxBookH - Math.floor(rand(bookIdx, shelf, 81) * 4);
      const color = bookColors[bookIdx % bookColors.length];
      const lean = rand(bookIdx, shelf, 82) > 0.85;

      if (bx + bw > maxBx) break;

      ctx.save();
      if (lean) {
        ctx.translate(bx + bw / 2, bookBase + bh);
        ctx.rotate(-0.08);
        ctx.translate(-(bx + bw / 2), -(bookBase + bh));
      }

      ctx.fillStyle = color;
      ctx.fillRect(bx, bookBase + (maxBookH - bh), bw, bh);
      ctx.fillStyle = 'rgba(255,255,255,0.2)';
      ctx.fillRect(bx, bookBase + (maxBookH - bh), 1, bh);
      ctx.fillStyle = 'rgba(0,0,0,0.2)';
      ctx.fillRect(bx + bw - 1, bookBase + (maxBookH - bh), 1, bh);

      if (bh > 8) {
        ctx.fillStyle = 'rgba(255,255,200,0.5)';
        ctx.fillRect(bx + 1, bookBase + (maxBookH - bh) + Math.floor(bh * 0.3), bw - 2, 1);
      }

      ctx.restore();
      bx += bw + 1;
      bookIdx++;
    }
  }

  // Globe decoration
  const globeX = x + pw - 14;
  const globeY = y + 6;
  ctx.fillStyle = '#5588AA';
  fillCircle(ctx, globeX, globeY + 4, 4);
  ctx.fillStyle = '#44AA44';
  ctx.fillRect(globeX - 2, globeY + 2, 3, 3);
  ctx.fillStyle = '#8B6840';
  ctx.fillRect(globeX - 1, globeY + 8, 2, 3);
  ctx.fillRect(globeX - 3, globeY + 10, 6, 1);

  // Frame edges (bevel)
  ctx.fillStyle = '#5A3818';
  ctx.fillRect(x, y, pw, 2);
  ctx.fillRect(x, y, 3, ph);
  ctx.fillStyle = '#3A2008';
  ctx.fillRect(x, y + ph - 3, pw, 3);
  ctx.fillRect(x + pw - 3, y, 3, ph);
}

/* ================================================================
   WHITEBOARD
   ================================================================ */
export function drawWhiteboard(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  ctx.fillStyle = '#888890';
  ctx.fillRect(x - 1, y - 1, pw + 2, ph + 2);
  ctx.fillStyle = '#A0A0A8';
  ctx.fillRect(x - 1, y - 1, pw + 2, 2);
  ctx.fillRect(x - 1, y - 1, 2, ph + 2);
  ctx.fillStyle = '#606068';
  ctx.fillRect(x - 1, y + ph - 1, pw + 2, 2);
  ctx.fillRect(x + pw - 1, y - 1, 2, ph + 2);

  ctx.fillStyle = '#F5F5EC';
  ctx.fillRect(x + 3, y + 3, pw - 6, ph - 6);

  ctx.fillStyle = '#333';
  ctx.font = 'bold 5px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('DEV FLOW', x + pw / 2, y + 10);

  const cols = 5;
  const colW = (pw - 10) / cols;
  ctx.strokeStyle = '#CCCCBB';
  ctx.lineWidth = 0.5;
  for (let i = 1; i < cols; i++) {
    const lx = x + 5 + i * colW;
    ctx.beginPath();
    ctx.moveTo(lx, y + 13);
    ctx.lineTo(lx, y + ph - 8);
    ctx.stroke();
  }

  const headerColors = ['#E74C3C', '#F5A623', '#4A90D9', '#9B59B6', '#2ECC71'];
  const headerLabels = ['TODO', 'WIP', 'TEST', 'REV', 'DONE'];
  for (let i = 0; i < cols; i++) {
    const hx = x + 6 + i * colW;
    ctx.fillStyle = headerColors[i];
    ctx.fillRect(hx, y + 13, colW - 3, 5);
    ctx.fillStyle = '#FFF';
    ctx.font = '3px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(headerLabels[i], hx + (colW - 3) / 2, y + 17);
  }

  const cardColors = ['#FFE0E0', '#E0F0FF', '#E0FFE0', '#FFF0D0', '#F0E0FF'];
  for (let i = 0; i < cols; i++) {
    const numCards = 2 + Math.floor(rand(i, 0, 99) * 3);
    for (let c = 0; c < numCards; c++) {
      const cx = x + 7 + i * colW;
      const cy = y + 21 + c * 8;
      if (cy + 6 > y + ph - 10) break;
      ctx.fillStyle = cardColors[(i + c) % cardColors.length];
      ctx.fillRect(cx, cy, colW - 5, 6);
      ctx.fillStyle = '#999';
      ctx.fillRect(cx + 1, cy + 2, colW - 9, 1);
      ctx.fillRect(cx + 1, cy + 4, (colW - 9) * 0.6, 0.5);
    }
  }

  ctx.strokeStyle = '#888';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x + pw / 2 - 20, y + ph - 16);
  ctx.lineTo(x + pw / 2 + 20, y + ph - 16);
  ctx.stroke();
  ctx.fillStyle = '#888';
  ctx.beginPath();
  ctx.moveTo(x + pw / 2 + 20, y + ph - 16);
  ctx.lineTo(x + pw / 2 + 16, y + ph - 18);
  ctx.lineTo(x + pw / 2 + 16, y + ph - 14);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = '#777';
  ctx.fillRect(x + pw / 4, y + ph - 1, pw / 2, 4);
  ctx.fillStyle = '#888';
  ctx.fillRect(x + pw / 4, y + ph - 1, pw / 2, 1);

  const markerColors = ['#CC3333', '#3366CC', '#33AA33'];
  for (let i = 0; i < 3; i++) {
    ctx.fillStyle = markerColors[i];
    ctx.fillRect(x + pw / 4 + 4 + i * 14, y + ph, 10, 2);
    ctx.fillStyle = '#222';
    ctx.fillRect(x + pw / 4 + 4 + i * 14, y + ph, 2, 2);
  }

  ctx.textAlign = 'left';
}

/* ================================================================
   COFFEE MACHINE
   ================================================================ */
export function drawCoffeeMachine(ctx: CanvasRenderingContext2D, x: number, y: number) {
  ctx.fillStyle = '#6B4226';
  ctx.fillRect(x + 2, y + T - 2, T - 4, T + 2);
  ctx.fillStyle = '#8B6240';
  ctx.fillRect(x + 2, y + T - 2, T - 4, 2);
  ctx.fillStyle = '#4A2A10';
  ctx.fillRect(x + 2, y + T * 2 - 4, T - 4, 3);
  ctx.fillStyle = '#4A2A10';
  ctx.fillRect(x + 4, y + T * 2 - 2, 3, 4);
  ctx.fillRect(x + T - 7, y + T * 2 - 2, 3, 4);

  ctx.fillStyle = '#2A2A2A';
  ctx.fillRect(x + 5, y + 2, T - 10, T - 6);
  ctx.fillStyle = '#1A1A1A';
  ctx.fillRect(x + 7, y + 4, T - 14, 12);
  ctx.fillStyle = '#22AA22';
  ctx.fillRect(x + 8, y + 5, 8, 4);
  ctx.fillStyle = '#115511';
  ctx.fillRect(x + 9, y + 6, 6, 2);

  ctx.fillStyle = '#FF3333';
  fillCircle(ctx, x + 10, y + T - 7, 1.5);
  ctx.fillStyle = '#33FF33';
  fillCircle(ctx, x + 16, y + T - 7, 1.5);
  ctx.fillStyle = '#FFD700';
  fillCircle(ctx, x + 22, y + T - 7, 1.5);

  ctx.fillStyle = '#555';
  ctx.fillRect(x + 12, y + 16, 6, 3);

  ctx.fillStyle = '#DDD';
  ctx.fillRect(x + 8, y + T + 2, 10, 9);
  ctx.fillStyle = '#EEE';
  ctx.fillRect(x + 9, y + T + 2, 8, 2);
  ctx.fillStyle = '#5C3317';
  ctx.fillRect(x + 9, y + T + 4, 8, 4);

  ctx.globalAlpha = 0.2;
  ctx.fillStyle = '#FFF';
  ctx.fillRect(x + 10, y + T - 1, 1, 3);
  ctx.fillRect(x + 13, y + T - 2, 1, 4);
  ctx.fillRect(x + 16, y + T, 1, 2);
  ctx.globalAlpha = 1;

  ctx.fillStyle = '#AA8855';
  ctx.font = '3px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('COFFEE', x + T / 2, y + 22);
  ctx.textAlign = 'left';
}

/* ================================================================
   PLANT
   ================================================================ */
export function drawPlant(ctx: CanvasRenderingContext2D, x: number, y: number) {
  ctx.fillStyle = 'rgba(0,0,0,0.1)';
  fillCircle(ctx, x + T / 2, y + T * 2 - 4, 10);

  ctx.fillStyle = '#B8652A';
  ctx.fillRect(x + 7, y + T + 6, T - 14, T - 10);
  ctx.fillStyle = '#C87840';
  ctx.fillRect(x + 5, y + T + 2, T - 10, 5);
  ctx.fillStyle = '#D89050';
  ctx.fillRect(x + 5, y + T + 2, T - 10, 2);
  ctx.fillStyle = '#A05A20';
  ctx.fillRect(x + 8, y + T * 2 - 6, T - 16, 3);
  ctx.fillStyle = '#8A4A18';
  ctx.fillRect(x + 9, y + T + 14, T - 18, 2);

  ctx.fillStyle = '#3A2815';
  ctx.fillRect(x + 7, y + T + 4, T - 14, 4);
  ctx.fillStyle = '#4A3420';
  ctx.fillRect(x + 8, y + T + 4, T - 16, 2);

  ctx.fillStyle = '#2A6B1A';
  ctx.fillRect(x + 14, y + 10, 2, T - 4);

  const leaves: Array<[number, number, number, number, string]> = [
    [2, 4, 10, 8, '#228B22'],
    [T - 12, 6, 10, 7, '#228B22'],
    [6, 0, 12, 10, '#2EA82E'],
    [4, 8, 8, 6, '#1E7A1E'],
    [T - 10, 10, 8, 5, '#1E7A1E'],
    [8, 2, 8, 6, '#44BB44'],
    [10, -2, 10, 8, '#3AAA3A'],
  ];
  for (const [ox, oy, lw, lh, color] of leaves) {
    ctx.fillStyle = color;
    ctx.fillRect(x + ox + 1, y + oy, lw - 2, lh);
    ctx.fillRect(x + ox, y + oy + 1, lw, lh - 2);
  }

  ctx.strokeStyle = 'rgba(0,60,0,0.3)';
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  ctx.moveTo(x + 7, y + 8);
  ctx.lineTo(x + 12, y + 5);
  ctx.moveTo(x + T - 7, y + 10);
  ctx.lineTo(x + T - 12, y + 7);
  ctx.stroke();

  ctx.fillStyle = '#2EA82E';
  ctx.fillRect(x + 1, y + 12, 6, 4);
  ctx.fillRect(x + T - 7, y + 14, 6, 3);
}

/* ================================================================
   PLANT-SMALL
   ================================================================ */
export function drawPlantSmall(ctx: CanvasRenderingContext2D, x: number, y: number) {
  ctx.fillStyle = '#B8652A';
  ctx.fillRect(x + 10, y + 18, 12, 10);
  ctx.fillStyle = '#C87840';
  ctx.fillRect(x + 9, y + 16, 14, 4);
  ctx.fillStyle = '#D89050';
  ctx.fillRect(x + 9, y + 16, 14, 1);

  ctx.fillStyle = '#3A2815';
  ctx.fillRect(x + 10, y + 17, 12, 2);

  ctx.fillStyle = '#2A6B1A';
  ctx.fillRect(x + 15, y + 10, 2, 8);

  ctx.fillStyle = '#228B22';
  ctx.fillRect(x + 11, y + 8, 6, 5);
  ctx.fillStyle = '#2EA82E';
  ctx.fillRect(x + 15, y + 6, 6, 5);
  ctx.fillStyle = '#44BB44';
  ctx.fillRect(x + 12, y + 5, 5, 4);
  ctx.fillStyle = '#1E7A1E';
  ctx.fillRect(x + 17, y + 9, 4, 4);
}

/* ================================================================
   CABINET
   ================================================================ */
export function drawCabinet(ctx: CanvasRenderingContext2D, x: number, y: number) {
  const ph = T * 2;

  ctx.fillStyle = 'rgba(0,0,0,0.1)';
  ctx.fillRect(x + 4, y + ph - 1, T - 4, 3);

  ctx.fillStyle = '#6A6A78';
  ctx.fillRect(x + 2, y + 2, T - 4, ph - 4);
  ctx.fillStyle = '#7A7A88';
  ctx.fillRect(x + 2, y + 2, 2, ph - 4);
  ctx.fillStyle = '#5A5A68';
  ctx.fillRect(x + T - 4, y + 2, 2, ph - 4);
  ctx.fillStyle = '#7A7A88';
  ctx.fillRect(x + 2, y + 2, T - 4, 2);

  const drawerH = (ph - 10) / 3;
  for (let i = 0; i < 3; i++) {
    const dy = y + 5 + i * (drawerH + 1);
    ctx.fillStyle = '#7A7A8A';
    ctx.fillRect(x + 4, dy, T - 8, drawerH - 1);
    ctx.fillStyle = '#8A8A9A';
    ctx.fillRect(x + 4, dy, T - 8, 1);
    ctx.fillRect(x + 4, dy, 1, drawerH - 1);
    ctx.fillStyle = '#5A5A6A';
    ctx.fillRect(x + 4, dy + drawerH - 2, T - 8, 1);
    ctx.fillRect(x + T - 5, dy, 1, drawerH - 1);
    ctx.fillStyle = '#BBBBCC';
    ctx.fillRect(x + T / 2 - 5, dy + drawerH / 2 - 1, 10, 2);
    ctx.fillStyle = '#DDDDEE';
    ctx.fillRect(x + T / 2 - 5, dy + drawerH / 2 - 1, 10, 1);
    ctx.fillStyle = '#999';
    ctx.fillRect(x + T / 2 - 3, dy + 3, 6, 4);
    ctx.fillStyle = '#DDD';
    ctx.fillRect(x + T / 2 - 2, dy + 4, 4, 2);
  }
}

/* ================================================================
   RUG
   ================================================================ */
export function drawRug(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  ctx.fillStyle = '#7A2233';
  ctx.fillRect(x + 2, y + 2, pw - 4, ph - 4);

  ctx.strokeStyle = '#D4A840';
  ctx.lineWidth = 2;
  ctx.strokeRect(x + 4, y + 4, pw - 8, ph - 8);

  ctx.fillStyle = '#D4A840';
  const borderStep = 8;
  for (let bx = x + 8; bx < x + pw - 8; bx += borderStep) {
    ctx.fillRect(bx, y + 5, 3, 2);
    ctx.fillRect(bx, y + ph - 7, 3, 2);
  }
  for (let by = y + 8; by < y + ph - 8; by += borderStep) {
    ctx.fillRect(x + 5, by, 2, 3);
    ctx.fillRect(x + pw - 7, by, 2, 3);
  }

  ctx.strokeStyle = '#1A3355';
  ctx.lineWidth = 1.5;
  ctx.strokeRect(x + 10, y + 10, pw - 20, ph - 20);

  ctx.fillStyle = '#8B3040';
  ctx.fillRect(x + 12, y + 12, pw - 24, ph - 24);

  const cx = x + pw / 2;
  const cy = y + ph / 2;
  const dw = Math.min(pw - 40, 60);
  const dh = Math.min(ph - 30, 40);

  ctx.fillStyle = '#1A3355';
  ctx.beginPath();
  ctx.moveTo(cx, cy - dh / 2);
  ctx.lineTo(cx + dw / 2, cy);
  ctx.lineTo(cx, cy + dh / 2);
  ctx.lineTo(cx - dw / 2, cy);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = '#D4A840';
  ctx.beginPath();
  ctx.moveTo(cx, cy - dh / 2 + 4);
  ctx.lineTo(cx + dw / 2 - 4, cy);
  ctx.lineTo(cx, cy + dh / 2 - 4);
  ctx.lineTo(cx - dw / 2 + 4, cy);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = '#7A2233';
  ctx.beginPath();
  ctx.moveTo(cx, cy - dh / 2 + 8);
  ctx.lineTo(cx + dw / 2 - 10, cy);
  ctx.lineTo(cx, cy + dh / 2 - 8);
  ctx.lineTo(cx - dw / 2 + 10, cy);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = '#D4A840';
  fillCircle(ctx, cx, cy, 3);

  const corners = [
    [x + 18, y + 18],
    [x + pw - 18, y + 18],
    [x + 18, y + ph - 18],
    [x + pw - 18, y + ph - 18],
  ];
  for (const [dx, dy] of corners) {
    ctx.fillStyle = '#D4A840';
    ctx.beginPath();
    ctx.moveTo(dx, dy - 4);
    ctx.lineTo(dx + 4, dy);
    ctx.lineTo(dx, dy + 4);
    ctx.lineTo(dx - 4, dy);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = '#1A3355';
    fillCircle(ctx, dx, dy, 1.5);
  }

  ctx.fillStyle = '#D4A840';
  for (let fx = x + 6; fx < x + pw - 4; fx += 3) {
    ctx.fillRect(fx, y, 1, 3);
    ctx.fillRect(fx, y + ph - 3, 1, 3);
  }
}

/* ================================================================
   WINDOW
   ================================================================ */
export function drawWindow(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  ctx.fillStyle = '#8B6840';
  ctx.fillRect(x - 4, y - 3, pw + 8, 4);
  ctx.fillStyle = '#A88050';
  ctx.fillRect(x - 4, y - 3, pw + 8, 1);
  fillCircle(ctx, x - 3, y - 1, 2);
  fillCircle(ctx, x + pw + 3, y - 1, 2);

  const curtainW = 10;
  ctx.fillStyle = '#AA2222';
  ctx.fillRect(x - 2, y, curtainW, ph + 2);
  ctx.fillStyle = '#882020';
  ctx.fillRect(x, y, 2, ph + 2);
  ctx.fillRect(x + 4, y, 1, ph + 2);
  ctx.fillStyle = '#CC3838';
  ctx.fillRect(x + 2, y, 1, ph + 2);
  ctx.fillRect(x + 6, y, 1, ph + 2);
  ctx.fillStyle = '#AA2222';
  ctx.fillRect(x + pw - curtainW + 2, y, curtainW, ph + 2);
  ctx.fillStyle = '#882020';
  ctx.fillRect(x + pw - 4, y, 2, ph + 2);
  ctx.fillRect(x + pw - 7, y, 1, ph + 2);
  ctx.fillStyle = '#CC3838';
  ctx.fillRect(x + pw - 2, y, 1, ph + 2);
  ctx.fillRect(x + pw - 9, y, 1, ph + 2);

  ctx.fillStyle = '#4A2A10';
  ctx.fillRect(x + 6, y + 2, pw - 12, ph - 2);

  const glassX = x + 9;
  const glassY = y + 5;
  const glassW = pw - 18;
  const glassH = ph - 8;

  ctx.fillStyle = '#AAD8F0';
  ctx.fillRect(glassX, glassY, glassW, glassH);
  ctx.fillStyle = '#87CEEB';
  ctx.fillRect(glassX, glassY + glassH * 0.3, glassW, glassH * 0.7);
  ctx.fillStyle = '#70B8E0';
  ctx.fillRect(glassX, glassY + glassH * 0.7, glassW, glassH * 0.3);

  ctx.fillStyle = 'rgba(255,255,255,0.8)';
  fillCircle(ctx, glassX + 15, glassY + 8, 4);
  fillCircle(ctx, glassX + 20, glassY + 7, 5);
  fillCircle(ctx, glassX + 26, glassY + 8, 3);
  fillCircle(ctx, glassX + glassW - 20, glassY + 12, 3);
  fillCircle(ctx, glassX + glassW - 15, glassY + 11, 4);

  const skylineY = glassY + glassH - 18;
  ctx.fillStyle = '#556677';
  ctx.fillRect(glassX + 4, skylineY + 4, 10, 14);
  ctx.fillRect(glassX + 18, skylineY, 8, 18);
  ctx.fillRect(glassX + 30, skylineY + 6, 12, 12);
  ctx.fillRect(glassX + 46, skylineY + 2, 6, 16);
  ctx.fillStyle = '#445566';
  ctx.fillRect(glassX + 56, skylineY + 8, 14, 10);
  ctx.fillRect(glassX + 72, skylineY + 4, 8, 14);

  ctx.fillStyle = '#FFE866';
  ctx.globalAlpha = 0.7;
  const bldgs: Array<[number, number, number, number]> = [
    [glassX + 5, skylineY + 6, 8, 10],
    [glassX + 19, skylineY + 2, 6, 14],
    [glassX + 31, skylineY + 8, 10, 8],
    [glassX + 47, skylineY + 4, 4, 12],
  ];
  for (const [bx, by, bw, bh] of bldgs) {
    for (let wy = by + 2; wy < by + bh - 2; wy += 3) {
      for (let wx = bx + 1; wx < bx + bw - 1; wx += 3) {
        if (rand(wx, wy, 77) > 0.4) {
          ctx.fillRect(wx, wy, 1.5, 1.5);
        }
      }
    }
  }
  ctx.globalAlpha = 1;

  ctx.fillStyle = '#4A2A10';
  ctx.fillRect(glassX + glassW / 2 - 2, glassY, 3, glassH);
  ctx.fillRect(glassX, glassY + glassH / 2 - 1, glassW, 3);
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(glassX - 1, glassY, 1, glassH);
  ctx.fillRect(glassX + glassW, glassY, 1, glassH);
  ctx.fillRect(glassX, glassY - 1, glassW, 1);

  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(x + 4, y + ph - 1, pw - 8, 4);
  ctx.fillStyle = '#7A5A38';
  ctx.fillRect(x + 4, y + ph - 1, pw - 8, 1);

  ctx.fillStyle = 'rgba(255,255,255,0.06)';
  ctx.fillRect(glassX + 2, glassY + 2, glassW / 3, glassH - 4);
}

/* ================================================================
   POSTERS
   ================================================================ */
export function drawPoster(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, _h: number, type: string) {
  const pw = w * T;
  const ph = _h * T;

  ctx.fillStyle = 'rgba(0,0,0,0.2)';
  ctx.fillRect(x + 4, y + 3, pw - 4, ph - 2);

  if (type === 'poster-indie') {
    ctx.fillStyle = '#1A3A4A';
    ctx.fillRect(x + 2, y + 2, pw - 4, ph - 4);
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 1;
    ctx.strokeRect(x + 3, y + 3, pw - 6, ph - 6);
    ctx.fillStyle = '#61DAFB';
    ctx.font = 'bold 7px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('INDIE', x + pw / 2, y + 14);
    const cx = x + pw / 2;
    const cy = y + ph / 2 + 2;
    ctx.fillStyle = '#FFD700';
    ctx.fillRect(cx - 2, cy - 6, 4, 4);
    ctx.fillStyle = '#61DAFB';
    ctx.fillRect(cx - 3, cy - 2, 6, 6);
    ctx.fillStyle = '#444';
    ctx.fillRect(cx - 3, cy + 4, 2, 4);
    ctx.fillRect(cx + 1, cy + 4, 2, 4);
    ctx.fillStyle = '#FFF';
    ctx.font = 'bold 6px monospace';
    ctx.fillText('DEV', x + pw / 2, y + ph - 8);
  } else {
    ctx.fillStyle = '#4A1A4A';
    ctx.fillRect(x + 2, y + 2, pw - 4, ph - 4);
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 1;
    ctx.strokeRect(x + 3, y + 3, pw - 6, ph - 6);
    ctx.fillStyle = '#FF66CC';
    ctx.font = 'bold 7px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('GAME', x + pw / 2, y + 14);
    const cx = x + pw / 2;
    const cy = y + ph / 2 + 2;
    ctx.fillStyle = '#DDD';
    ctx.fillRect(cx - 7, cy - 3, 14, 6);
    ctx.fillRect(cx - 9, cy - 1, 3, 4);
    ctx.fillRect(cx + 6, cy - 1, 3, 4);
    ctx.fillStyle = '#333';
    ctx.fillRect(cx - 6, cy - 1, 3, 1);
    ctx.fillRect(cx - 5, cy - 2, 1, 3);
    ctx.fillStyle = '#FF4444';
    fillCircle(ctx, cx + 4, cy - 1, 1);
    ctx.fillStyle = '#44FF44';
    fillCircle(ctx, cx + 6, cy, 1);
    ctx.fillStyle = '#FFF';
    ctx.font = 'bold 6px monospace';
    ctx.fillText('JAM', x + pw / 2, y + ph - 8);
  }
  ctx.textAlign = 'left';
}

/* ================================================================
   COOLER
   ================================================================ */
export function drawCooler(ctx: CanvasRenderingContext2D, x: number, y: number) {
  const ph = T * 2;

  ctx.fillStyle = 'rgba(0,0,0,0.08)';
  ctx.fillRect(x + 7, y + ph - 2, T - 10, 4);

  ctx.fillStyle = '#D8D8E0';
  ctx.fillRect(x + 6, y + 14, T - 12, ph - 18);
  ctx.fillStyle = '#E8E8F0';
  ctx.fillRect(x + 6, y + 14, 2, ph - 18);
  ctx.fillStyle = '#C0C0C8';
  ctx.fillRect(x + T - 8, y + 14, 2, ph - 18);

  ctx.fillStyle = '#88BBEE';
  ctx.fillRect(x + 8, y + 2, T - 16, 14);
  ctx.fillStyle = '#AAD4FF';
  ctx.fillRect(x + 9, y + 3, 3, 10);
  ctx.fillStyle = '#77AADD';
  ctx.fillRect(x + 11, y, 8, 4);
  ctx.fillStyle = '#6699CC';
  ctx.fillRect(x + 9, y + 8, T - 18, 1);

  ctx.fillStyle = '#888';
  ctx.fillRect(x + 10, y + 20, 3, 4);
  ctx.fillRect(x + 17, y + 20, 3, 4);
  ctx.fillStyle = '#FF4444';
  fillCircle(ctx, x + 11.5, y + 21, 1.5);
  ctx.fillStyle = '#4488FF';
  fillCircle(ctx, x + 18.5, y + 21, 1.5);
  ctx.fillStyle = '#FFF';
  ctx.font = '2px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('H', x + 11.5, y + 22);
  ctx.fillText('C', x + 18.5, y + 22);
  ctx.textAlign = 'left';

  ctx.fillStyle = '#999';
  ctx.fillRect(x + 8, y + 26, T - 16, 3);
  ctx.fillStyle = '#AAA';
  ctx.fillRect(x + 8, y + 26, T - 16, 1);
}

/* ================================================================
   ARCADE MACHINE
   ================================================================ */
export function drawArcade(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  ctx.fillStyle = 'rgba(0,0,0,0.12)';
  ctx.fillRect(x + 4, y + ph - 2, pw - 4, 4);

  ctx.fillStyle = '#1A1A3A';
  ctx.fillRect(x + 4, y + 6, pw - 8, ph - 8);
  ctx.fillStyle = '#2A2A4A';
  ctx.fillRect(x + 4, y + 6, 4, ph - 8);
  ctx.fillRect(x + pw - 8, y + 6, 4, ph - 8);

  ctx.fillStyle = '#4A2A6A';
  for (let sy = y + 10; sy < y + ph - 8; sy += 6) {
    ctx.fillRect(x + 5, sy, 2, 3);
    ctx.fillRect(x + pw - 7, sy, 2, 3);
  }

  ctx.fillStyle = '#3A1A5A';
  ctx.fillRect(x + 8, y + 2, pw - 16, 14);
  ctx.fillStyle = 'rgba(100,50,200,0.3)';
  ctx.fillRect(x + 6, y, pw - 12, 18);
  ctx.fillStyle = '#2A1A4A';
  ctx.fillRect(x + 10, y + 4, pw - 20, 10);
  ctx.fillStyle = '#88CCFF';
  ctx.font = 'bold 6px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('ARCADE', x + pw / 2, y + 12);

  const scrX = x + 10;
  const scrY = y + 20;
  const scrW = pw - 20;
  const scrH = 28;
  ctx.fillStyle = '#111';
  ctx.fillRect(scrX - 2, scrY - 2, scrW + 4, scrH + 4);
  ctx.fillStyle = '#0A0A1A';
  ctx.fillRect(scrX, scrY, scrW, scrH);

  ctx.fillStyle = '#44FF44';
  ctx.fillRect(scrX + scrW / 2 - 2, scrY + scrH - 8, 4, 4);
  ctx.fillRect(scrX + scrW / 2 - 1, scrY + scrH - 10, 2, 2);
  ctx.fillStyle = '#FF4444';
  for (let i = 0; i < 4; i++) {
    ctx.fillRect(scrX + 6 + i * 10, scrY + 4, 6, 4);
    ctx.fillRect(scrX + 7 + i * 10, scrY + 8, 4, 2);
  }
  ctx.fillStyle = '#FFF';
  ctx.globalAlpha = 0.5;
  ctx.fillRect(scrX + 5, scrY + 15, 1, 1);
  ctx.fillRect(scrX + 18, scrY + 10, 1, 1);
  ctx.fillRect(scrX + 30, scrY + 18, 1, 1);
  ctx.fillRect(scrX + 12, scrY + 22, 1, 1);
  ctx.globalAlpha = 1;
  ctx.fillStyle = '#FFD700';
  ctx.font = '3px monospace';
  ctx.fillText('12500', scrX + scrW / 2, scrY + 4);

  const cpY = scrY + scrH + 6;
  ctx.fillStyle = '#2A2A3A';
  ctx.fillRect(x + 8, cpY, pw - 16, 16);
  ctx.fillStyle = '#3A3A4A';
  ctx.fillRect(x + 8, cpY, pw - 16, 2);

  const joyX = x + 16;
  const joyY = cpY + 8;
  ctx.fillStyle = '#1A1A1A';
  fillCircle(ctx, joyX, joyY, 4);
  ctx.fillStyle = '#333';
  fillCircle(ctx, joyX, joyY, 3);
  ctx.fillStyle = '#222';
  ctx.fillRect(joyX - 1, joyY - 6, 2, 4);
  ctx.fillStyle = '#444';
  fillCircle(ctx, joyX, joyY - 6, 2);

  const btnColors = ['#FF3333', '#33FF33', '#3333FF', '#FFFF33'];
  for (let i = 0; i < 4; i++) {
    ctx.fillStyle = btnColors[i];
    fillCircle(ctx, x + pw - 20 + i * 5, cpY + 8, 2.5);
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    fillCircle(ctx, x + pw - 20 + i * 5, cpY + 7, 1);
  }

  ctx.fillStyle = '#555';
  ctx.fillRect(x + pw / 2 - 4, cpY + 18, 8, 4);
  ctx.fillStyle = '#333';
  ctx.fillRect(x + pw / 2 - 2, cpY + 19, 4, 2);

  ctx.fillStyle = '#111128';
  ctx.fillRect(x + 6, y + ph - 6, pw - 12, 4);

  ctx.textAlign = 'left';
}

/* ================================================================
   FRIDGE
   ================================================================ */
export function drawFridge(ctx: CanvasRenderingContext2D, x: number, y: number, _w: number, h: number) {
  const ph = h * T;

  ctx.fillStyle = 'rgba(0,0,0,0.1)';
  ctx.fillRect(x + T - 2, y + 8, 3, ph - 6);

  ctx.fillStyle = '#E0E0E0';
  ctx.fillRect(x + 2, y + 4, T - 4, ph - 6);
  ctx.fillStyle = '#EEEEEE';
  ctx.fillRect(x + 2, y + 4, 2, ph - 6);
  ctx.fillStyle = '#C8C8C8';
  ctx.fillRect(x + T - 4, y + 4, 2, ph - 6);

  ctx.fillStyle = '#E8E8E8';
  ctx.fillRect(x + 3, y + 5, T - 6, ph / 3 - 2);
  ctx.fillStyle = '#DCDCDC';
  ctx.fillRect(x + 3, y + ph / 3 + 3, T - 6, ph * 2 / 3 - 8);

  ctx.fillStyle = '#AAAAAA';
  ctx.fillRect(x + 3, y + ph / 3 + 1, T - 6, 2);

  ctx.fillStyle = '#888';
  ctx.fillRect(x + T - 7, y + 12, 2, ph / 3 - 14);
  ctx.fillRect(x + T - 7, y + ph / 3 + 8, 2, ph / 3 - 4);
  ctx.fillStyle = '#AAA';
  ctx.fillRect(x + T - 7, y + 12, 1, ph / 3 - 14);
  ctx.fillRect(x + T - 7, y + ph / 3 + 8, 1, ph / 3 - 4);

  ctx.fillStyle = '#FF6666';
  ctx.fillRect(x + 6, y + 10, 4, 4);
  ctx.fillStyle = '#6666FF';
  ctx.fillRect(x + 12, y + 14, 4, 5);
  ctx.fillStyle = '#66CC66';
  ctx.fillRect(x + 8, y + 20, 3, 3);
  ctx.fillStyle = '#FFF';
  ctx.fillRect(x + 14, y + 8, 5, 5);
  ctx.fillStyle = '#AAD';
  ctx.fillRect(x + 15, y + 9, 3, 3);

  // Microwave on top
  const mwX = x + 3;
  const mwY = y - 8;
  ctx.fillStyle = '#333';
  ctx.fillRect(mwX, mwY, T - 6, 12);
  ctx.fillStyle = '#1A1A2A';
  ctx.fillRect(mwX + 2, mwY + 2, T - 14, 8);
  ctx.fillStyle = '#222838';
  ctx.fillRect(mwX + 3, mwY + 3, T - 16, 6);
  ctx.fillStyle = '#444';
  ctx.fillRect(mwX + T - 10, mwY + 2, 6, 8);
  ctx.fillStyle = '#22CC22';
  ctx.fillRect(mwX + T - 9, mwY + 3, 2, 2);
  ctx.fillStyle = '#CC2222';
  ctx.fillRect(mwX + T - 9, mwY + 6, 2, 2);
  ctx.fillStyle = '#00AA00';
  ctx.fillRect(mwX + T - 7, mwY + 3, 3, 2);
}
