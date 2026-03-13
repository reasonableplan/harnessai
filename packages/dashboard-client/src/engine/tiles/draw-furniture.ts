/**
 * All furniture renderers — Stardew Valley cozy cabin style
 * sofa, bookshelf, whiteboard(corkboard), fireplace, coffee machine,
 * plant, plant-small, cabinet, rug, window, poster, cooler, fridge
 */

import { T, rand, fillCircle } from './tile-utils';

/* ================================================================
   SOFA — warm brown leather / fabric
   ================================================================ */
export function drawSofa(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  const pw = w * T;
  const ph = h * T;

  // Shadow & wooden legs
  ctx.fillStyle = 'rgba(40,25,10,0.1)';
  ctx.fillRect(x + 6, y + ph - 2, pw - 8, 4);
  ctx.fillStyle = '#6A4A28';
  ctx.fillRect(x + 6, y + ph - 3, 4, 4);
  ctx.fillRect(x + pw - 10, y + ph - 3, 4, 4);

  // Back (warm brown)
  ctx.fillStyle = '#7A5A38';
  ctx.fillRect(x + 4, y, pw - 8, 14);
  ctx.fillStyle = '#6A4A28';
  ctx.fillRect(x + 4, y, pw - 8, 2);
  ctx.fillStyle = '#8A6A48';
  ctx.fillRect(x + 6, y + 3, pw - 12, 9);

  // Seat base
  ctx.fillStyle = '#8B6A45';
  ctx.fillRect(x + 2, y + 12, pw - 4, ph - 14);

  // Armrests
  ctx.fillStyle = '#7A5A38';
  ctx.fillRect(x, y + 4, 8, ph - 6);
  ctx.fillRect(x + pw - 8, y + 4, 8, ph - 6);
  ctx.fillStyle = '#9A7A58';
  ctx.fillRect(x + 1, y + 5, 6, 2);
  ctx.fillRect(x + pw - 7, y + 5, 6, 2);
  ctx.fillStyle = '#6A4A28';
  ctx.fillRect(x + 6, y + 6, 2, ph - 10);
  ctx.fillRect(x + pw - 8, y + 6, 2, ph - 10);

  // Cushions (warm forest green)
  const cushionW = Math.floor((pw - 20) / 3);
  for (let i = 0; i < 3; i++) {
    const cx = x + 10 + i * cushionW;
    const cy = y + 14;
    const cw = cushionW - 2;
    const ch = ph - 20;
    ctx.fillStyle = '#5A7A4A';
    ctx.fillRect(cx, cy, cw, ch);
    ctx.fillStyle = '#6A8A5A';
    ctx.fillRect(cx + 1, cy, cw - 2, 3);
    ctx.fillStyle = '#4A6A3A';
    ctx.fillRect(cx + 1, cy + ch - 2, cw - 2, 2);
    ctx.strokeStyle = '#4A6A3A';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(cx + 2, cy + ch / 2);
    ctx.lineTo(cx + cw - 2, cy + ch / 2);
    ctx.stroke();
  }

  // Decorative throw pillow (golden)
  const pillowX = x + 12;
  const pillowY = y + 14;
  ctx.fillStyle = '#D4A040';
  ctx.fillRect(pillowX, pillowY, 10, 10);
  ctx.fillStyle = '#C49030';
  ctx.fillRect(pillowX + 1, pillowY + 1, 8, 8);
  ctx.fillStyle = '#E4B050';
  ctx.fillRect(pillowX + 2, pillowY + 2, 3, 3);
  ctx.fillStyle = '#EAC060';
  ctx.fillRect(pillowX, pillowY, 10, 1);
}

/* ================================================================
   BOOKSHELF — warm rustic wood with colorful book spines
   ================================================================ */
