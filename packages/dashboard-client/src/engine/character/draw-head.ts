/**
 * Character head: face, hair styles, domain accessories
 */

import { CHAR_W as _CHAR_W, type AgentColors } from '../sprite-config';
import { lighten, darken, px, cpx } from './draw-utils';

// ---- Head ----

export function drawHead(
  ctx: CanvasRenderingContext2D,
  c: AgentColors,
  isBlinking: boolean,
  isError: boolean,
  isThinking: boolean,
  isWorking: boolean,
  isIdle: boolean,
  isWaiting: boolean,
) {
  const hx = 9;  // head left x
  const hy = 2;  // head top y
  const hw = 14; // head width
  const hh = 12; // head height

  // ---- Neck (below head, above body) ----
  ctx.fillStyle = c.skin;
  px(ctx, 13, 13, 6, 3);
  cpx(ctx, c.skinShadow, 17, 13, 2, 3);

  // ---- Head shape (rounded rectangle) ----
  ctx.fillStyle = c.skin;
  px(ctx, hx + 1, hy, hw - 2, hh);
  px(ctx, hx, hy + 1, hw, hh - 2);

  // Face shadow (right side, multi-level)
  ctx.fillStyle = c.skinShadow;
  px(ctx, hx + hw - 2, hy + 2, 2, hh - 4);
  ctx.fillStyle = darken(c.skinShadow, 0.1);
  px(ctx, hx + hw - 1, hy + 3, 1, hh - 6);

  // ---- Ears ----
  ctx.fillStyle = c.skin;
  px(ctx, hx - 2, hy + 3, 2, 4);
  px(ctx, hx + hw, hy + 3, 2, 4);
  ctx.fillStyle = c.skinShadow;
  px(ctx, hx - 1, hy + 4, 1, 2);
  px(ctx, hx + hw, hy + 4, 1, 2);

  // ---- Eyes ----
  const eyeY = hy + 5;
  const leftEyeX = hx + 2;
  const rightEyeX = hx + hw - 6;

  if (isBlinking) {
    ctx.fillStyle = '#333333';
    px(ctx, leftEyeX, eyeY + 1, 4, 1);
    px(ctx, rightEyeX, eyeY + 1, 4, 1);
    ctx.fillStyle = '#444444';
    px(ctx, leftEyeX, eyeY + 2, 1, 1);
    px(ctx, leftEyeX + 3, eyeY + 2, 1, 1);
    px(ctx, rightEyeX, eyeY + 2, 1, 1);
    px(ctx, rightEyeX + 3, eyeY + 2, 1, 1);
  } else {
    // White sclera
    ctx.fillStyle = '#FFFFFF';
    px(ctx, leftEyeX, eyeY, 4, 3);
    px(ctx, rightEyeX, eyeY, 4, 3);

    // Eye outline
    ctx.fillStyle = '#444444';
    px(ctx, leftEyeX, eyeY - 1, 4, 1);
    px(ctx, rightEyeX, eyeY - 1, 4, 1);
    ctx.fillStyle = '#555555';
    px(ctx, leftEyeX, eyeY + 3, 4, 1);
    px(ctx, rightEyeX, eyeY + 3, 4, 1);

    // Pupil (2x2)
    ctx.fillStyle = '#222233';
    px(ctx, leftEyeX + 1, eyeY + 1, 2, 2);
    px(ctx, rightEyeX + 1, eyeY + 1, 2, 2);

    // Highlight
    ctx.fillStyle = '#FFFFFF';
    px(ctx, leftEyeX + 1, eyeY, 1, 1);
    px(ctx, rightEyeX + 1, eyeY, 1, 1);
    ctx.fillStyle = 'rgba(255,255,255,0.6)';
    px(ctx, leftEyeX + 3, eyeY + 2, 1, 1);
    px(ctx, rightEyeX + 3, eyeY + 2, 1, 1);
  }

  // ---- Eyebrows ----
  if (isError) {
    ctx.fillStyle = darken(c.hair, 0.2);
    px(ctx, leftEyeX, eyeY - 3, 1, 1);
    px(ctx, leftEyeX + 1, eyeY - 2, 2, 1);
    px(ctx, leftEyeX + 3, eyeY - 2, 1, 1);
    px(ctx, rightEyeX, eyeY - 2, 1, 1);
    px(ctx, rightEyeX + 1, eyeY - 2, 2, 1);
    px(ctx, rightEyeX + 3, eyeY - 3, 1, 1);
  } else if (isThinking) {
    ctx.fillStyle = darken(c.hair, 0.1);
    px(ctx, leftEyeX, eyeY - 2, 4, 1);
    px(ctx, leftEyeX + 1, eyeY - 3, 2, 1);
    px(ctx, rightEyeX, eyeY - 2, 4, 1);
    px(ctx, rightEyeX + 1, eyeY - 3, 2, 1);
  } else if (isWorking) {
    ctx.fillStyle = darken(c.hair, 0.1);
    px(ctx, leftEyeX, eyeY - 2, 4, 1);
    px(ctx, rightEyeX, eyeY - 2, 4, 1);
  } else {
    ctx.fillStyle = darken(c.hair, 0.1);
    px(ctx, leftEyeX, eyeY - 2, 3, 1);
    px(ctx, rightEyeX + 1, eyeY - 2, 3, 1);
  }

  // ---- Nose ----
  ctx.fillStyle = c.skinShadow;
  px(ctx, hx + hw / 2 - 1, hy + 8, 2, 2);
  ctx.fillStyle = lighten(c.skin, 0.1);
  px(ctx, hx + hw / 2 - 1, hy + 8, 1, 1);

  // ---- Mouth ----
  const mouthY = hy + 10;
  const mouthX = hx + hw / 2 - 2;

  if (isError) {
    ctx.fillStyle = '#CC3333';
    px(ctx, mouthX, mouthY + 1, 1, 1);
    px(ctx, mouthX + 1, mouthY, 2, 1);
    px(ctx, mouthX + 3, mouthY + 1, 1, 1);
    ctx.fillStyle = '#FFFFFF';
    px(ctx, mouthX + 1, mouthY + 1, 2, 1);
  } else if (isIdle) {
    ctx.fillStyle = '#AA7755';
    px(ctx, mouthX, mouthY, 1, 1);
    px(ctx, mouthX + 1, mouthY + 1, 2, 1);
    px(ctx, mouthX + 3, mouthY, 1, 1);
  } else if (isWorking) {
    ctx.fillStyle = '#AA7755';
    px(ctx, mouthX + 1, mouthY, 2, 1);
  } else if (isThinking) {
    ctx.fillStyle = '#AA7755';
    px(ctx, mouthX + 1, mouthY, 2, 1);
    ctx.fillStyle = '#996644';
    px(ctx, mouthX + 1, mouthY + 1, 2, 1);
  } else if (isWaiting) {
    ctx.fillStyle = '#AA7755';
    px(ctx, mouthX + 1, mouthY, 2, 2);
    ctx.fillStyle = '#995544';
    px(ctx, mouthX + 1, mouthY + 1, 2, 1);
  } else {
    ctx.fillStyle = '#AA7755';
    px(ctx, mouthX + 1, mouthY, 2, 1);
  }

  // ---- Blush cheeks (idle) ----
  if (isIdle) {
    ctx.fillStyle = 'rgba(255,120,120,0.35)';
    px(ctx, hx + 1, hy + 8, 2, 2);
    px(ctx, hx + hw - 3, hy + 8, 2, 2);
  }

  // ---- Error red tint overlay ----
  if (isError) {
    ctx.fillStyle = 'rgba(200,50,50,0.12)';
    px(ctx, hx, hy + 1, hw, hh - 2);
  }
}

