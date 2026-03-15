/**
 * Tileset-based background renderer.
 * Replaces procedural draw-* functions with drawImage() from tileset PNGs.
 */

import {
  TILE_SIZE, MAP_COLS, MAP_ROWS, WALL_ROWS,
  CANVAS_W, CANVAS_H, RENDER_SCALE,
  FURNITURE, type FurniturePlacement,
} from '../sprite-config';
import type { TilesetCache } from './tileset-loader';
import {
  SRC_TILE, WALL_TILE_ROWS, FURNITURE_SPRITES,
  getFloorTile,
} from './tile-coords';

// ---- Floor rendering ----

function renderFloor(
  ctx: CanvasRenderingContext2D,
  roomBuilder: HTMLImageElement,
): void {
  for (let row = WALL_ROWS; row < MAP_ROWS; row++) {
    for (let col = 0; col < MAP_COLS; col++) {
      const tile = getFloorTile(col, row);
      ctx.drawImage(
        roomBuilder,
        tile.col * SRC_TILE, tile.row * SRC_TILE, SRC_TILE, SRC_TILE,
        col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE,
      );
    }
  }
}

// ---- Wall rendering ----

function renderWalls(
  ctx: CanvasRenderingContext2D,
  roomBuilder: HTMLImageElement,
): void {
  for (let row = 0; row < WALL_ROWS; row++) {
    const tileRef = WALL_TILE_ROWS[row] ?? WALL_TILE_ROWS[0]!;
    for (let col = 0; col < MAP_COLS; col++) {
      ctx.drawImage(
        roomBuilder,
        tileRef.col * SRC_TILE, tileRef.row * SRC_TILE, SRC_TILE, SRC_TILE,
        col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE,
      );
    }
  }
}

// ---- Furniture rendering ----

/** Render order groups matching the procedural renderer */
const WALL_MOUNTED = new Set(['window', 'whiteboard', 'poster-indie', 'poster-jam']);
const BEHIND_CHARS = new Set([
  'desk', 'sofa', 'bookshelf', 'coffee', 'plant', 'plant-small',
  'cabinet', 'cooler', 'fireplace', 'fridge',
]);

function renderFurnitureItem(
  ctx: CanvasRenderingContext2D,
  cache: TilesetCache,
  f: FurniturePlacement,
): void {
  const sprite = FURNITURE_SPRITES[f.type];
  if (!sprite) return;

  const img = cache[sprite.tileset];
  if (!img) return;

  const destX = f.col * TILE_SIZE;
  const destY = f.row * TILE_SIZE;
  const destW = (f.w ?? 1) * TILE_SIZE;
  const destH = (f.h ?? 1) * TILE_SIZE;

  ctx.drawImage(
    img,
    sprite.srcX, sprite.srcY, sprite.srcW, sprite.srcH,
    destX, destY, destW, destH,
  );
}

function renderFurnitureGroup(
  ctx: CanvasRenderingContext2D,
  cache: TilesetCache,
  filter: Set<string>,
): void {
  for (const f of FURNITURE) {
    if (filter.has(f.type)) {
      renderFurnitureItem(ctx, cache, f);
    }
  }
}

// ---- Main entry point ----

/**
 * Create a pre-rendered background buffer using tileset images.
 * Returns null if the room-builder tileset (floor/wall) failed to load.
 *
 * Render order (matches procedural renderer):
 * 1. Floor tiles
 * 2. Wall tiles
 * 3. Rugs (behind everything)
 * 4. Wall-mounted items (windows, whiteboards, posters)
 * 5. Furniture behind characters (desks, sofas, plants, etc.)
 */
export function createTilesetBackgroundBuffer(cache: TilesetCache): HTMLCanvasElement | null {
  if (!cache.roomBuilder) return null;

  const buffer = document.createElement('canvas');
  buffer.width = CANVAS_W;
  buffer.height = CANVAS_H;
  const ctx = buffer.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;

  // Scale context so we draw in logical coords (TILE_SIZE=32)
  // Source tiles are 16px, destination tiles are 32px — handled by drawImage dest size
  ctx.scale(RENDER_SCALE, RENDER_SCALE);

  // Base fill so canvas is never fully transparent
  ctx.fillStyle = '#C8A66B'; // honey wood
  ctx.fillRect(0, WALL_ROWS * TILE_SIZE, MAP_COLS * TILE_SIZE, (MAP_ROWS - WALL_ROWS) * TILE_SIZE);
  ctx.fillStyle = '#7A6548'; // brown wall
  ctx.fillRect(0, 0, MAP_COLS * TILE_SIZE, WALL_ROWS * TILE_SIZE);

  // 1. Floor
  renderFloor(ctx, cache.roomBuilder);

  // 2. Walls
  renderWalls(ctx, cache.roomBuilder);

  // 3. Rugs
  for (const f of FURNITURE) {
    if (f.type === 'rug') renderFurnitureItem(ctx, cache, f);
  }

  // 4. Wall-mounted
  renderFurnitureGroup(ctx, cache, WALL_MOUNTED);

  // 5. Furniture behind characters
  renderFurnitureGroup(ctx, cache, BEHIND_CHARS);

  return buffer;
}
