/**
 * LPC-style tilemap renderer
 * Draws floor, walls, furniture, and decorations procedurally on Canvas
 */

import {
  TILE_SIZE,
  MAP_COLS,
  MAP_ROWS,
  WALL_ROWS,
  FURNITURE,
  type FurniturePlacement,
} from './sprite-config';

const T = TILE_SIZE;

// ---- Color palette (LPC interior style) ----
const FLOOR_BASE = '#8B7355';
const FLOOR_LIGHT = '#9B8365';
const FLOOR_DARK = '#7A6245';
const FLOOR_LINE = '#6A5235';

const WALL_BASE = '#A09080';
const WALL_LIGHT = '#B0A090';
const WALL_DARK = '#8A7A6A';
const WALL_TOP = '#706050';
const WAINSCOT = '#5A4A3A';
const WAINSCOT_LIGHT = '#6A5A4A';

// ---- Tile drawing functions ----

function drawFloorTile(ctx: CanvasRenderingContext2D, x: number, y: number, row: number, col: number) {
  // Wood plank floor — alternating plank pattern
  const isEven = (row + col) % 2 === 0;
  ctx.fillStyle = isEven ? FLOOR_BASE : FLOOR_LIGHT;
  ctx.fillRect(x, y, T, T);

  // Plank grain lines
  ctx.strokeStyle = FLOOR_LINE;
  ctx.lineWidth = 1;
  const grainOffset = (col * 7 + row * 3) % 5;
  for (let i = 0; i < 3; i++) {
    const gy = y + 8 + i * 10 + grainOffset;
    if (gy < y + T) {
      ctx.beginPath();
      ctx.moveTo(x + 2, gy);
      ctx.lineTo(x + T - 2, gy);
      ctx.stroke();
    }
  }

  // Plank border (bottom & right edges)
  ctx.fillStyle = FLOOR_DARK;
  ctx.fillRect(x, y + T - 1, T, 1);
  ctx.fillRect(x + T - 1, y, 1, T);

  // Subtle shadow near wall
  if (row === WALL_ROWS) {
    ctx.fillStyle = 'rgba(0,0,0,0.15)';
    ctx.fillRect(x, y, T, 8);
  }
}

function drawWallTile(ctx: CanvasRenderingContext2D, x: number, y: number, row: number, col: number) {
  // Stone/plaster wall with brick pattern
  ctx.fillStyle = WALL_BASE;
  ctx.fillRect(x, y, T, T);

  // Brick lines
  const brickH = 8;
  const brickW = 16;
  ctx.strokeStyle = WALL_DARK;
  ctx.lineWidth = 1;

  for (let by = 0; by < T; by += brickH) {
    // Horizontal mortar line
    ctx.beginPath();
    ctx.moveTo(x, y + by);
    ctx.lineTo(x + T, y + by);
    ctx.stroke();

    // Vertical mortar lines (offset every other row)
    const offset = (Math.floor(by / brickH) + col) % 2 === 0 ? 0 : brickW / 2;
    for (let bx = offset; bx < T; bx += brickW) {
      ctx.beginPath();
      ctx.moveTo(x + bx, y + by);
      ctx.lineTo(x + bx, y + by + brickH);
      ctx.stroke();
    }
  }

  // Highlight on bricks
  ctx.fillStyle = WALL_LIGHT;
  for (let by = 0; by < T; by += brickH) {
    const offset = (Math.floor(by / brickH) + col) % 2 === 0 ? 2 : brickW / 2 + 2;
    for (let bx = offset; bx < T - 4; bx += brickW) {
      ctx.fillRect(x + bx, y + by + 1, 4, 2);
    }
  }

  // Top row cap (darker)
  if (row === 0) {
    ctx.fillStyle = WALL_TOP;
    ctx.fillRect(x, y, T, 4);
  }

  // Wainscoting (bottom of wall area)
  if (row === WALL_ROWS - 1) {
    ctx.fillStyle = WAINSCOT;
    ctx.fillRect(x, y + T - 10, T, 10);
    // Panel detail
    ctx.fillStyle = WAINSCOT_LIGHT;
    ctx.fillRect(x + 2, y + T - 8, T - 4, 2);
    // Baseboard
    ctx.fillStyle = '#4A3A2A';
    ctx.fillRect(x, y + T - 2, T, 2);
  }
}

// ---- Furniture drawing ----