// ---- Hair ----

export function drawHair(ctx: CanvasRenderingContext2D, c: AgentColors) {
  const hx = 9;
  const hy = 2;
  const hw = 14;

  const hairLight = lighten(c.hair, 0.2);
  const hairDark = darken(c.hair, 0.25);

  switch (c.hairStyle) {
    case 'short': {
      ctx.fillStyle = c.hair;
      px(ctx, hx, hy - 2, hw, 5);
      px(ctx, hx + 1, hy - 3, hw - 2, 2);
      px(ctx, hx + 2, hy - 4, hw - 4, 1);
      px(ctx, hx - 1, hy - 1, 2, 5);
      px(ctx, hx + hw - 1, hy - 1, 2, 5);
      ctx.fillStyle = hairLight;
      px(ctx, hx + 3, hy - 3, 3, 1);
      px(ctx, hx + 4, hy - 4, 2, 1);
      px(ctx, hx + 2, hy - 2, 4, 1);
      ctx.fillStyle = hairDark;
      px(ctx, hx, hy + 2, hw, 1);
      px(ctx, hx - 1, hy + 1, 1, 3);
      px(ctx, hx + hw, hy + 1, 1, 3);
      ctx.fillStyle = hairDark;
      px(ctx, hx + 5, hy - 3, 1, 3);
      break;
    }

    case 'spiky': {
      ctx.fillStyle = c.hair;
      px(ctx, hx - 1, hy - 1, hw + 2, 4);
      px(ctx, hx, hy - 2, hw, 2);
      px(ctx, hx - 1, hy - 4, 3, 3);
      px(ctx, hx + 2, hy - 6, 3, 5);
      px(ctx, hx + 5, hy - 7, 2, 6);
      px(ctx, hx + 7, hy - 5, 3, 4);
      px(ctx, hx + 10, hy - 7, 2, 6);
      px(ctx, hx + 12, hy - 5, 2, 4);
      px(ctx, hx + 13, hy - 3, 2, 2);
      ctx.fillStyle = hairLight;
      px(ctx, hx + 2, hy - 6, 1, 2);
      px(ctx, hx + 5, hy - 7, 1, 2);
      px(ctx, hx + 10, hy - 7, 1, 2);
      px(ctx, hx + 7, hy - 5, 1, 2);
      ctx.fillStyle = hairDark;
      px(ctx, hx - 1, hy + 2, hw + 2, 1);
      ctx.fillStyle = c.hair;
      px(ctx, hx - 2, hy, 2, 4);
      px(ctx, hx + hw, hy, 2, 4);
      break;
    }

    case 'long': {
      ctx.fillStyle = c.hair;
      px(ctx, hx + 1, hy - 3, hw - 2, 2);
      px(ctx, hx, hy - 2, hw, 3);
      px(ctx, hx - 1, hy - 1, hw + 2, 4);
      px(ctx, hx + 3, hy - 4, hw - 6, 1);
      px(ctx, hx - 2, hy + 1, 3, 12);
      px(ctx, hx + hw - 1, hy + 1, 3, 12);
      px(ctx, hx - 1, hy + 13, 2, 2);
      px(ctx, hx + hw - 1, hy + 13, 2, 2);
      px(ctx, hx - 1, hy + 2, 2, 8);
      px(ctx, hx + hw - 1, hy + 2, 2, 8);
      ctx.fillStyle = hairLight;
      px(ctx, hx + 4, hy - 3, 4, 1);
      px(ctx, hx + 3, hy - 2, 5, 1);
      px(ctx, hx + 5, hy - 4, 2, 1);
      ctx.fillStyle = hairDark;
      px(ctx, hx - 2, hy + 8, 2, 5);
      px(ctx, hx + hw, hy + 8, 2, 5);
      ctx.fillStyle = hairDark;
      px(ctx, hx + hw / 2, hy - 2, 1, 3);
      ctx.fillStyle = c.hair;
      px(ctx, hx + 1, hy + 1, 4, 2);
      px(ctx, hx + hw - 5, hy + 1, 4, 2);
      ctx.fillStyle = hairLight;
      px(ctx, hx + 2, hy + 1, 2, 1);
      break;
    }

    case 'curly': {
      ctx.fillStyle = c.hair;
      px(ctx, hx - 1, hy - 1, hw + 2, 4);
      px(ctx, hx, hy - 2, hw, 2);
      px(ctx, hx - 2, hy - 3, 4, 3);
      px(ctx, hx + 1, hy - 4, 4, 3);
      px(ctx, hx + 5, hy - 5, 3, 4);
      px(ctx, hx + 8, hy - 4, 4, 3);
      px(ctx, hx + 12, hy - 3, 3, 3);
      px(ctx, hx - 2, hy, 3, 6);
      px(ctx, hx + hw - 1, hy, 3, 6);
      px(ctx, hx - 3, hy + 2, 2, 3);
      px(ctx, hx + hw, hy + 2, 2, 3);
      ctx.fillStyle = hairLight;
      px(ctx, hx + 1, hy - 4, 2, 1);
      px(ctx, hx + 5, hy - 5, 2, 1);
      px(ctx, hx + 9, hy - 4, 2, 1);
      px(ctx, hx - 2, hy + 1, 1, 2);
      px(ctx, hx + hw, hy + 1, 1, 2);
      ctx.fillStyle = hairDark;
      px(ctx, hx + 3, hy - 3, 1, 2);
      px(ctx, hx + 7, hy - 4, 1, 2);
      px(ctx, hx + 11, hy - 3, 1, 2);
      px(ctx, hx - 2, hy + 4, 1, 2);
      px(ctx, hx + hw, hy + 4, 1, 2);
      break;
    }

    case 'ponytail': {
      ctx.fillStyle = c.hair;
      px(ctx, hx, hy - 2, hw, 5);
      px(ctx, hx + 1, hy - 3, hw - 2, 2);
      px(ctx, hx + 3, hy - 4, hw - 6, 1);
      px(ctx, hx, hy + 1, 3, 2);
      px(ctx, hx + hw - 3, hy + 1, 3, 2);
      px(ctx, hx + hw - 2, hy + 1, 3, 3);
      px(ctx, hx + hw + 1, hy + 2, 3, 3);
      px(ctx, hx + hw + 2, hy + 5, 2, 4);
      px(ctx, hx + hw + 2, hy + 9, 2, 3);
      px(ctx, hx + hw + 3, hy + 11, 1, 2);
      ctx.fillStyle = hairLight;
      px(ctx, hx + hw + 1, hy + 2, 1, 2);
      px(ctx, hx + hw + 2, hy + 5, 1, 3);
      ctx.fillStyle = hairDark;
      px(ctx, hx + hw + 3, hy + 3, 1, 2);
      px(ctx, hx + hw + 3, hy + 7, 1, 3);
      ctx.fillStyle = c.accent;
      px(ctx, hx + hw, hy + 3, 2, 2);
      ctx.fillStyle = lighten(c.accent, 0.3);
      px(ctx, hx + hw, hy + 3, 1, 1);
      ctx.fillStyle = hairLight;
      px(ctx, hx + 3, hy - 3, 4, 1);
      px(ctx, hx + 4, hy - 4, 3, 1);
      ctx.fillStyle = hairDark;
      px(ctx, hx, hy + 2, hw, 1);
      break;
    }
  }
}

