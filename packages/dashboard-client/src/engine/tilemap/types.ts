/**
 * Tilemap data types for sprite-based office rendering
 */

/** A placed furniture/object on the map */
export interface FurnitureItem {
  id: string;
  /** Source tileset key (e.g., 'modern-interiors', 'kitchen') */
  tilesetId: string;
  /** Source tile coordinates in the tileset (pixel coords) */
  srcX: number;
  srcY: number;
  /** Size in tiles */
  tileW: number;
  tileH: number;
  /** Placement position on the map (tile coords) */
  col: number;
  row: number;
  /** Depth: 'behind' = drawn before characters, 'front' = drawn after */
  zLayer: 'behind' | 'front';
  /** Optional: marks this furniture as a desk slot for agents */
  deskSlot?: {
    /** Where the agent sits (logical pixel coords) */
    seatX: number;
    seatY: number;
    /** Where the agent idles nearby (logical pixel coords) */
    idleX: number;
    idleY: number;
  };
}

/** Desk slot derived from furniture placements */
export interface DeskSlotDef {
  furnitureId: string;
  seat: { x: number; y: number };
  idle: { x: number; y: number };
}

/** Full tilemap data structure */
export interface TilemapData {
  version: 1;
  /** Map dimensions in tiles */
  width: number;
  height: number;
  /** Source tile size in pixels (16 for our assets) */
  tileSize: number;
  /** Floor layer: 2D array of tile IDs [row][col] — index into room-builder tileset */
  floor: number[][];
  /** Wall layer: 2D array of tile IDs [row][col] */
  walls: number[][];
  /** Object/furniture placements */
  furniture: FurnitureItem[];
  /** Desk slots for agent positioning (derived from furniture with deskSlot) */
  deskSlots: DeskSlotDef[];
  /** Bookshelf/search area position (logical pixels) */
  searchArea: { x: number; y: number };
}

/** Tileset metadata for loading */
export interface TilesetDef {
  id: string;
  src: string;
  tileSize: number;
  /** Number of tile columns in the tileset image */
  cols: number;
}

/** Loaded asset cache */
export interface AssetCache {
  tilesets: Map<string, ImageBitmap>;
  tilesetDefs: Map<string, TilesetDef>;
}