function drawDesk(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  // Desk surface (top-down RPG style)
  ctx.fillStyle = '#6B4226';
  ctx.fillRect(x + 2, y + 4, pw - 4, ph - 4);
  // Desk edge highlight
  ctx.fillStyle = '#8B6240';
  ctx.fillRect(x + 2, y + 4, pw - 4, 4);
  // Desk shadow
  ctx.fillStyle = '#4A2A16';
  ctx.fillRect(x + 2, y + ph - 4, pw - 4, 4);
  ctx.fillRect(x + pw - 4, y + 4, 4, ph - 4);

  // Legs (visible from front)
  ctx.fillStyle = '#4A2A16';
  ctx.fillRect(x + 4, y + ph - 2, 4, 4);
  ctx.fillRect(x + pw - 8, y + ph - 2, 4, 4);

  // Monitor on desk
  const monX = x + pw / 2 - 10;
  const monY = y + 6;
  // Screen
  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(monX, monY, 20, 14);
  // Screen bezel
  ctx.strokeStyle = '#555555';
  ctx.lineWidth = 2;
  ctx.strokeRect(monX, monY, 20, 14);
  // Screen content (code lines)
  ctx.fillStyle = '#44CC44';
  ctx.fillRect(monX + 3, monY + 3, 8, 1);
  ctx.fillStyle = '#61DAFB';
  ctx.fillRect(monX + 3, monY + 6, 12, 1);
  ctx.fillStyle = '#FFD700';
  ctx.fillRect(monX + 3, monY + 9, 6, 1);
  // Stand
  ctx.fillStyle = '#555555';
  ctx.fillRect(monX + 8, monY + 14, 4, 4);
  ctx.fillRect(monX + 5, monY + 17, 10, 2);

  // Keyboard
  ctx.fillStyle = '#333333';
  ctx.fillRect(monX + 1, monY + 22, 18, 6);
  ctx.fillStyle = '#444444';
  for (let ki = 0; ki < 4; ki++) {
    ctx.fillRect(monX + 3 + ki * 4, monY + 23, 3, 1);
    ctx.fillRect(monX + 3 + ki * 4, monY + 25, 3, 1);
  }
}

function drawSofa(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  // Sofa base
  ctx.fillStyle = '#8B3A3A';
  ctx.fillRect(x + 4, y + 8, pw - 8, ph - 8);
  // Cushion highlight
  ctx.fillStyle = '#A04848';
  ctx.fillRect(x + 6, y + 10, pw - 12, ph - 16);
  // Armrests
  ctx.fillStyle = '#7A2A2A';
  ctx.fillRect(x, y + 4, 8, ph - 4);
  ctx.fillRect(x + pw - 8, y + 4, 8, ph - 4);
  // Back
  ctx.fillStyle = '#6A2222';
  ctx.fillRect(x + 4, y, pw - 8, 12);
  // Cushion lines
  ctx.strokeStyle = '#6A2222';
  ctx.lineWidth = 1;
  const cushionW = (pw - 16) / 3;
  for (let i = 1; i < 3; i++) {
    ctx.beginPath();
    ctx.moveTo(x + 8 + i * cushionW, y + 12);
    ctx.lineTo(x + 8 + i * cushionW, y + ph - 8);
    ctx.stroke();
  }
}

function drawBookshelf(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  // Shelf frame
  ctx.fillStyle = '#5A3A1A';
  ctx.fillRect(x, y, pw, ph);
  // Inner shelves
  ctx.fillStyle = '#7A5A3A';
  ctx.fillRect(x + 2, y + 2, pw - 4, ph - 4);

  // Shelf dividers
  const shelfH = ph / 4;
  ctx.fillStyle = '#5A3A1A';
  for (let i = 1; i < 4; i++) {
    ctx.fillRect(x + 2, y + i * shelfH, pw - 4, 3);
  }

  // Books on shelves
  const bookColors = ['#CC3333', '#3366CC', '#33AA33', '#CC9900', '#9933CC', '#CC6633', '#339999'];
  for (let shelf = 0; shelf < 4; shelf++) {
    let bx = x + 4;
    const by = y + shelf * shelfH + 4;
    const maxBx = x + pw - 6;
    let bookIdx = shelf * 3;
    while (bx < maxBx) {
      const bw = 4 + Math.floor((bookIdx * 7 + shelf * 3) % 4);
      const bh = shelfH - 8;
      ctx.fillStyle = bookColors[bookIdx % bookColors.length];
      ctx.fillRect(bx, by, bw, bh);
      // Book spine highlight
      ctx.fillStyle = 'rgba(255,255,255,0.2)';
      ctx.fillRect(bx, by, 1, bh);
      bx += bw + 1;
      bookIdx++;
    }
  }
}

