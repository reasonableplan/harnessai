/**
 * Stardew Valley-inspired sprite configuration
 * All position/color/animation constants for the Canvas-based office scene
 */

// Render scale: 2x for higher pixel density (logical 768x512 → physical 1536x1024)
export const RENDER_SCALE = 2;

// Tile size: 32x32 logical, Map: 24x16 tiles
export const TILE_SIZE = 32;
export const MAP_COLS = 24;
export const MAP_ROWS = 16;
export const LOGICAL_W = MAP_COLS * TILE_SIZE; // 768
export const LOGICAL_H = MAP_ROWS * TILE_SIZE; // 512
export const CANVAS_W = LOGICAL_W * RENDER_SCALE; // 1536
export const CANVAS_H = LOGICAL_H * RENDER_SCALE; // 1024

// Character sprite size: 2x of Modern Interiors 16×32 frame
export const CHAR_W = 32;
export const CHAR_H = 64;

// Wall rows (rows 0-4 are wall, 5-15 are floor)
export const WALL_ROWS = 5;

// ---- Agent colors (Stardew Valley-inspired warm palette) ----
export interface AgentColors {
  body: string;
  bodyDark: string;
  accent: string;
  hair: string;
  skin: string;
  skinShadow: string;
  pants: string;
  shoes: string;
  hairStyle: 'short' | 'spiky' | 'long' | 'curly' | 'ponytail';
}

export const AGENT_COLORS: Record<string, AgentColors> = {
  director: {
    body: '#4A3068',     // Royal purple vest
    bodyDark: '#362050',
    accent: '#FFD700',   // Gold star
    hair: '#5C3A1A',     // Warm brown
    skin: '#FFD5B8',
    skinShadow: '#E8B898',
    pants: '#2A2040',
    shoes: '#4A3A2A',
    hairStyle: 'short',
  },
  git: {
    body: '#C04020',     // Warm barn red
    bodyDark: '#A03018',
    accent: '#FF8C55',   // Sunset orange
    hair: '#1C1C1C',
    skin: '#D4A574',
    skinShadow: '#B8885C',
    pants: '#5A4030',
    shoes: '#3A2A1A',
    hairStyle: 'spiky',
  },
  frontend: {
    body: '#2A7A8A',     // Ocean teal
    bodyDark: '#1E5A6A',
    accent: '#5CE0D0',   // Seafoam
    hair: '#8B4513',     // Auburn
    skin: '#FFE0C4',
    skinShadow: '#E8C4A4',
    pants: '#3A4A50',
    shoes: '#4A3A2A',
    hairStyle: 'long',
  },
  backend: {
    body: '#3A7A2E',     // Forest green
    bodyDark: '#2A5A1E',
    accent: '#7CC46A',   // Spring green
    hair: '#2A1A0A',
    skin: '#E8C8A0',
    skinShadow: '#CCA880',
    pants: '#4A4030',
    shoes: '#3A3020',
    hairStyle: 'curly',
  },
  docs: {
    body: '#C4880A',     // Harvest gold
    bodyDark: '#A07008',
    accent: '#FFD54F',   // Sunflower yellow
    hair: '#6B4226',     // Chestnut
    skin: '#FFE4CC',
    skinShadow: '#E8CAB0',
    pants: '#5A4830',
    shoes: '#4A3A28',
    hairStyle: 'ponytail',
  },
};

export const DOMAIN_LABELS: Record<string, string> = {
  director: 'DIR',
  git: 'GIT',
  frontend: 'FE',
  backend: 'BE',
  docs: 'DOC',
};

// ---- Desk slot system (dynamic agent support) ----
export interface DeskSlot {
  desk: { x: number; y: number };
  idle: { x: number; y: number };
}

export const DESK_SLOTS: DeskSlot[] = [
  // Slot 0: Director (center-top boss desk)
  { desk: { x: 384, y: 192 }, idle: { x: 608, y: 432 } },
  // Slot 1: Git (left)
  { desk: { x: 96, y: 272 }, idle: { x: 576, y: 440 } },
  // Slot 2: Frontend (center-left)
  { desk: { x: 256, y: 320 }, idle: { x: 640, y: 432 } },
  // Slot 3: Backend (center-right)
  { desk: { x: 512, y: 272 }, idle: { x: 672, y: 440 } },
  // Slot 4: Docs (right)
  { desk: { x: 640, y: 320 }, idle: { x: 704, y: 432 } },
  // Slot 5: Extra desk (center-lower)
  { desk: { x: 432, y: 352 }, idle: { x: 592, y: 448 } },
  // Slot 6: Extra desk (left-lower)
  { desk: { x: 208, y: 416 }, idle: { x: 624, y: 448 } },
  // Slot 7: Extra desk (right-lower)
  { desk: { x: 560, y: 384 }, idle: { x: 656, y: 448 } },
];

