/**
 * Main character drawing entry point and shadow
 */

import { CHAR_W, CHAR_H, AGENT_COLORS } from '../sprite-config';
import { getWalkBob, getWalkStride } from './draw-utils';
import { drawLegs, drawBody, drawArms } from './draw-body';
import { drawHead, drawHair, drawAccessory } from './draw-head';

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
  const isWorking = status === 'working';
  const isThinking = status === 'thinking';
  const isError = status === 'error';
  const isWaiting = status === 'waiting';
  const isIdle = status === 'idle';
  const isWalking = status === 'delivering' || status === 'searching';
  const isSitting = isWorking || isThinking || isError || isWaiting;

  const bob = isWalking ? getWalkBob(frame.walkFrame) : 0;
  const stride = isWalking ? getWalkStride(frame.walkFrame) : { left: 0, right: 0 };

  ctx.save();

  if (bob !== 0) {
    ctx.translate(0, bob);
  }

  drawShadow(ctx, isSitting);
  drawLegs(ctx, colors, stride, isIdle, isSitting, isWalking);
  drawBody(ctx, colors, domain, isSitting);
  drawArms(ctx, colors, domain, status, frame.armFrame, isSitting);
  drawHead(ctx, colors, frame.isBlinking, isError, isThinking, isWorking, isIdle, isWaiting);
  drawHair(ctx, colors);
  drawAccessory(ctx, domain, colors, isSitting);

  ctx.restore();
}

function drawShadow(ctx: CanvasRenderingContext2D, isSitting: boolean) {
  ctx.fillStyle = 'rgba(0,0,0,0.25)';
  ctx.beginPath();
  if (isSitting) {
    ctx.ellipse(CHAR_W / 2, CHAR_H - 1, 10, 3, 0, 0, Math.PI * 2);
  } else {
    ctx.ellipse(CHAR_W / 2, CHAR_H - 1, 8, 3, 0, 0, Math.PI * 2);
  }
  ctx.fill();
}