function drawWhiteboard(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  // Board frame
  ctx.fillStyle = '#555555';
  ctx.fillRect(x, y, pw, ph);
  // White surface
  ctx.fillStyle = '#F0F0E8';
  ctx.fillRect(x + 4, y + 4, pw - 8, ph - 8);
  // Grid lines (kanban columns)
  ctx.strokeStyle = '#CCCCBB';
  ctx.lineWidth = 1;
  const cols = 6;
  for (let i = 1; i < cols; i++) {
    const lx = x + 4 + (i / cols) * (pw - 8);
    ctx.beginPath();
    ctx.moveTo(lx, y + 12);
    ctx.lineTo(lx, y + ph - 8);
    ctx.stroke();
  }
  // Column headers (tiny colored rectangles)
  const headerColors = ['#888', '#4A90D9', '#F5A623', '#9B59B6', '#E74C3C', '#2ECC71'];
  for (let i = 0; i < cols; i++) {
    const hx = x + 6 + (i / cols) * (pw - 8);
    ctx.fillStyle = headerColors[i];
    ctx.fillRect(hx, y + 6, (pw - 16) / cols - 2, 4);
  }
  // Marker tray
  ctx.fillStyle = '#888888';
  ctx.fillRect(x + pw / 4, y + ph - 2, pw / 2, 4);
  // Markers
  ctx.fillStyle = '#CC3333';
  ctx.fillRect(x + pw / 4 + 4, y + ph - 1, 8, 2);
  ctx.fillStyle = '#3366CC';
  ctx.fillRect(x + pw / 4 + 16, y + ph - 1, 8, 2);
  ctx.fillStyle = '#33AA33';
  ctx.fillRect(x + pw / 4 + 28, y + ph - 1, 8, 2);
}

function drawCoffeeMachine(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Table
  ctx.fillStyle = '#6B4226';
  ctx.fillRect(x + 2, y + T, T - 4, T - 4);
  ctx.fillStyle = '#4A2A16';
  ctx.fillRect(x + 2, y + T * 2 - 6, T - 4, 4);

  // Machine body
  ctx.fillStyle = '#333333';
  ctx.fillRect(x + 6, y + 4, T - 12, T - 4);
  // Machine face
  ctx.fillStyle = '#222222';
  ctx.fillRect(x + 8, y + 8, T - 16, 10);
  // Buttons
  ctx.fillStyle = '#FF4444';
  ctx.fillRect(x + 10, y + T - 8, 3, 3);
  ctx.fillStyle = '#44FF44';
  ctx.fillRect(x + 16, y + T - 8, 3, 3);
  // Cup
  ctx.fillStyle = '#EEEEEE';
  ctx.fillRect(x + 10, y + T + 2, 8, 8);
  ctx.fillStyle = '#8B5A2B';
  ctx.fillRect(x + 11, y + T + 3, 6, 5);
}

function drawPlant(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Pot
  ctx.fillStyle = '#AA5533';
  ctx.fillRect(x + 8, y + T + 4, T - 16, T - 8);
  ctx.fillStyle = '#884422';
  ctx.fillRect(x + 6, y + T, T - 12, 6);
  // Soil
  ctx.fillStyle = '#3A2A1A';
  ctx.fillRect(x + 8, y + T + 2, T - 16, 4);
  // Leaves
  ctx.fillStyle = '#228B22';
  ctx.fillRect(x + 4, y + 4, 8, 12);
  ctx.fillRect(x + T - 12, y + 6, 8, 10);
  ctx.fillRect(x + 8, y, 10, 14);
  // Lighter leaves
  ctx.fillStyle = '#44AA44';
  ctx.fillRect(x + 6, y + 6, 4, 6);
  ctx.fillRect(x + T - 8, y + 8, 4, 6);
  ctx.fillRect(x + 12, y + 2, 4, 8);
  // Stem
  ctx.fillStyle = '#1A6B1A';
  ctx.fillRect(x + 14, y + 12, 2, T - 8);
}

function drawCabinet(ctx: CanvasRenderingContext2D, x: number, y: number) {
  const ph = T * 2;
  // Frame
  ctx.fillStyle = '#5A5A6A';
  ctx.fillRect(x + 2, y + 2, T - 4, ph - 4);
  // Drawers
  ctx.fillStyle = '#6A6A7A';
  const drawerH = (ph - 8) / 3;
  for (let i = 0; i < 3; i++) {
    const dy = y + 4 + i * drawerH;
    ctx.fillRect(x + 4, dy, T - 8, drawerH - 2);
    // Handle
    ctx.fillStyle = '#AAAAAA';
    ctx.fillRect(x + T / 2 - 3, dy + drawerH / 2 - 1, 6, 2);
    ctx.fillStyle = '#6A6A7A';
  }
}