export const BOOKSHELF_POS = { x: 704, y: 280 };

export function getAgentPixelPosition(slotIndex: number, status: string): { x: number; y: number } {
  const slot = DESK_SLOTS[slotIndex] ?? DESK_SLOTS[0];
  switch (status) {
    case 'working':
    case 'thinking':
    case 'error':
    case 'waiting':
      return slot.desk;
    case 'idle':
      return slot.idle;
    case 'searching':
      return {
        x: BOOKSHELF_POS.x - (slotIndex % 3) * 20,
        y: BOOKSHELF_POS.y + Math.floor(slotIndex / 3) * 20,
      };
    case 'delivering': {
      const dir = DESK_SLOTS[0].desk;
      return { x: (slot.desk.x + dir.x) / 2, y: (slot.desk.y + dir.y) / 2 };
    }
    case 'reviewing': {
      const dir = DESK_SLOTS[0].desk;
      // Stagger reviewing agents so they don't overlap
      const offset = slotIndex * 24;
      return { x: dir.x + 40 + (offset % 72), y: dir.y + 16 + Math.floor(offset / 72) * 20 };
    }
    default:
      return slot.desk;
  }
}

/** Get display label for an agent (e.g., "FE", "FE2") */
export function getAgentLabel(id: string, domain: string): string {
  const base = DOMAIN_LABELS[domain] ?? domain.slice(0, 3).toUpperCase();
  if (id === domain) return base;
  const match = id.match(/(\d+)$/);
  if (match) return `${base}${match[1]}`;
  return id.slice(0, 4).toUpperCase();
}

// ---- Furniture tile placements (tile coords) ----
export interface FurniturePlacement {
  type: string;
  col: number;
  row: number;
  w?: number; // width in tiles (default 1)
  h?: number; // height in tiles (default 1)
}

export const FURNITURE: FurniturePlacement[] = [
  // Director desk (center, near wall)
  { type: 'desk', col: 11, row: 5, w: 3, h: 2 },
  // Git desk (left side)
  { type: 'desk', col: 2, row: 8, w: 3, h: 2 },
  // Frontend desk (center-left)
  { type: 'desk', col: 7, row: 9, w: 3, h: 2 },
  // Backend desk (center-right)
  { type: 'desk', col: 15, row: 8, w: 3, h: 2 },
  // Docs desk (right)
  { type: 'desk', col: 19, row: 9, w: 3, h: 2 },
  // Extra desks for dynamic agents (slots 5-7)
  { type: 'desk', col: 12, row: 10, w: 3, h: 2 },
  { type: 'desk', col: 5, row: 12, w: 3, h: 2 },
  { type: 'desk', col: 16, row: 11, w: 3, h: 2 },
  // Sofa (bottom-right)
  { type: 'sofa', col: 18, row: 13, w: 4, h: 2 },
  // Bookshelf (right wall area)
  { type: 'bookshelf', col: 21, row: 5, w: 2, h: 3 },
  // Whiteboard → Corkboard (on wall)
  { type: 'whiteboard', col: 15, row: 1, w: 4, h: 3 },
  // Coffee machine (bottom-left corner)
  { type: 'coffee', col: 1, row: 13, w: 1, h: 2 },
  // Plant (bottom-left)
  { type: 'plant', col: 0, row: 13, w: 1, h: 2 },
  // Filing cabinet
  { type: 'cabinet', col: 5, row: 5, w: 1, h: 2 },
  // Rug (center)
  { type: 'rug', col: 9, row: 12, w: 5, h: 3 },
  // Window on wall
  { type: 'window', col: 3, row: 1, w: 4, h: 3 },
  { type: 'window', col: 9, row: 1, w: 4, h: 3 },
  // Wall decorations
  { type: 'poster-indie', col: 7, row: 1, w: 2, h: 2 },
  { type: 'poster-jam', col: 13, row: 1, w: 2, h: 2 },
  // Water cooler
  { type: 'cooler', col: 23, row: 12, w: 1, h: 2 },
  // Fireplace (left of director area — replaces arcade)
  { type: 'fireplace', col: 8, row: 5, w: 2, h: 3 },
  // Fridge + microwave (left wall area)
  { type: 'fridge', col: 0, row: 8, w: 1, h: 3 },
  // Extra plants
  { type: 'plant', col: 23, row: 5, w: 1, h: 2 },
  { type: 'plant-small', col: 6, row: 5, w: 1, h: 1 },
];
