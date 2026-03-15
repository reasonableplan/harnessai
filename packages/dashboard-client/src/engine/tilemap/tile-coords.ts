/**
 * Tileset coordinate constants for room-builder and modern-interiors/kitchen.
 *
 * All srcX/srcY values are in PIXELS (not tiles).
 * Tile size in source images: 16×16.
 *
 * NOTE: These coordinates are based on visual inspection of the PNG tilesets.
 * If a furniture piece looks wrong, adjust srcX/srcY here.
 */

// ---- Source tile size (all tilesets use 16×16) ----
export const SRC_TILE = 16;

// ---- Room builder dimensions ----
export const RB_COLS = 17; // 272px / 16

// ---- Wall tiles (room-builder, brown wood theme — cols 8-9) ----
// Each row in the wall section represents a different vertical position of the wall.
// We map our 5 wall rows (0-4) to specific tiles in the brown wood columns.
export interface WallTileRow {
  /** Tile col/row in room-builder for the left variant */
  col: number;
  row: number;
}

/** Brown wood wall tiles from room-builder.
 *  Map each of our 5 wall rows to a tile in the tileset.
 *  room-builder cols 0-1: cream/light, cols 2-3: orange, cols 4-5: red, cols 6-7: dark red, cols 8-9: brown wood
 *  Wall rows run from ~row 2 (top) to ~row 10 (wainscoting) */
export const WALL_TILE_ROWS: WallTileRow[] = [
  { col: 0, row: 2 },  // wall row 0: top cap
  { col: 0, row: 3 },  // wall row 1: upper wall
  { col: 0, row: 4 },  // wall row 2: mid wall
  { col: 0, row: 5 },  // wall row 3: lower wall
  { col: 0, row: 7 },  // wall row 4: wainscoting
];

/** Floor tile variants from room-builder (honey wood — cols 4-5, rows 11-14).
 *  Multiple variants for visual variety via seeded random. */
export const FLOOR_TILE_VARIANTS: Array<{ col: number; row: number }> = [
  { col: 4, row: 11 },
  { col: 5, row: 11 },
  { col: 4, row: 12 },
  { col: 5, row: 12 },
  { col: 4, row: 13 },
  { col: 5, row: 13 },
];

// ---- Furniture sprite references (modern-interiors / kitchen) ----

export interface FurnitureSpriteRef {
  tileset: 'modernInteriors' | 'kitchen';
  /** Source pixel coordinates in the tileset image */
  srcX: number;
  srcY: number;
  /** Source pixel dimensions */
  srcW: number;
  srcH: number;
}

/**
 * Furniture type → tileset region mapping.
 * srcX/srcY are pixel coords, srcW/srcH are pixel dimensions.
 *
 * modern-interiors-16x16.png: 256×1424 (16col × 89row)
 *   Approx layout: rows 0-3=appliances, 4-7=beds/bathroom, 8-11=bookshelves,
 *   12-15=rugs, 16-20=cabinets, 21-24=art/posters, 25-30=windows,
 *   31-36=tables, 37-44=school/office desks, 45-50=shelving,
 *   51-56=plants, 65-72=wardrobes, 73-78=sofas
 * kitchen-16x16.png: 144×592 (9col × 37row)
 *   Approx layout: rows 0-3=floors, 4-8=appliances/counters, 13+=chairs
 *
 * NOTE: Coordinates are approximate — adjust srcX/srcY based on visual inspection.
 */