function drawRug(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;
  // Rug base
  ctx.fillStyle = '#6B3344';
  ctx.fillRect(x + 4, y + 4, pw - 8, ph - 8);
  // Inner border
  ctx.strokeStyle = '#AA6644';
  ctx.lineWidth = 2;
  ctx.strokeRect(x + 8, y + 8, pw - 16, ph - 16);
  // Center pattern
  ctx.fillStyle = '#8B4455';
  ctx.fillRect(x + 16, y + 16, pw - 32, ph - 32);
  // Diamond pattern in center
  ctx.fillStyle = '#AA6644';
  const cx = x + pw / 2;
  const cy = y + ph / 2;
  ctx.beginPath();
  ctx.moveTo(cx, cy - 16);
  ctx.lineTo(cx + 20, cy);
  ctx.lineTo(cx, cy + 16);
  ctx.lineTo(cx - 20, cy);
  ctx.closePath();
  ctx.fill();
}

function drawWindow(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  const pw = w * T;
  const ph = h * T;

  // Window frame (dark wood)
  ctx.fillStyle = '#5A3A1A';
  ctx.fillRect(x, y, pw, ph);

  // Glass panes (sky view)
  const glassX = x + 4;
  const glassY = y + 4;
  const glassW = pw - 8;
  const glassH = ph - 8;

  // Sky gradient effect
  ctx.fillStyle = '#87CEEB';
  ctx.fillRect(glassX, glassY, glassW, glassH);
  ctx.fillStyle = '#B0E0F0';
  ctx.fillRect(glassX, glassY, glassW, glassH / 3);

  // Clouds
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.fillRect(glassX + 8, glassY + 6, 16, 4);
  ctx.fillRect(glassX + 12, glassY + 4, 8, 8);
  ctx.fillRect(glassX + glassW - 28, glassY + 10, 12, 4);

  // Sun
  ctx.fillStyle = '#FFD700';
  ctx.fillRect(glassX + glassW - 14, glassY + 4, 8, 8);

  // Distant buildings/trees
  ctx.fillStyle = '#6A8A6A';
  ctx.fillRect(glassX + 4, glassY + glassH - 12, 10, 12);
  ctx.fillRect(glassX + 20, glassY + glassH - 8, 8, 8);
  ctx.fillStyle = '#7A7A8A';
  ctx.fillRect(glassX + 34, glassY + glassH - 16, 12, 16);
  ctx.fillRect(glassX + 50, glassY + glassH - 10, 8, 10);

  // Window cross frame
  ctx.fillStyle = '#5A3A1A';
  ctx.fillRect(x + pw / 2 - 1, glassY, 3, glassH);
  ctx.fillRect(glassX, y + ph / 2 - 1, glassW, 3);

  // Curtains (red, simple)
  ctx.fillStyle = '#AA3333';
  ctx.fillRect(x, y, 6, ph);
  ctx.fillRect(x + pw - 6, y, 6, ph);
  // Curtain folds
  ctx.fillStyle = '#882222';
  ctx.fillRect(x + 2, y, 1, ph);
  ctx.fillRect(x + pw - 4, y, 1, ph);
  // Curtain rod
  ctx.fillStyle = '#8B6840';
  ctx.fillRect(x - 2, y - 2, pw + 4, 3);
}

function drawPoster(ctx: CanvasRenderingContext2D, x: number, y: number, type: string) {
  const ph = T * 2;
  // Poster background
  ctx.fillStyle = type === 'poster-ship' ? '#2A4A6A' : '#4A2A4A';
  ctx.fillRect(x + 4, y + 2, T - 8, ph - 4);
  // Border
  ctx.strokeStyle = '#FFFFFF';
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 4, y + 2, T - 8, ph - 4);

  if (type === 'poster-ship') {
    // Rocket
    ctx.fillStyle = '#FF6644';
    ctx.fillRect(x + 12, y + 8, 6, 14);
    ctx.fillStyle = '#FF4422';
    ctx.fillRect(x + 11, y + 18, 8, 6);
    // Flame
    ctx.fillStyle = '#FFD700';
    ctx.fillRect(x + 13, y + 24, 4, 6);
    ctx.fillStyle = '#FF8800';
    ctx.fillRect(x + 14, y + 28, 2, 4);
    // Text
    ctx.fillStyle = '#FFFFFF';
    ctx.font = '4px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('SHIP', x + T / 2, y + ph - 8);
    ctx.fillText('IT!', x + T / 2, y + ph - 3);
  } else {
    // Code brackets
    ctx.fillStyle = '#61DAFB';
    ctx.font = 'bold 10px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('< />', x + T / 2, y + 22);
    ctx.fillStyle = '#FFFFFF';
    ctx.font = '4px monospace';
    ctx.fillText('CODE', x + T / 2, y + ph - 8);
  }
  ctx.textAlign = 'left'; // reset
}

