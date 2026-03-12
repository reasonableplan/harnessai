/**
 * Main character drawing entry point — pixel-map sprite system
 * Characters are rendered from 32×48 string grids defined in sprite-data.ts
 */

import { CHAR_W, CHAR_H, AGENT_COLORS } from '../sprite-config';
import { getWalkBob } from './draw-utils';
import { getCharacterSprite, buildPalette, renderSprite, type SpritePatch } from './sprite-data';

export interface CharacterFrame {
  walkFrame: number; // 0-3 for walk cycle
  armFrame: number;  // 0-1 for working arm movement
  isBlinking: boolean;
}

export function drawCharacter(
  ctx: CanvasRenderingContext2D,
  domain: string,
  status: string,
  frame: CharacterFrame,
): void {
  const colors = AGENT_COLORS[domain] ?? AGENT_COLORS.frontend;
  const palette = buildPalette(colors);
  const spriteSet = getCharacterSprite(domain);

  const isWalking = status === 'delivering' || status === 'searching';
  const bob = isWalking ? getWalkBob(frame.walkFrame) : 0;

  ctx.save();
  if (bob !== 0) ctx.translate(0, bob);

  // Build patches for current animation state
  const patches: SpritePatch[] = [];

  if (frame.isBlinking && spriteSet.blinkPatch) {
    patches.push(spriteSet.blinkPatch);
  }

  if (isWalking && spriteSet.walkPatches && spriteSet.walkPatches.length > 0) {
    const walkIdx = frame.walkFrame % spriteSet.walkPatches.length;
    patches.push(spriteSet.walkPatches[walkIdx]);
  }

  if (status === 'working' && spriteSet.workPatches && spriteSet.workPatches.length > 0) {
    const armIdx = frame.armFrame % spriteSet.workPatches.length;
    patches.push(spriteSet.workPatches[armIdx]);
  }

  // Draw ground shadow
  ctx.fillStyle = 'rgba(40,25,10,0.18)';
  ctx.beginPath();
  ctx.ellipse(CHAR_W / 2, CHAR_H - 1, 10, 3, 0, 0, Math.PI * 2);
  ctx.fill();

  // Render the sprite pixel-map
  renderSprite(ctx, spriteSet.base, palette, patches.length > 0 ? patches : undefined);

  ctx.restore();
}