export const FURNITURE_SPRITES: Record<string, FurnitureSpriteRef> = {
  // Computer desk with monitor (3×2 tiles) — office desk section ~row 37-42
  desk: {
    tileset: 'modernInteriors',
    srcX: 4 * 16, srcY: 38 * 16,
    srcW: 3 * 16, srcH: 2 * 16,
  },
  // Sofa/couch (4×2 tiles) — sofa section ~row 73
  sofa: {
    tileset: 'modernInteriors',
    srcX: 0, srcY: 73 * 16,
    srcW: 4 * 16, srcH: 2 * 16,
  },
  // Bookshelf (2×3 tiles) — bookshelf section ~row 8-11
  bookshelf: {
    tileset: 'modernInteriors',
    srcX: 0, srcY: 8 * 16,
    srcW: 2 * 16, srcH: 3 * 16,
  },
  // Corkboard / whiteboard (4×3 tiles) — board section ~row 38-42
  whiteboard: {
    tileset: 'modernInteriors',
    srcX: 8 * 16, srcY: 38 * 16,
    srcW: 4 * 16, srcH: 3 * 16,
  },
  // Coffee machine (1×2 tiles) — kitchen appliances ~row 4-6
  coffee: {
    tileset: 'kitchen',
    srcX: 5 * 16, srcY: 4 * 16,
    srcW: 1 * 16, srcH: 2 * 16,
  },
  // Potted plant large (1×2 tiles) — plant section ~row 51-56
  plant: {
    tileset: 'modernInteriors',
    srcX: 2 * 16, srcY: 51 * 16,
    srcW: 1 * 16, srcH: 2 * 16,
  },
  // Small plant (1×1 tile)
  'plant-small': {
    tileset: 'modernInteriors',
    srcX: 2 * 16, srcY: 53 * 16,
    srcW: 1 * 16, srcH: 1 * 16,
  },
  // Filing cabinet (1×2 tiles) — cabinet section ~row 16-20
  cabinet: {
    tileset: 'modernInteriors',
    srcX: 0, srcY: 16 * 16,
    srcW: 1 * 16, srcH: 2 * 16,
  },
  // Rug / carpet (5×3 tiles) — rug section ~row 12-15
  rug: {
    tileset: 'modernInteriors',
    srcX: 0, srcY: 12 * 16,
    srcW: 5 * 16, srcH: 3 * 16,
  },
  // Window (4×3 tiles) — window section ~row 25-30
  window: {
    tileset: 'modernInteriors',
    srcX: 0, srcY: 25 * 16,
    srcW: 4 * 16, srcH: 3 * 16,
  },
  // Poster — indie style (2×2 tiles) — art/poster section ~row 21-24
  'poster-indie': {
    tileset: 'modernInteriors',
    srcX: 0, srcY: 21 * 16,
    srcW: 2 * 16, srcH: 2 * 16,
  },
  // Poster — jam style (2×2 tiles)
  'poster-jam': {
    tileset: 'modernInteriors',
    srcX: 2 * 16, srcY: 21 * 16,
    srcW: 2 * 16, srcH: 2 * 16,
  },
  // Water cooler (1×2 tiles) — kitchen appliances
  cooler: {
    tileset: 'kitchen',
    srcX: 4 * 16, srcY: 4 * 16,
    srcW: 1 * 16, srcH: 2 * 16,
  },
  // Fireplace (2×3 tiles) — misc furniture ~row 63-66
  fireplace: {
    tileset: 'modernInteriors',
    srcX: 0, srcY: 63 * 16,
    srcW: 2 * 16, srcH: 3 * 16,
  },
  // Fridge (1×3 tiles) — kitchen appliances ~row 4
  fridge: {
    tileset: 'kitchen',
    srcX: 0, srcY: 4 * 16,
    srcW: 1 * 16, srcH: 3 * 16,
  },
};

// ---- Deterministic tile variation ----

/** Simple hash for deterministic per-tile variation (from tile-utils.ts) */
function tileHash(col: number, row: number): number {
  let h = (col * 2654435761) ^ (row * 2246822519);
  h = ((h >>> 16) ^ h) * 0x45d9f3b;
  return (h >>> 0) % FLOOR_TILE_VARIANTS.length;
}

/** Get the floor tile variant for a given map position */
export function getFloorTile(col: number, row: number): { col: number; row: number } {
  const idx = tileHash(col, row);
  return FLOOR_TILE_VARIANTS[idx] ?? FLOOR_TILE_VARIANTS[0]!;
}
