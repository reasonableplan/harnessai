/**
 * LPC-style sprite configuration
 * All position/color/animation constants for the Canvas-based office scene
 */

// Tile size: 32x32, Map: 24x16 tiles = 768x512 internal resolution
export const TILE_SIZE = 32;
export const MAP_COLS = 24;
export const MAP_ROWS = 16;
export const CANVAS_W = MAP_COLS * TILE_SIZE; // 768
export const CANVAS_H = MAP_ROWS * TILE_SIZE; // 512

// Character sprite size (LPC standard proportions)
export const CHAR_W = 24;
export const CHAR_H = 32;

// Wall rows (rows 0-4 are wall, 5-15 are floor)
export const WALL_ROWS = 5;

// ---- Agent colors (matching original theme) ----
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
    body: '#2C2C54', bodyDark: '#1A1A3E', accent: '#FFD700',
    hair: '#4A3728', skin: '#FFCC99', skinShadow: '#E5B080',
    pants: '#1A1A3E', shoes: '#333344', hairStyle: 'short',
  },
  git: {
    body: '#CC3322', bodyDark: '#AA2211', accent: '#FF7854',
    hair: '#1A1A1A', skin: '#8B6848', skinShadow: '#7A5838',
    pants: '#333344', shoes: '#222233', hairStyle: 'spiky',
  },
  frontend: {
    body: '#20232A', bodyDark: '#15181E', accent: '#61DAFB',
    hair: '#8B4513', skin: '#FFD5B8', skinShadow: '#E8BCA0',
    pants: '#2A3A4A', shoes: '#444455', hairStyle: 'long',
  },
  backend: {
    body: '#2E6B2E', bodyDark: '#1E5A1E', accent: '#68A063',
    hair: '#222222', skin: '#DEB887', skinShadow: '#C8A070',
    pants: '#333344', shoes: '#333333', hairStyle: 'curly',
  },
  docs: {
    body: '#C9A800', bodyDark: '#A08800', accent: '#F7DF1E',
    hair: '#654321', skin: '#FFE0C0', skinShadow: '#E8C8A8',
    pants: '#4A4030', shoes: '#554433', hairStyle: 'ponytail',
  },
};

export const DOMAIN_LABELS: Record<string, string> = {
  director: 'DIR',
  git: 'GIT',
  frontend: 'FE',
  backend: 'BE',
  docs: 'DOC',
};

// ---- Positions (in pixel coords on the 768x512 canvas) ----
export const DESK_POSITIONS: Record<string, { x: number; y: number }> = {
  director: { x: 384, y: 192 },  // center-top, the boss desk
  git:      { x: 96,  y: 272 },
  frontend: { x: 256, y: 320 },
  backend:  { x: 512, y: 272 },
  docs:     { x: 640, y: 320 },
};

export const SOFA_POSITIONS: Record<string, { x: number; y: number }> = {
  director: { x: 608, y: 432 },
  git:      { x: 576, y: 440 },
  frontend: { x: 640, y: 432 },
  backend:  { x: 672, y: 440 },
  docs:     { x: 704, y: 432 },
};

export const BOOKSHELF_POS = { x: 704, y: 280 };

export function getAgentPixelPosition(
  domain: string,
  status: string,
): { x: number; y: number } {
  const desk = DESK_POSITIONS[domain] ?? { x: 384, y: 288 };
  switch (status) {
    case 'working':
    case 'thinking':
    case 'error':
    case 'waiting':
      return desk;
    case 'idle':
      return SOFA_POSITIONS[domain] ?? { x: 640, y: 432 };
    case 'searching':
      return BOOKSHELF_POS;
    case 'delivering':
      return { x: (desk.x + 384) / 2, y: (desk.y + 256) / 2 };
    case 'reviewing': {
      const dir = DESK_POSITIONS.director;
      return { x: dir.x + 40, y: dir.y + 16 };
    }
    default:
      return desk;
  }
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
  // Sofa (bottom-right)
  { type: 'sofa', col: 18, row: 13, w: 4, h: 2 },
  // Bookshelf (right wall area)
  { type: 'bookshelf', col: 21, row: 5, w: 2, h: 3 },
  // Whiteboard (on wall)
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
  // Wall posters
  { type: 'poster-ship', col: 7, row: 2, w: 1, h: 2 },
  { type: 'poster-code', col: 14, row: 2, w: 1, h: 2 },
  // Water cooler
  { type: 'cooler', col: 23, row: 12, w: 1, h: 2 },
];