// ---- Domain Accessories ----

export function drawAccessory(
  ctx: CanvasRenderingContext2D,
  domain: string,
  c: AgentColors,
  isSitting: boolean,
) {
  switch (domain) {
    case 'director': {
      const eyeY = 6;
      ctx.fillStyle = '#DAA520';
      px(ctx, 10, eyeY, 5, 1);
      px(ctx, 10, eyeY + 4, 5, 1);
      px(ctx, 10, eyeY, 1, 5);
      px(ctx, 14, eyeY, 1, 5);
      px(ctx, 17, eyeY, 5, 1);
      px(ctx, 17, eyeY + 4, 5, 1);
      px(ctx, 17, eyeY, 1, 5);
      px(ctx, 21, eyeY, 1, 5);
      px(ctx, 15, eyeY + 1, 2, 1);
      px(ctx, 8, eyeY + 1, 2, 1);
      px(ctx, 22, eyeY + 1, 2, 1);
      ctx.fillStyle = '#111122';
      px(ctx, 11, eyeY + 1, 3, 3);
      px(ctx, 18, eyeY + 1, 3, 3);
      ctx.fillStyle = 'rgba(255,255,255,0.35)';
      px(ctx, 11, eyeY + 1, 2, 1);
      px(ctx, 18, eyeY + 1, 2, 1);
      ctx.fillStyle = 'rgba(255,255,255,0.15)';
      px(ctx, 13, eyeY + 3, 1, 1);
      px(ctx, 20, eyeY + 3, 1, 1);
      ctx.fillStyle = '#FFD700';
      px(ctx, 10, eyeY, 2, 1);
      px(ctx, 17, eyeY, 2, 1);
      break;
    }

    case 'frontend': {
      const eyeY = 6;
      const frameColor = '#61DAFB';
      const frameDark = '#4AABBF';
      ctx.fillStyle = frameColor;
      px(ctx, 10, eyeY, 5, 1);
      px(ctx, 10, eyeY + 3, 5, 1);
      px(ctx, 10, eyeY, 1, 4);
      px(ctx, 14, eyeY, 1, 4);
      px(ctx, 17, eyeY, 5, 1);
      px(ctx, 17, eyeY + 3, 5, 1);
      px(ctx, 17, eyeY, 1, 4);
      px(ctx, 21, eyeY, 1, 4);
      px(ctx, 15, eyeY + 1, 2, 1);
      px(ctx, 8, eyeY + 1, 2, 1);
      px(ctx, 22, eyeY + 1, 2, 1);
      ctx.fillStyle = frameDark;
      px(ctx, 10, eyeY + 3, 5, 1);
      px(ctx, 17, eyeY + 3, 5, 1);
      ctx.fillStyle = 'rgba(97,218,251,0.1)';
      px(ctx, 11, eyeY + 1, 3, 2);
      px(ctx, 18, eyeY + 1, 3, 2);
      break;
    }

    case 'backend': {
      const padColor = '#68A063';
      const padDark = '#4A7A43';
      const bandColor = '#555555';
      const bandLight = '#777777';
      ctx.fillStyle = bandColor;
      px(ctx, 8, -1, 16, 2);
      px(ctx, 10, -2, 12, 1);
      ctx.fillStyle = bandLight;
      px(ctx, 11, -2, 10, 1);
      ctx.fillStyle = padColor;
      px(ctx, 5, 3, 4, 6);
      ctx.fillStyle = padDark;
      px(ctx, 5, 3, 1, 6);
      px(ctx, 5, 8, 4, 1);
      ctx.fillStyle = lighten(padColor, 0.2);
      px(ctx, 6, 4, 2, 4);
      ctx.fillStyle = '#333333';
      px(ctx, 7, 5, 1, 1);
      px(ctx, 7, 7, 1, 1);
      ctx.fillStyle = padColor;
      px(ctx, 23, 3, 4, 6);
      ctx.fillStyle = padDark;
      px(ctx, 26, 3, 1, 6);
      px(ctx, 23, 8, 4, 1);
      ctx.fillStyle = lighten(padColor, 0.2);
      px(ctx, 24, 4, 2, 4);
      ctx.fillStyle = '#333333';
      px(ctx, 24, 5, 1, 1);
      px(ctx, 24, 7, 1, 1);
      break;
    }

    case 'docs': {
      const nbX = isSitting ? 28 : 27;
      const nbY = isSitting ? 22 : 20;
      ctx.fillStyle = '#F7DF1E';
      px(ctx, nbX, nbY, 6, 8);
      ctx.fillStyle = '#C9B100';
      px(ctx, nbX, nbY, 6, 1);
      px(ctx, nbX, nbY, 1, 8);
      px(ctx, nbX, nbY + 7, 6, 1);
      ctx.fillStyle = lighten('#F7DF1E', 0.3);
      px(ctx, nbX + 2, nbY + 1, 3, 1);
      ctx.fillStyle = '#888888';
      px(ctx, nbX + 2, nbY + 3, 3, 1);
      px(ctx, nbX + 2, nbY + 5, 3, 1);
      ctx.fillStyle = '#666666';
      px(ctx, nbX + 2, nbY + 2, 2, 1);
      ctx.fillStyle = '#CC3333';
      px(ctx, nbX + 4, nbY, 1, 2);
      break;
    }
  }
}
