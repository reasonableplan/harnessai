/**
 * Pre-render character frames to offscreen canvases for performance
 */

import { CHAR_W, CHAR_H, RENDER_SCALE } from '../sprite-config';
import { drawCharacter } from './draw-character';

export function prerenderCharacters(): Map<string, HTMLCanvasElement[]> {
  const cache = new Map<string, HTMLCanvasElement[]>();
  const domains = ['director', 'git', 'frontend', 'backend', 'docs'];
  const statuses = ['idle', 'working', 'thinking', 'error', 'waiting', 'searching', 'delivering', 'reviewing'];

  const canvasW = (CHAR_W + 16) * RENDER_SCALE;
  const canvasH = (CHAR_H + 16) * RENDER_SCALE;

  for (const domain of domains) {
    for (const status of statuses) {
      const frames: HTMLCanvasElement[] = [];
      const walkFrames = (status === 'delivering' || status === 'searching') ? 4 : 1;
      const armFrames = status === 'working' ? 2 : 1;
      const totalFrames = Math.max(walkFrames, armFrames);

      for (let i = 0; i < totalFrames; i++) {
        const canvas = document.createElement('canvas');
        canvas.width = canvasW;
        canvas.height = canvasH;
        const fCtx = canvas.getContext('2d')!;
        fCtx.imageSmoothingEnabled = false;

        fCtx.scale(RENDER_SCALE, RENDER_SCALE);
        fCtx.save();
        fCtx.translate(8, 12); // padding: 8px left, 12px top for tall hair (spiky)
        drawCharacter(fCtx, domain, status, {
          walkFrame: i % walkFrames,
          armFrame: i % armFrames,
          isBlinking: false,
        });
        fCtx.restore();

        frames.push(canvas);
      }

      // Blink frame (same as frame 0 but blinking) — last in array
      const blinkCanvas = document.createElement('canvas');
      blinkCanvas.width = canvasW;
      blinkCanvas.height = canvasH;
      const bCtx = blinkCanvas.getContext('2d')!;
      bCtx.imageSmoothingEnabled = false;
      bCtx.scale(RENDER_SCALE, RENDER_SCALE);
      bCtx.save();
      bCtx.translate(8, 12);
      drawCharacter(bCtx, domain, status, {
        walkFrame: 0,
        armFrame: 0,
        isBlinking: true,
      });
      bCtx.restore();
      frames.push(blinkCanvas);

      cache.set(`${domain}:${status}`, frames);
    }
  }

  return cache;
}
