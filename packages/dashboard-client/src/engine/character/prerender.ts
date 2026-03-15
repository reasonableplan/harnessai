/**
 * Pre-render character frames to offscreen canvases for performance.
 * Uses image sprites from Modern Interiors when available, falls back to pixel-map.
 */

import { CHAR_W, CHAR_H, RENDER_SCALE } from '../sprite-config';
import {
  loadAllSprites,
  getSpriteFrame,
  SPRITE_FRAME_W,
  SPRITE_FRAME_H,
  type SpriteCollection,
} from './sprite-loader';
import { drawCharacter } from './draw-character';

const PADDING = 16;

/** Pixel-map grid dimensions (from sprite-data.ts) */
const PIXMAP_W = 32;
const PIXMAP_H = 48;

/** Shared sprite collection (available after async load) */
let spriteCollection: SpriteCollection | null = null;

/** Get the loaded sprite collection (for use by UI components) */
export function getSpriteCollection(): SpriteCollection | null {
  return spriteCollection;
}

/**
 * Async: load image sprites from Modern Interiors, then build frame cache.
 */
export async function prerenderCharactersAsync(): Promise<Map<string, HTMLCanvasElement[]>> {
  spriteCollection = await loadAllSprites();
  return buildCache(spriteCollection);
}

/**
 * Sync fallback: builds cache using pixel-map rendering (no image sprites).
 */
export function prerenderCharacters(): Map<string, HTMLCanvasElement[]> {
  return buildCache(null);
}

/**
 * Rebuild cache with updated assignments (call after user changes character)
 */
export function rebuildCache(): Map<string, HTMLCanvasElement[]> {
  return buildCache(spriteCollection);
}

/** Draw a sprite frame (16×32 source) scaled to fill CHAR_W×CHAR_H, centered with padding */
function renderSpriteFrame(
  ctx: CanvasRenderingContext2D,
  frame: HTMLCanvasElement,
  canvasW: number,
  canvasH: number,
): void {
  const drawW = CHAR_W * RENDER_SCALE;
  const drawH = CHAR_H * RENDER_SCALE;
  const offsetX = (canvasW - drawW) / 2;
  const offsetY = canvasH - drawH - (PADDING / 2) * RENDER_SCALE; // align bottom
  ctx.drawImage(
    frame,
    0, 0, SPRITE_FRAME_W, SPRITE_FRAME_H,
    offsetX, offsetY, drawW, drawH,
  );
}

/** Draw pixel-map fallback (32×48 grid) centered in the prerender canvas */
function renderPixelMap(
  ctx: CanvasRenderingContext2D,
  domain: string,
  status: string,
  walkFrame: number,
  armFrame: number,
  isBlinking: boolean,
): void {
  ctx.save();
  ctx.scale(RENDER_SCALE, RENDER_SCALE);
  // Center 32×48 pixel map horizontally, align bottom with padding
  const offsetX = (CHAR_W + PADDING - PIXMAP_W) / 2;
  const offsetY = PADDING / 2 + (CHAR_H - PIXMAP_H);
  ctx.translate(offsetX, offsetY);
  drawCharacter(ctx, domain, status, { walkFrame, armFrame, isBlinking });
  ctx.restore();
}

function buildCache(
  collection: SpriteCollection | null,
): Map<string, HTMLCanvasElement[]> {
  const cache = new Map<string, HTMLCanvasElement[]>();
  const domains = ['director', 'orchestration', 'git', 'frontend', 'backend', 'docs'];
  const statuses = [
    'idle', 'working', 'thinking', 'error',
    'waiting', 'searching', 'delivering', 'reviewing',
  ];

  const canvasW = (CHAR_W + PADDING) * RENDER_SCALE;
  const canvasH = (CHAR_H + PADDING) * RENDER_SCALE;

  for (const domain of domains) {
    for (const status of statuses) {
      const frames: HTMLCanvasElement[] = [];
      const walkFrames = status === 'delivering' || status === 'searching' ? 4 : 1;
      const deskFrames = status === 'working' || status === 'thinking' || status === 'waiting' ? 6 : 1;
      const totalFrames = Math.max(walkFrames, deskFrames);

      for (let i = 0; i < totalFrames; i++) {
        const canvas = document.createElement('canvas');
        canvas.width = canvasW;
        canvas.height = canvasH;
        const fCtx = canvas.getContext('2d')!;
        fCtx.imageSmoothingEnabled = false;

        const spriteFrame = collection
          ? getSpriteFrame(collection, domain, status, i)
          : null;

        if (spriteFrame) {
          renderSpriteFrame(fCtx, spriteFrame, canvasW, canvasH);
        } else {
          renderPixelMap(fCtx, domain, status, i % walkFrames, i % deskFrames, false);
        }

        frames.push(canvas);
      }

      // Blink frame (last frame in array)
      const blinkCanvas = document.createElement('canvas');
      blinkCanvas.width = canvasW;
      blinkCanvas.height = canvasH;
      const bCtx = blinkCanvas.getContext('2d')!;
      bCtx.imageSmoothingEnabled = false;

      const blinkSprite = collection
        ? getSpriteFrame(collection, domain, status, 0)
        : null;

      if (blinkSprite) {
        // Image sprites don't have separate blink frames — reuse idle frame
        renderSpriteFrame(bCtx, blinkSprite, canvasW, canvasH);
      } else {
        renderPixelMap(bCtx, domain, status, 0, 0, true);
      }
      frames.push(blinkCanvas);

      cache.set(`${domain}:${status}`, frames);
    }
  }

  return cache;
}