function drawCooler(ctx: CanvasRenderingContext2D, x: number, y: number) {
  // Body
  ctx.fillStyle = '#CCCCDD';
  ctx.fillRect(x + 6, y + 2, T - 12, T * 2 - 6);
  // Top (water jug)
  ctx.fillStyle = '#AADDFF';
  ctx.fillRect(x + 8, y, T - 16, 10);
  ctx.fillStyle = '#88BBEE';
  ctx.fillRect(x + 10, y + 2, T - 20, 6);
  // Tap
  ctx.fillStyle = '#4488CC';
  ctx.fillRect(x + 12, y + 14, 6, 4);
  // Drip tray
  ctx.fillStyle = '#999999';
  ctx.fillRect(x + 8, y + T, T - 16, 3);
}

// ---- Main render functions ----

function drawFurnitureItem(ctx: CanvasRenderingContext2D, f: FurniturePlacement) {
  const x = f.col * T;
  const y = f.row * T;
  const w = f.w ?? 1;
  const h = f.h ?? 1;

  ctx.save();
  switch (f.type) {
    case 'desk': drawDesk(ctx, x, y, w, h); break;
    case 'sofa': drawSofa(ctx, x, y, w, h); break;
    case 'bookshelf': drawBookshelf(ctx, x, y, w, h); break;
    case 'whiteboard': drawWhiteboard(ctx, x, y, w, h); break;
    case 'coffee': drawCoffeeMachine(ctx, x, y); break;
    case 'plant': drawPlant(ctx, x, y); break;
    case 'cabinet': drawCabinet(ctx, x, y); break;
    case 'rug': drawRug(ctx, x, y, w, h); break;
    case 'window': drawWindow(ctx, x, y, w, h); break;
    case 'poster-ship':
    case 'poster-code': drawPoster(ctx, x, y, f.type); break;
    case 'cooler': drawCooler(ctx, x, y); break;
  }
  ctx.restore();
}

/** Render all background layers (floor + walls + furniture behind characters) */
export function renderBackground(ctx: CanvasRenderingContext2D) {
  // Floor tiles
  for (let row = WALL_ROWS; row < MAP_ROWS; row++) {
    for (let col = 0; col < MAP_COLS; col++) {
      drawFloorTile(ctx, col * T, row * T, row, col);
    }
  }

  // Wall tiles
  for (let row = 0; row < WALL_ROWS; row++) {
    for (let col = 0; col < MAP_COLS; col++) {
      drawWallTile(ctx, col * T, row * T, row, col);
    }
  }

  // Draw rug first (below everything)
  for (const f of FURNITURE) {
    if (f.type === 'rug') drawFurnitureItem(ctx, f);
  }

  // Draw wall-mounted items (windows, whiteboard, posters)
  for (const f of FURNITURE) {
    if (['window', 'whiteboard', 'poster-ship', 'poster-code'].includes(f.type)) {
      drawFurnitureItem(ctx, f);
    }
  }
}

/** Render furniture that should appear behind characters (lower parts) */
export function renderFurnitureBehind(ctx: CanvasRenderingContext2D) {
  for (const f of FURNITURE) {
    if (['desk', 'sofa', 'bookshelf', 'coffee', 'plant', 'cabinet', 'cooler'].includes(f.type)) {
      drawFurnitureItem(ctx, f);
    }
  }
}

/** Pre-render the entire background to an offscreen canvas for performance */
export function createBackgroundBuffer(): HTMLCanvasElement {
  const buffer = document.createElement('canvas');
  buffer.width = MAP_COLS * T;
  buffer.height = MAP_ROWS * T;
  const ctx = buffer.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;

  renderBackground(ctx);
  renderFurnitureBehind(ctx);

  return buffer;
}