export function drawBookshelf(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  const pw = w * T;
  const ph = h * T;

  // Shadow
  ctx.fillStyle = 'rgba(40,25,10,0.15)';
  ctx.fillRect(x + 3, y + 3, pw, ph);
  // Outer frame (dark warm wood)
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(x, y, pw, ph);
  // Inner back
  ctx.fillStyle = '#7A5A38';
  ctx.fillRect(x + 3, y + 3, pw - 6, ph - 6);

  const shelfCount = 4;
  const shelfH = Math.floor((ph - 6) / shelfCount);

  // Stardew-inspired book colors (warm, saturated)
  const bookColors = [
    '#B84040', '#4A78B0', '#50884A', '#CC8830',
    '#885AB0', '#C06030', '#3A8888', '#A04068',
    '#708838', '#385AAA', '#D07020', '#6044AA',
    '#288870', '#B84458',
  ];

  for (let shelf = 0; shelf < shelfCount; shelf++) {
    const sy = y + 3 + shelf * shelfH;
    // Shelf plank
    ctx.fillStyle = '#6A4A28';
    ctx.fillRect(x + 3, sy + shelfH - 3, pw - 6, 3);
    ctx.fillStyle = '#8A6A48';
    ctx.fillRect(x + 3, sy + shelfH - 3, pw - 6, 1);

    // Books
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
      ctx.fillStyle = 'rgba(255,240,200,0.2)';
      ctx.fillRect(bx, bookBase + (maxBookH - bh), 1, bh);
      ctx.fillStyle = 'rgba(0,0,0,0.2)';
      ctx.fillRect(bx + bw - 1, bookBase + (maxBookH - bh), 1, bh);

      if (bh > 8) {
        ctx.fillStyle = 'rgba(255,240,200,0.4)';
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
  ctx.fillStyle = '#5A8898';
  fillCircle(ctx, globeX, globeY + 4, 4);
  ctx.fillStyle = '#5AAA5A';
  ctx.fillRect(globeX - 2, globeY + 2, 3, 3);
  ctx.fillStyle = '#8B6840';
  ctx.fillRect(globeX - 1, globeY + 8, 2, 3);
  ctx.fillRect(globeX - 3, globeY + 10, 6, 1);

  // Frame bevel
  ctx.fillStyle = '#6A4828';
  ctx.fillRect(x, y, pw, 2);
  ctx.fillRect(x, y, 3, ph);
  ctx.fillStyle = '#4A2A10';
  ctx.fillRect(x, y + ph - 3, pw, 3);
  ctx.fillRect(x + pw - 3, y, 3, ph);
}

/* ================================================================
   WHITEBOARD → CORKBOARD (Stardew notice board style)
   ================================================================ */
export function drawWhiteboard(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  const pw = w * T;
  const ph = h * T;

  // Wooden frame
  ctx.fillStyle = '#6A4A28';
  ctx.fillRect(x - 1, y - 1, pw + 2, ph + 2);
  ctx.fillStyle = '#8A6A48';
  ctx.fillRect(x - 1, y - 1, pw + 2, 2);
  ctx.fillRect(x - 1, y - 1, 2, ph + 2);
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(x - 1, y + ph - 1, pw + 2, 2);
  ctx.fillRect(x + pw - 1, y - 1, 2, ph + 2);

  // Cork background
  ctx.fillStyle = '#C4A060';
  ctx.fillRect(x + 3, y + 3, pw - 6, ph - 6);
  // Cork texture
  ctx.fillStyle = '#B89050';
  for (let i = 0; i < 20; i++) {
    const tx = x + 4 + rand(i, 0, 90) * (pw - 10);
    const ty = y + 4 + rand(i, 1, 91) * (ph - 10);
    fillCircle(ctx, tx, ty, 1 + rand(i, 2, 92));
  }

  // Title banner
  ctx.fillStyle = '#5A3A18';
  ctx.font = 'bold 5px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('TASK BOARD', x + pw / 2, y + 10);

  // Pinned cards (colored sticky notes)
  const cols = 5;
  const colW = (pw - 10) / cols;
  ctx.strokeStyle = '#B09060';
  ctx.lineWidth = 0.5;
  for (let i = 1; i < cols; i++) {
    const lx = x + 5 + i * colW;
    ctx.beginPath();
    ctx.moveTo(lx, y + 13);
    ctx.lineTo(lx, y + ph - 8);
    ctx.stroke();
  }

  // Column headers (warm tones)
  const headerColors = ['#C04040', '#D48830', '#4A8AB0', '#8860A8', '#50884A'];
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

  // Sticky note cards
  const cardColors = ['#FFE8A0', '#FFD0A0', '#C8E8C0', '#D0D8FF', '#FFD0D0'];
  for (let i = 0; i < cols; i++) {
    const numCards = 2 + Math.floor(rand(i, 0, 99) * 3);
    for (let c = 0; c < numCards; c++) {
      const cx = x + 7 + i * colW;
      const cy = y + 21 + c * 8;
      if (cy + 6 > y + ph - 10) break;
      ctx.fillStyle = cardColors[(i + c) % cardColors.length];
      ctx.fillRect(cx, cy, colW - 5, 6);
      ctx.fillStyle = '#998870';
      ctx.fillRect(cx + 1, cy + 2, colW - 9, 1);
      ctx.fillRect(cx + 1, cy + 4, (colW - 9) * 0.6, 0.5);
      // Pin
      ctx.fillStyle = '#CC3030';
      fillCircle(ctx, cx + (colW - 5) / 2, cy, 1.5);
    }
  }

  // Bottom shelf
  ctx.fillStyle = '#6A4A28';
  ctx.fillRect(x + pw / 4, y + ph - 1, pw / 2, 4);
  ctx.fillStyle = '#8A6A48';
  ctx.fillRect(x + pw / 4, y + ph - 1, pw / 2, 1);

  ctx.textAlign = 'left';
}

/* ================================================================
   FIREPLACE — cozy Stardew hearth (replaces arcade)
   ================================================================ */
export function drawFireplace(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  const pw = w * T;
  const ph = h * T;

  // Stone chimney base
  ctx.fillStyle = '#8A7A68';
  ctx.fillRect(x + 2, y + 2, pw - 4, ph - 4);

  // Stone texture
  const stoneColors = ['#9A8A78', '#8A7A68', '#7A6A58', '#A09080'];
  for (let sy = 0; sy < ph - 4; sy += 8) {
    for (let sx = 0; sx < pw - 4; sx += 10) {
      const offset = Math.floor(sy / 8) % 2 === 0 ? 0 : 5;
      const ci = Math.floor(rand(sx, sy, 40) * stoneColors.length);
      ctx.fillStyle = stoneColors[ci];
      const sw = 8 + Math.floor(rand(sx, sy, 41) * 4);
      ctx.fillRect(x + 3 + sx + offset, y + 3 + sy, Math.min(sw, pw - 7 - sx - offset), 7);
      // Stone highlight
      ctx.fillStyle = 'rgba(255,240,200,0.1)';
      ctx.fillRect(x + 3 + sx + offset, y + 3 + sy, Math.min(sw, pw - 7 - sx - offset), 1);
    }
  }

  // Mantle (dark wood beam)
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(x - 2, y + 4, pw + 4, 6);
  ctx.fillStyle = '#7A5A38';
  ctx.fillRect(x - 2, y + 4, pw + 4, 2);

  // Firebox opening (arch shape)
  const fbX = x + pw / 2 - 14;
  const fbY = y + 16;
  const fbW = 28;
  const fbH = ph - 24;
  ctx.fillStyle = '#1A1008';
  ctx.fillRect(fbX + 2, fbY, fbW - 4, fbH);
  ctx.fillRect(fbX, fbY + 4, fbW, fbH - 4);
  // Arch top
  ctx.fillRect(fbX + 4, fbY - 2, fbW - 8, 4);

  // Fire glow
  ctx.fillStyle = 'rgba(255,120,30,0.15)';
  ctx.fillRect(fbX - 4, fbY - 4, fbW + 8, fbH + 8);

  // Flames (layered warm colors)
  const flameX = x + pw / 2;
  const flameBase = y + ph - 12;
  // Outer glow
  ctx.fillStyle = '#FF6010';
  ctx.globalAlpha = 0.7;
  ctx.fillRect(flameX - 10, flameBase - 8, 20, 12);
  // Mid flame
  ctx.fillStyle = '#FF8830';
  ctx.globalAlpha = 0.8;
  ctx.fillRect(flameX - 7, flameBase - 12, 14, 14);
  // Inner flame
  ctx.fillStyle = '#FFCC40';
  ctx.globalAlpha = 0.9;
  ctx.fillRect(flameX - 4, flameBase - 10, 8, 10);
  // Hot core
  ctx.fillStyle = '#FFF0A0';
  ctx.globalAlpha = 1;
  ctx.fillRect(flameX - 2, flameBase - 6, 4, 6);
  ctx.globalAlpha = 1;

  // Logs
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(flameX - 10, flameBase + 2, 8, 4);
  ctx.fillRect(flameX + 2, flameBase + 2, 8, 4);
  ctx.fillStyle = '#7A5A38';
  ctx.fillRect(flameX - 10, flameBase + 2, 8, 1);
  ctx.fillRect(flameX + 2, flameBase + 2, 8, 1);

  // Embers
  ctx.fillStyle = '#FF4400';
  ctx.globalAlpha = 0.6;
  fillCircle(ctx, flameX - 6, flameBase, 1);
  fillCircle(ctx, flameX + 4, flameBase - 1, 0.8);
  fillCircle(ctx, flameX, flameBase + 1, 1.2);
  ctx.globalAlpha = 1;

  // Hearth base stones
  ctx.fillStyle = '#6A5A48';
  ctx.fillRect(x, y + ph - 6, pw, 6);
  ctx.fillStyle = '#7A6A58';
  ctx.fillRect(x, y + ph - 6, pw, 1);
}

/* ================================================================
   COFFEE MACHINE — rustic brewing station
   ================================================================ */
export function drawCoffeeMachine(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Wooden counter base
  ctx.fillStyle = '#7A5A30';
  ctx.fillRect(x + 2, y + T - 2, T - 4, T + 2);
  ctx.fillStyle = '#8A6A40';
  ctx.fillRect(x + 2, y + T - 2, T - 4, 2);
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(x + 2, y + T * 2 - 4, T - 4, 3);
  // Legs
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(x + 4, y + T * 2 - 2, 3, 4);
  ctx.fillRect(x + T - 7, y + T * 2 - 2, 3, 4);

  // Coffee maker body (copper/warm metal)
  ctx.fillStyle = '#8A5A30';
  ctx.fillRect(x + 5, y + 2, T - 10, T - 6);
  ctx.fillStyle = '#A07040';
  ctx.fillRect(x + 7, y + 4, T - 14, 12);
  // Glass carafe area
  ctx.fillStyle = '#6B3A18';
  ctx.fillRect(x + 8, y + 5, 8, 4);
  ctx.fillStyle = '#4A2A10';
  ctx.fillRect(x + 9, y + 6, 6, 2);

  // Indicator dots (warm)
  ctx.fillStyle = '#CC5533';
  fillCircle(ctx, x + 10, y + T - 7, 1.5);
  ctx.fillStyle = '#55AA55';
  fillCircle(ctx, x + 16, y + T - 7, 1.5);
  ctx.fillStyle = '#DDAA33';
  fillCircle(ctx, x + 22, y + T - 7, 1.5);

  // Spout
  ctx.fillStyle = '#6A4A28';
  ctx.fillRect(x + 12, y + 16, 6, 3);

  // Cup underneath
  ctx.fillStyle = '#E0C8A0';
  ctx.fillRect(x + 8, y + T + 2, 10, 9);
  ctx.fillStyle = '#EEDDC0';
  ctx.fillRect(x + 9, y + T + 2, 8, 2);
  ctx.fillStyle = '#6B3A18';
  ctx.fillRect(x + 9, y + T + 4, 8, 4);

  // Steam
  ctx.globalAlpha = 0.15;
  ctx.fillStyle = '#F0E0C0';
  ctx.fillRect(x + 10, y + T - 1, 1, 3);
  ctx.fillRect(x + 13, y + T - 2, 1, 4);
  ctx.fillRect(x + 16, y + T, 1, 2);
  ctx.globalAlpha = 1;

  // Label
  ctx.fillStyle = '#8A6A40';
  ctx.font = '3px monospace';
  ctx.textAlign = 'center';
  ctx.fillText('BREW', x + T / 2, y + 22);
  ctx.textAlign = 'left';
}

/* ================================================================
   PLANT — lush Stardew-style potted plant
   ================================================================ */
export function drawPlant(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Shadow
  ctx.fillStyle = 'rgba(40,25,10,0.1)';
  fillCircle(ctx, x + T / 2, y + T * 2 - 4, 10);

  // Terracotta pot
  ctx.fillStyle = '#C06830';
  ctx.fillRect(x + 7, y + T + 6, T - 14, T - 10);
  ctx.fillStyle = '#D07840';
  ctx.fillRect(x + 5, y + T + 2, T - 10, 5);
  ctx.fillStyle = '#E08850';
  ctx.fillRect(x + 5, y + T + 2, T - 10, 2);
  // Pot rim
  ctx.fillStyle = '#B05828';
  ctx.fillRect(x + 8, y + T * 2 - 6, T - 16, 3);

  // Soil
  ctx.fillStyle = '#4A3018';
  ctx.fillRect(x + 7, y + T + 4, T - 14, 4);
  ctx.fillStyle = '#5A3A20';
  ctx.fillRect(x + 8, y + T + 4, T - 16, 2);

  // Stem
  ctx.fillStyle = '#3A7A2A';
  ctx.fillRect(x + 14, y + 10, 2, T - 4);

  // Leaves (lush greens)
  const leaves: Array<[number, number, number, number, string]> = [
    [2, 4, 10, 8, '#3A8A2A'],
    [T - 12, 6, 10, 7, '#3A8A2A'],
    [6, 0, 12, 10, '#4AAA3A'],
    [4, 8, 8, 6, '#2A7A1A'],
    [T - 10, 10, 8, 5, '#2A7A1A'],
    [8, 2, 8, 6, '#5ABB4A'],
    [10, -2, 10, 8, '#4AAA3A'],
  ];
  for (const [ox, oy, lw, lh, color] of leaves) {
    ctx.fillStyle = color;
    ctx.fillRect(x + ox + 1, y + oy, lw - 2, lh);
    ctx.fillRect(x + ox, y + oy + 1, lw, lh - 2);
  }

  // Leaf veins
  ctx.strokeStyle = 'rgba(20,80,10,0.25)';
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  ctx.moveTo(x + 7, y + 8);
  ctx.lineTo(x + 12, y + 5);
  ctx.moveTo(x + T - 7, y + 10);
  ctx.lineTo(x + T - 12, y + 7);
  ctx.stroke();

  // Small flower (Stardew touch)
  ctx.fillStyle = '#FFD040';
  fillCircle(ctx, x + 8, y + 3, 2);
  ctx.fillStyle = '#FFF0A0';
  fillCircle(ctx, x + 8, y + 3, 1);

  // Drooping leaves
  ctx.fillStyle = '#4AAA3A';
  ctx.fillRect(x + 1, y + 12, 6, 4);
  ctx.fillRect(x + T - 7, y + 14, 6, 3);
}

/* ================================================================
   PLANT-SMALL — small desk succulent
   ================================================================ */
export function drawPlantSmall(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Small terracotta pot
  ctx.fillStyle = '#C06830';
  ctx.fillRect(x + 10, y + 18, 12, 10);
  ctx.fillStyle = '#D07840';
  ctx.fillRect(x + 9, y + 16, 14, 4);
  ctx.fillStyle = '#E08850';
  ctx.fillRect(x + 9, y + 16, 14, 1);

  // Soil
  ctx.fillStyle = '#4A3018';
  ctx.fillRect(x + 10, y + 17, 12, 2);

  // Stem
  ctx.fillStyle = '#3A7A2A';
  ctx.fillRect(x + 15, y + 10, 2, 8);

  // Leaves
  ctx.fillStyle = '#3A8A2A';
  ctx.fillRect(x + 11, y + 8, 6, 5);
  ctx.fillStyle = '#4AAA3A';
  ctx.fillRect(x + 15, y + 6, 6, 5);
  ctx.fillStyle = '#5ABB4A';
  ctx.fillRect(x + 12, y + 5, 5, 4);
  ctx.fillStyle = '#2A7A1A';
  ctx.fillRect(x + 17, y + 9, 4, 4);

  // Tiny flower
  ctx.fillStyle = '#FF8080';
  fillCircle(ctx, x + 14, y + 6, 1.5);
}

/* ================================================================
   CABINET — warm wooden drawer chest
   ================================================================ */
export function drawCabinet(ctx: CanvasRenderingContext2D, x: number, y: number) {
  const ph = T * 2;

  ctx.fillStyle = 'rgba(40,25,10,0.1)';
  ctx.fillRect(x + 4, y + ph - 1, T - 4, 3);

  // Body (warm wood)
  ctx.fillStyle = '#7A5A30';
  ctx.fillRect(x + 2, y + 2, T - 4, ph - 4);
  ctx.fillStyle = '#8A6A40';
  ctx.fillRect(x + 2, y + 2, 2, ph - 4);
  ctx.fillStyle = '#6A4A20';
  ctx.fillRect(x + T - 4, y + 2, 2, ph - 4);
  ctx.fillStyle = '#8A6A40';
  ctx.fillRect(x + 2, y + 2, T - 4, 2);

  // Drawers
  const drawerH = (ph - 10) / 3;
  for (let i = 0; i < 3; i++) {
    const dy = y + 5 + i * (drawerH + 1);
    ctx.fillStyle = '#8A6A40';
    ctx.fillRect(x + 4, dy, T - 8, drawerH - 1);
    ctx.fillStyle = '#9A7A50';
    ctx.fillRect(x + 4, dy, T - 8, 1);
    ctx.fillRect(x + 4, dy, 1, drawerH - 1);
    ctx.fillStyle = '#6A4A28';
    ctx.fillRect(x + 4, dy + drawerH - 2, T - 8, 1);
    ctx.fillRect(x + T - 5, dy, 1, drawerH - 1);
    // Handle (brass knob)
    ctx.fillStyle = '#C4A040';
    fillCircle(ctx, x + T / 2, dy + drawerH / 2, 2);
    ctx.fillStyle = '#DDBB55';
    fillCircle(ctx, x + T / 2 - 0.5, dy + drawerH / 2 - 0.5, 1);
  }
}

/* ================================================================
   RUG — warm woven Stardew rug
   ================================================================ */
export function drawRug(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  // Base (warm earthy red)
  ctx.fillStyle = '#8A4030';
  ctx.fillRect(x + 2, y + 2, pw - 4, ph - 4);

  // Outer border (golden pattern)
  ctx.strokeStyle = '#D4A840';
  ctx.lineWidth = 2;
  ctx.strokeRect(x + 4, y + 4, pw - 8, ph - 8);

  // Border pattern (warm geometric)
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

  // Inner border (forest green)
  ctx.strokeStyle = '#3A6A38';
  ctx.lineWidth = 1.5;
  ctx.strokeRect(x + 10, y + 10, pw - 20, ph - 20);

  // Inner fill (slightly lighter)
  ctx.fillStyle = '#9A5040';
  ctx.fillRect(x + 12, y + 12, pw - 24, ph - 24);

  // Center diamond pattern
  const cx = x + pw / 2;
  const cy = y + ph / 2;
  const dw = Math.min(pw - 40, 60);
  const dh = Math.min(ph - 30, 40);

  ctx.fillStyle = '#3A6A38';
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

  ctx.fillStyle = '#8A4030';
  ctx.beginPath();
  ctx.moveTo(cx, cy - dh / 2 + 8);
  ctx.lineTo(cx + dw / 2 - 10, cy);
  ctx.lineTo(cx, cy + dh / 2 - 8);
  ctx.lineTo(cx - dw / 2 + 10, cy);
  ctx.closePath();
  ctx.fill();

  // Center star (Stardew touch)
  ctx.fillStyle = '#D4A840';
  fillCircle(ctx, cx, cy, 3);
  ctx.fillStyle = '#FFF0C0';
  fillCircle(ctx, cx, cy, 1.5);

  // Corner decorations
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
    ctx.fillStyle = '#3A6A38';
    fillCircle(ctx, dx, dy, 1.5);
  }

  // Fringe (warm)
  ctx.fillStyle = '#D4A840';
  for (let fx = x + 6; fx < x + pw - 4; fx += 3) {
    ctx.fillRect(fx, y, 1, 3);
    ctx.fillRect(fx, y + ph - 3, 1, 3);
  }
}

/* ================================================================
   WINDOW — countryside view (green hills, sun) instead of city
   ================================================================ */
export function drawWindow(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  const pw = w * T;
  const ph = h * T;

  // Curtain rod (warm wood)
  ctx.fillStyle = '#7A5A30';
  ctx.fillRect(x - 4, y - 3, pw + 8, 4);
  ctx.fillStyle = '#9A7A48';
  ctx.fillRect(x - 4, y - 3, pw + 8, 1);
  fillCircle(ctx, x - 3, y - 1, 2);
  fillCircle(ctx, x + pw + 3, y - 1, 2);

  // Curtains (warm golden/ochre instead of red)
  const curtainW = 10;
  ctx.fillStyle = '#B48830';
  ctx.fillRect(x - 2, y, curtainW, ph + 2);
  ctx.fillStyle = '#9A7028';
  ctx.fillRect(x, y, 2, ph + 2);
  ctx.fillRect(x + 4, y, 1, ph + 2);
  ctx.fillStyle = '#C89838';
  ctx.fillRect(x + 2, y, 1, ph + 2);
  ctx.fillRect(x + 6, y, 1, ph + 2);
  ctx.fillStyle = '#B48830';
  ctx.fillRect(x + pw - curtainW + 2, y, curtainW, ph + 2);
  ctx.fillStyle = '#9A7028';
  ctx.fillRect(x + pw - 4, y, 2, ph + 2);
  ctx.fillRect(x + pw - 7, y, 1, ph + 2);
  ctx.fillStyle = '#C89838';
  ctx.fillRect(x + pw - 2, y, 1, ph + 2);
  ctx.fillRect(x + pw - 9, y, 1, ph + 2);

  // Window frame (wood)
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(x + 6, y + 2, pw - 12, ph - 2);

  // Glass area
  const glassX = x + 9;
  const glassY = y + 5;
  const glassW = pw - 18;
  const glassH = ph - 8;

  // Sky gradient (warm sunny day)
  ctx.fillStyle = '#88CCF0';
  ctx.fillRect(glassX, glassY, glassW, glassH * 0.4);
  ctx.fillStyle = '#A0D8F0';
  ctx.fillRect(glassX, glassY + glassH * 0.4, glassW, glassH * 0.2);

  // Sun
  ctx.fillStyle = '#FFE060';
  fillCircle(ctx, glassX + glassW - 12, glassY + 8, 5);
  ctx.fillStyle = '#FFF0A0';
  fillCircle(ctx, glassX + glassW - 12, glassY + 8, 3);

  // Clouds (soft white)
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  fillCircle(ctx, glassX + 15, glassY + 8, 4);
  fillCircle(ctx, glassX + 20, glassY + 7, 5);
  fillCircle(ctx, glassX + 26, glassY + 8, 3);

  // Rolling green hills (Stardew countryside)
  const hillY = glassY + glassH * 0.55;
  // Far hills (lighter green)
  ctx.fillStyle = '#6AAA58';
  ctx.beginPath();
  ctx.moveTo(glassX, hillY + 4);
  ctx.quadraticCurveTo(glassX + glassW * 0.25, hillY - 6, glassX + glassW * 0.5, hillY + 2);
  ctx.quadraticCurveTo(glassX + glassW * 0.75, hillY + 8, glassX + glassW, hillY);
  ctx.lineTo(glassX + glassW, glassY + glassH);
  ctx.lineTo(glassX, glassY + glassH);
  ctx.closePath();
  ctx.fill();

  // Near hills (deeper green)
  ctx.fillStyle = '#4A8A38';
  ctx.beginPath();
  ctx.moveTo(glassX, hillY + 12);
  ctx.quadraticCurveTo(glassX + glassW * 0.3, hillY + 4, glassX + glassW * 0.6, hillY + 10);
  ctx.quadraticCurveTo(glassX + glassW * 0.85, hillY + 16, glassX + glassW, hillY + 8);
  ctx.lineTo(glassX + glassW, glassY + glassH);
  ctx.lineTo(glassX, glassY + glassH);
  ctx.closePath();
  ctx.fill();

  // Trees on hills
  ctx.fillStyle = '#3A7A2A';
  const treePositions = [0.15, 0.35, 0.55, 0.7, 0.85];
  for (const tp of treePositions) {
    const tx = glassX + glassW * tp;
    const ty = hillY + 2 + rand(Math.floor(tp * 10), 0, 77) * 8;
    // Tree trunk
    ctx.fillStyle = '#5A3A18';
    ctx.fillRect(tx, ty + 3, 2, 4);
    // Foliage
    ctx.fillStyle = '#3A7A2A';
    ctx.fillRect(tx - 2, ty, 6, 5);
    ctx.fillRect(tx - 1, ty - 2, 4, 3);
  }

  // Window cross (wood)
  ctx.fillStyle = '#5A3A18';
  ctx.fillRect(glassX + glassW / 2 - 2, glassY, 3, glassH);
  ctx.fillRect(glassX, glassY + glassH / 2 - 1, glassW, 3);
  ctx.fillStyle = '#6A4A28';
  ctx.fillRect(glassX - 1, glassY, 1, glassH);
  ctx.fillRect(glassX + glassW, glassY, 1, glassH);
  ctx.fillRect(glassX, glassY - 1, glassW, 1);

  // Window sill
  ctx.fillStyle = '#6A4A28';
  ctx.fillRect(x + 4, y + ph - 1, pw - 8, 4);
  ctx.fillStyle = '#8A6A48';
  ctx.fillRect(x + 4, y + ph - 1, pw - 8, 1);

  // Glass reflection
  ctx.fillStyle = 'rgba(255,255,255,0.04)';
  ctx.fillRect(glassX + 2, glassY + 2, glassW / 3, glassH - 4);
}

/* ================================================================
   POSTERS — Stardew-style wall decorations
   ================================================================ */
export function drawPoster(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  type: string,
) {
  const pw = w * T;
  const ph = h * T;

  ctx.fillStyle = 'rgba(40,25,10,0.2)';
  ctx.fillRect(x + 4, y + 3, pw - 4, ph - 2);

  if (type === 'poster-indie') {
    // "Sprint" calendar/poster (warm tones)
    ctx.fillStyle = '#2A5A5A';
    ctx.fillRect(x + 2, y + 2, pw - 4, ph - 4);
    ctx.strokeStyle = '#D4A840';
    ctx.lineWidth = 1;
    ctx.strokeRect(x + 3, y + 3, pw - 6, ph - 6);
    ctx.fillStyle = '#5CE0D0';
    ctx.font = 'bold 7px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('CODE', x + pw / 2, y + 14);
    // Small pixel art character
    const cx = x + pw / 2;
    const cy = y + ph / 2 + 2;
    ctx.fillStyle = '#FFD040';
    ctx.fillRect(cx - 2, cy - 6, 4, 4);
    ctx.fillStyle = '#5CE0D0';
    ctx.fillRect(cx - 3, cy - 2, 6, 6);
    ctx.fillStyle = '#5A4030';
    ctx.fillRect(cx - 3, cy + 4, 2, 4);
    ctx.fillRect(cx + 1, cy + 4, 2, 4);
    ctx.fillStyle = '#FFF';
    ctx.font = 'bold 6px monospace';
    ctx.fillText('JAM', x + pw / 2, y + ph - 8);
  } else {
    // Farm/nature themed poster
    ctx.fillStyle = '#5A3A20';
    ctx.fillRect(x + 2, y + 2, pw - 4, ph - 4);
    ctx.strokeStyle = '#D4A840';
    ctx.lineWidth = 1;
    ctx.strokeRect(x + 3, y + 3, pw - 6, ph - 6);
    ctx.fillStyle = '#FFD040';
    ctx.font = 'bold 7px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('SHIP', x + pw / 2, y + 14);
    // Small rocket/star
    const cx = x + pw / 2;
    const cy = y + ph / 2 + 2;
    ctx.fillStyle = '#FFD040';
    // Star shape
    ctx.fillRect(cx - 1, cy - 5, 2, 10);
    ctx.fillRect(cx - 5, cy - 1, 10, 2);
    ctx.fillRect(cx - 3, cy - 3, 6, 6);
    ctx.fillStyle = '#FFF0A0';
    fillCircle(ctx, cx, cy, 2);
    ctx.fillStyle = '#FFF';
    ctx.font = 'bold 6px monospace';
    ctx.fillText('IT!', x + pw / 2, y + ph - 8);
  }
  ctx.textAlign = 'left';
}

/* ================================================================
   COOLER — wooden water barrel (Stardew style)
   ================================================================ */
export function drawCooler(ctx: CanvasRenderingContext2D, x: number, y: number) {
  const ph = T * 2;

  ctx.fillStyle = 'rgba(40,25,10,0.08)';
  ctx.fillRect(x + 7, y + ph - 2, T - 10, 4);

  // Barrel body
  ctx.fillStyle = '#8A6838';
  ctx.fillRect(x + 6, y + 8, T - 12, ph - 12);
  // Barrel staves
  ctx.fillStyle = '#9A7848';
  ctx.fillRect(x + 7, y + 9, 3, ph - 14);
  ctx.fillRect(x + 13, y + 9, 3, ph - 14);
  ctx.fillRect(x + 19, y + 9, 3, ph - 14);
  // Metal bands
  ctx.fillStyle = '#777';
  ctx.fillRect(x + 6, y + 14, T - 12, 2);
  ctx.fillRect(x + 6, y + ph - 10, T - 12, 2);
  ctx.fillStyle = '#999';
  ctx.fillRect(x + 6, y + 14, T - 12, 1);
  ctx.fillRect(x + 6, y + ph - 10, T - 12, 1);

  // Water bucket on top
  ctx.fillStyle = '#5A8ABB';
  ctx.fillRect(x + 8, y + 2, T - 16, 8);
  ctx.fillStyle = '#7AAAD0';
  ctx.fillRect(x + 9, y + 3, 3, 5);

  // Spigot
  ctx.fillStyle = '#666';
  ctx.fillRect(x + 10, y + 20, 3, 4);
  ctx.fillRect(x + 17, y + 20, 3, 4);
  ctx.fillStyle = '#888';
  fillCircle(ctx, x + 11.5, y + 21, 1.5);
  fillCircle(ctx, x + 18.5, y + 21, 1.5);

  // Drip tray
  ctx.fillStyle = '#7A5A30';
  ctx.fillRect(x + 8, y + 26, T - 16, 3);
  ctx.fillStyle = '#8A6A40';
  ctx.fillRect(x + 8, y + 26, T - 16, 1);
}

/* ================================================================
   FRIDGE — warm wooden icebox (Stardew style)
   ================================================================ */
export function drawFridge(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  _w: number,
  h: number,
) {
  const ph = h * T;

  // Side shadow
  ctx.fillStyle = 'rgba(40,25,10,0.1)';
  ctx.fillRect(x + T - 2, y + 8, 3, ph - 6);

  // Wooden icebox body
  ctx.fillStyle = '#8A6A40';
  ctx.fillRect(x + 2, y + 4, T - 4, ph - 6);
  ctx.fillStyle = '#9A7A50';
  ctx.fillRect(x + 2, y + 4, 2, ph - 6);
  ctx.fillStyle = '#7A5A30';
  ctx.fillRect(x + T - 4, y + 4, 2, ph - 6);

  // Upper compartment (ice)
  ctx.fillStyle = '#A08A60';
  ctx.fillRect(x + 3, y + 5, T - 6, ph / 3 - 2);
  // Lower compartment
  ctx.fillStyle = '#9A7A50';
  ctx.fillRect(x + 3, y + ph / 3 + 3, T - 6, (ph * 2) / 3 - 8);

  // Divider
  ctx.fillStyle = '#7A5A30';
  ctx.fillRect(x + 3, y + ph / 3 + 1, T - 6, 2);

  // Handles (brass)
  ctx.fillStyle = '#C4A040';
  ctx.fillRect(x + T - 7, y + 12, 2, ph / 3 - 14);
  ctx.fillRect(x + T - 7, y + ph / 3 + 8, 2, ph / 3 - 4);
  ctx.fillStyle = '#DDBB55';
  ctx.fillRect(x + T - 7, y + 12, 1, ph / 3 - 14);
  ctx.fillRect(x + T - 7, y + ph / 3 + 8, 1, ph / 3 - 4);

  // Food items peeking through
  ctx.fillStyle = '#CC5533';
  ctx.fillRect(x + 6, y + 10, 4, 4); // apple
  ctx.fillStyle = '#4488CC';
  ctx.fillRect(x + 12, y + 14, 4, 5); // jar
  ctx.fillStyle = '#5AAA5A';
  ctx.fillRect(x + 8, y + 20, 3, 3); // veggie

  // Bread basket on top
  const bX = x + 3;
  const bY = y - 6;
  ctx.fillStyle = '#B08838';
  ctx.fillRect(bX, bY + 4, T - 6, 6);
  ctx.fillStyle = '#C49848';
  ctx.fillRect(bX + 1, bY + 4, T - 8, 2);
  // Bread
  ctx.fillStyle = '#D4A050';
  ctx.fillRect(bX + 3, bY, 8, 6);
  ctx.fillStyle = '#E4B060';
  ctx.fillRect(bX + 4, bY + 1, 6, 2);
}
