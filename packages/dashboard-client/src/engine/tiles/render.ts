/**
 * Tile render orchestration: furniture dispatch, background/furniture rendering, buffer creation
 */

import { MAP_COLS, MAP_ROWS, WALL_ROWS, CANVAS_W, CANVAS_H, RENDER_SCALE, FURNITURE, type FurniturePlacement } from '../sprite-config';
import { T } from './tile-utils';
import { drawFloorTile, drawWallTile } from './draw-floor-wall';
import { drawDesk } from './draw-desk';
import {
  drawSofa, drawBookshelf, drawWhiteboard, drawCoffeeMachine,
  drawPlant, drawPlantSmall, drawCabinet, drawRug, drawWindow,
  drawPoster, drawCooler, drawArcade, drawFridge,
} from './draw-furniture';
import { drawFloorCables } from './draw-cables';

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
    case 'plant-small': drawPlantSmall(ctx, x, y); break;
    case 'cabinet': drawCabinet(ctx, x, y); break;
    case 'rug': drawRug(ctx, x, y, w, h); break;
    case 'window': drawWindow(ctx, x, y, w, h); break;
    case 'poster-indie': drawPoster(ctx, x, y, w, h, f.type); break;
    case 'poster-jam': drawPoster(ctx, x, y, w, h, f.type); break;
    case 'cooler': drawCooler(ctx, x, y); break;
    case 'arcade': drawArcade(ctx, x, y, w, h); break;
    case 'fridge': drawFridge(ctx, x, y, w, h); break;
  }
  ctx.restore();
}

/** Render all background layers (floor + walls + rug + wall-mounted items) */
export function renderBackground(ctx: CanvasRenderingContext2D): void {
  for (let row = WALL_ROWS; row < MAP_ROWS; row++) {
    for (let col = 0; col < MAP_COLS; col++) {
      drawFloorTile(ctx, col * T, row * T, row, col);
    }
  }

  for (let row = 0; row < WALL_ROWS; row++) {
    for (let col = 0; col < MAP_COLS; col++) {
      drawWallTile(ctx, col * T, row * T, row, col);
    }
  }

  for (const f of FURNITURE) {
    if (f.type === 'rug') drawFurnitureItem(ctx, f);
  }

  for (const f of FURNITURE) {
    if (['window', 'whiteboard', 'poster-indie', 'poster-jam'].includes(f.type)) {
      drawFurnitureItem(ctx, f);
    }
  }
}

/** Render furniture that should appear behind (and around) characters */
export function renderFurnitureBehind(ctx: CanvasRenderingContext2D): void {
  for (const f of FURNITURE) {
    if (['desk', 'sofa', 'bookshelf', 'coffee', 'plant', 'plant-small', 'cabinet', 'cooler', 'arcade', 'fridge'].includes(f.type)) {
      drawFurnitureItem(ctx, f);
    }
  }

  drawFloorCables(ctx);
}

/** Pre-render the entire background to an offscreen canvas for performance */
export function createBackgroundBuffer(): HTMLCanvasElement {
  const buffer = document.createElement('canvas');
  buffer.width = CANVAS_W;
  buffer.height = CANVAS_H;
  const ctx = buffer.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;
  ctx.scale(RENDER_SCALE, RENDER_SCALE);
  renderBackground(ctx);
  renderFurnitureBehind(ctx);
  return buffer;
}
