/**
 * Character body parts: legs, torso, shirt detail, arms
 */

import type { AgentColors } from '../sprite-config';
import { lighten, darken, px, cpx } from './draw-utils';

// ---- Legs ----

export function drawLegs(
  ctx: CanvasRenderingContext2D,
  c: AgentColors,
  stride: { left: number; right: number },
  isIdle: boolean,
  isSitting: boolean,
  isWalking: boolean,
) {
  const pantsHighlight = lighten(c.pants, 0.15);
  const pantsShadow = darken(c.pants, 0.2);
  const shoesHighlight = lighten(c.shoes, 0.2);

  if (isSitting) {
    // ---- SITTING POSE: thighs horizontal, calves hanging down ----
    const thighY = 32;
    const calfY = 37;

    // Left thigh (horizontal)
    ctx.fillStyle = c.pants;
    px(ctx, 8, thighY, 6, 4);
    ctx.fillStyle = pantsHighlight;
    px(ctx, 8, thighY, 6, 1); // top highlight
    ctx.fillStyle = pantsShadow;
    px(ctx, 8, thighY + 3, 6, 1); // bottom shadow

    // Right thigh (horizontal)
    ctx.fillStyle = c.pants;
    px(ctx, 18, thighY, 6, 4);
    ctx.fillStyle = pantsHighlight;
    px(ctx, 18, thighY, 6, 1);
    ctx.fillStyle = pantsShadow;
    px(ctx, 18, thighY + 3, 6, 1);

    // Knee shadow (darker at bend)
    ctx.fillStyle = pantsShadow;
    px(ctx, 13, thighY + 1, 1, 3);
    px(ctx, 17, thighY + 1, 1, 3);

    // Left calf (vertical, hanging)
    ctx.fillStyle = c.pants;
    px(ctx, 9, calfY, 4, 7);
    ctx.fillStyle = pantsShadow;
    px(ctx, 12, calfY, 1, 6); // right shadow on calf

    // Right calf (vertical, hanging)
    ctx.fillStyle = c.pants;
    px(ctx, 19, calfY, 4, 7);
    ctx.fillStyle = pantsShadow;
    px(ctx, 22, calfY, 1, 6);

    // Shoes (dangling)
    ctx.fillStyle = c.shoes;
    px(ctx, 8, calfY + 7, 6, 2);
    px(ctx, 18, calfY + 7, 6, 2);
    ctx.fillStyle = shoesHighlight;
    px(ctx, 9, calfY + 7, 4, 1);
    px(ctx, 19, calfY + 7, 4, 1);
    // Shoe soles
    ctx.fillStyle = darken(c.shoes, 0.3);
    px(ctx, 8, calfY + 8, 6, 1);
    px(ctx, 18, calfY + 8, 6, 1);
  } else if (isIdle) {
    // ---- IDLE: relaxed standing, legs together ----
    const legY = 33;
    const legH = 11;

    // Left leg
    ctx.fillStyle = c.pants;
    px(ctx, 10, legY, 5, legH);
    ctx.fillStyle = pantsHighlight;
    px(ctx, 10, legY, 2, legH - 2);
    ctx.fillStyle = pantsShadow;
    px(ctx, 14, legY + 2, 1, legH - 4); // inner shadow
    // Knee shadow
    ctx.fillStyle = pantsShadow;
    px(ctx, 11, legY + 5, 3, 1);

    // Right leg
    ctx.fillStyle = c.pants;
    px(ctx, 17, legY, 5, legH);
    ctx.fillStyle = pantsHighlight;
    px(ctx, 17, legY, 2, legH - 2);
    ctx.fillStyle = pantsShadow;
    px(ctx, 21, legY + 2, 1, legH - 4);
    ctx.fillStyle = pantsShadow;
    px(ctx, 18, legY + 5, 3, 1);

    // Gap between legs
    ctx.fillStyle = pantsShadow;
    px(ctx, 15, legY + 1, 2, legH - 2);

    // Shoes
    ctx.fillStyle = c.shoes;
    px(ctx, 9, legY + legH, 6, 3);
    px(ctx, 17, legY + legH, 6, 3);
    // Shoe highlight
    ctx.fillStyle = shoesHighlight;
    px(ctx, 10, legY + legH, 4, 1);
    px(ctx, 18, legY + legH, 4, 1);
    // Shoe soles
    ctx.fillStyle = darken(c.shoes, 0.3);
    px(ctx, 9, legY + legH + 2, 6, 1);
    px(ctx, 17, legY + legH + 2, 6, 1);
  } else if (isWalking) {
    // ---- WALKING: animated stride ----
    const legY = 33;
    const legH = 10;

    // Left leg with stride offset
    ctx.fillStyle = c.pants;
    px(ctx, 10 + stride.left, legY, 5, legH);
    ctx.fillStyle = pantsHighlight;
    px(ctx, 10 + stride.left, legY, 2, legH - 2);
    ctx.fillStyle = pantsShadow;
    px(ctx, 14 + stride.left, legY + 2, 1, legH - 3);

    // Right leg with stride offset
    ctx.fillStyle = c.pants;
    px(ctx, 17 + stride.right, legY, 5, legH);
    ctx.fillStyle = pantsHighlight;
    px(ctx, 17 + stride.right, legY, 2, legH - 2);
    ctx.fillStyle = pantsShadow;
    px(ctx, 21 + stride.right, legY + 2, 1, legH - 3);

    // Shoes
    ctx.fillStyle = c.shoes;
    px(ctx, 9 + stride.left, legY + legH, 6, 3);
    px(ctx, 16 + stride.right, legY + legH, 6, 3);
    ctx.fillStyle = shoesHighlight;
    px(ctx, 10 + stride.left, legY + legH, 4, 1);
    px(ctx, 17 + stride.right, legY + legH, 4, 1);
    ctx.fillStyle = darken(c.shoes, 0.3);
    px(ctx, 9 + stride.left, legY + legH + 2, 6, 1);
    px(ctx, 16 + stride.right, legY + legH + 2, 6, 1);
  } else {
    // ---- DEFAULT STANDING ----
    const legY = 33;
    const legH = 11;

    // Left leg
    ctx.fillStyle = c.pants;
    px(ctx, 10, legY, 5, legH);
    ctx.fillStyle = pantsHighlight;
    px(ctx, 10, legY, 2, legH - 2);
    ctx.fillStyle = pantsShadow;
    px(ctx, 14, legY + 2, 1, legH - 4);
    ctx.fillStyle = pantsShadow;
    px(ctx, 11, legY + 5, 3, 1);

    // Right leg
    ctx.fillStyle = c.pants;
    px(ctx, 17, legY, 5, legH);
    ctx.fillStyle = pantsHighlight;
    px(ctx, 17, legY, 2, legH - 2);
    ctx.fillStyle = pantsShadow;
    px(ctx, 21, legY + 2, 1, legH - 4);
    ctx.fillStyle = pantsShadow;
    px(ctx, 18, legY + 5, 3, 1);

    // Gap
    ctx.fillStyle = pantsShadow;
    px(ctx, 15, legY + 1, 2, legH - 2);

    // Shoes
    ctx.fillStyle = c.shoes;
    px(ctx, 9, legY + legH, 6, 3);
    px(ctx, 17, legY + legH, 6, 3);
    ctx.fillStyle = shoesHighlight;
    px(ctx, 10, legY + legH, 4, 1);
    px(ctx, 18, legY + legH, 4, 1);
    ctx.fillStyle = darken(c.shoes, 0.3);
    px(ctx, 9, legY + legH + 2, 6, 1);
    px(ctx, 17, legY + legH + 2, 6, 1);
  }
}

// ---- Body / Torso ----

export function drawBody(
  ctx: CanvasRenderingContext2D,
  c: AgentColors,
  domain: string,
  isSitting: boolean,
) {
  const bodyY = 16;
  const bodyH = 17;
  const bodyHighlight = lighten(c.body, 0.15);
  const bodyDarker = darken(c.bodyDark, 0.15);

  // ---- Neck ----
  ctx.fillStyle = c.skin;
  px(ctx, 13, 14, 6, 4);
  cpx(ctx, c.skinShadow, 17, 15, 2, 3); // neck shadow right

  // ---- Shoulders & Torso ----
  ctx.fillStyle = c.body;
  px(ctx, 6, bodyY, 20, 2); // wide shoulders
  cpx(ctx, 'rgba(0,0,0,0)', 6, bodyY, 1, 1);
  ctx.fillStyle = c.body;
  px(ctx, 7, bodyY, 18, 1); // top row slightly narrower
  px(ctx, 6, bodyY + 1, 20, 1); // full width row

  // Main torso
  ctx.fillStyle = c.body;
  px(ctx, 7, bodyY + 2, 18, bodyH - 4);

  // Torso highlight (left side)
  ctx.fillStyle = bodyHighlight;
  px(ctx, 8, bodyY + 2, 3, bodyH - 6);

  // Torso shadow (right side)
  ctx.fillStyle = c.bodyDark;
  px(ctx, 21, bodyY + 2, 4, bodyH - 5);
  ctx.fillStyle = bodyDarker;
  px(ctx, 23, bodyY + 3, 2, bodyH - 7);

  // ---- Collar / neckline with accent ----
  ctx.fillStyle = c.accent;
  px(ctx, 13, bodyY, 1, 2);
  px(ctx, 14, bodyY, 4, 1);
  px(ctx, 18, bodyY, 1, 2);
  ctx.fillStyle = darken(c.accent, 0.2);
  px(ctx, 14, bodyY + 1, 4, 1);

  // ---- Belt at waist ----
  const beltY = bodyY + bodyH - 2;
  ctx.fillStyle = darken(c.bodyDark, 0.3);
  px(ctx, 7, beltY, 18, 2);
  ctx.fillStyle = darken(c.bodyDark, 0.1);
  px(ctx, 7, beltY, 18, 1);
  ctx.fillStyle = c.accent;
  px(ctx, 14, beltY, 4, 2);
  ctx.fillStyle = lighten(c.accent, 0.3);
  px(ctx, 15, beltY, 2, 1);

  // ---- Domain-specific shirt detail ----
  drawShirtDetail(ctx, domain, c, bodyY);

  // ---- Bottom of torso (tuck into pants) ----
  if (isSitting) {
    ctx.fillStyle = c.body;
    px(ctx, 8, bodyY + bodyH, 16, 1);
  }
}

function drawShirtDetail(
  ctx: CanvasRenderingContext2D,
  domain: string,
  c: AgentColors,
  bodyY: number,
) {
  const cx = 16; // center x
  const dy = bodyY + 6; // detail y center

  switch (domain) {
    case 'git': {
      ctx.fillStyle = c.accent;
      px(ctx, cx - 2, dy, 1, 5);
      px(ctx, cx - 1, dy + 3, 3, 1);
      px(ctx, cx + 1, dy + 1, 1, 3);
      ctx.fillStyle = lighten(c.accent, 0.3);
      px(ctx, cx - 2, dy, 1, 1);
      px(ctx, cx + 1, dy + 1, 1, 1);
      px(ctx, cx - 2, dy + 4, 1, 1);
      break;
    }
    case 'frontend': {
      ctx.fillStyle = c.accent;
      px(ctx, cx - 1, dy + 1, 3, 1);
      px(ctx, cx, dy, 1, 3);
      ctx.fillStyle = lighten(c.accent, 0.4);
      px(ctx, cx - 2, dy, 1, 1);
      px(ctx, cx + 2, dy + 2, 1, 1);
      break;
    }
    case 'backend': {
      ctx.fillStyle = c.accent;
      px(ctx, cx - 2, dy, 5, 1);
      px(ctx, cx - 2, dy + 2, 5, 1);
      px(ctx, cx - 2, dy + 4, 5, 1);
      px(ctx, cx - 2, dy, 1, 5);
      px(ctx, cx + 2, dy, 1, 5);
      ctx.fillStyle = lighten(c.accent, 0.5);
      px(ctx, cx - 1, dy + 1, 1, 1);
      px(ctx, cx - 1, dy + 3, 1, 1);
      break;
    }
    case 'docs': {
      ctx.fillStyle = c.accent;
      px(ctx, cx - 2, dy, 4, 5);
      ctx.fillStyle = darken(c.accent, 0.2);
      px(ctx, cx - 1, dy + 1, 2, 1);
      px(ctx, cx - 1, dy + 3, 2, 1);
      ctx.fillStyle = lighten(c.accent, 0.3);
      px(ctx, cx + 1, dy, 1, 1);
      break;
    }
    case 'director': {
      ctx.fillStyle = c.accent;
      px(ctx, cx, dy, 1, 1);
      px(ctx, cx - 2, dy + 1, 5, 1);
      px(ctx, cx - 1, dy + 2, 3, 1);
      ctx.fillStyle = lighten(c.accent, 0.4);
      px(ctx, cx, dy, 1, 1);
      break;
    }
  }
}

// ---- Arms ----

export function drawArms(
  ctx: CanvasRenderingContext2D,
  c: AgentColors,
  _domain: string,
  status: string,
  armFrame: number,
  _isSitting: boolean,
) {
  const armY = 17;
  const sleeveColor = c.body;
  const sleeveShadow = c.bodyDark;
  const handColor = c.skin;
  const handShadow = c.skinShadow;

  if (status === 'working') {
    // ---- TYPING: arms forward, alternating bob ----
    const offsetL = armFrame === 0 ? 0 : -1;
    const offsetR = armFrame === 0 ? -1 : 0;

    ctx.fillStyle = sleeveColor;
    px(ctx, 2, armY + offsetL, 5, 7);
    ctx.fillStyle = sleeveShadow;
    px(ctx, 2, armY + offsetL, 1, 6);
    px(ctx, 6, armY + 1 + offsetL, 1, 5);
    ctx.fillStyle = handColor;
    px(ctx, 3, armY + 7 + offsetL, 4, 3);
    ctx.fillStyle = handShadow;
    px(ctx, 3, armY + 9 + offsetL, 4, 1);
    ctx.fillStyle = handShadow;
    px(ctx, 4, armY + 8 + offsetL, 1, 1);

    ctx.fillStyle = sleeveColor;
    px(ctx, 25, armY + offsetR, 5, 7);
    ctx.fillStyle = sleeveShadow;
    px(ctx, 29, armY + offsetR, 1, 6);
    px(ctx, 25, armY + 1 + offsetR, 1, 5);
    ctx.fillStyle = handColor;
    px(ctx, 25, armY + 7 + offsetR, 4, 3);
    ctx.fillStyle = handShadow;
    px(ctx, 25, armY + 9 + offsetR, 4, 1);
    ctx.fillStyle = handShadow;
    px(ctx, 27, armY + 8 + offsetR, 1, 1);

  } else if (status === 'thinking') {
    // ---- THINKING: left arm down, right arm up to chin ----
    ctx.fillStyle = sleeveColor;
    px(ctx, 2, armY, 5, 8);
    ctx.fillStyle = sleeveShadow;
    px(ctx, 2, armY, 1, 7);
    ctx.fillStyle = handColor;
    px(ctx, 3, armY + 8, 4, 3);
    ctx.fillStyle = handShadow;
    px(ctx, 3, armY + 10, 4, 1);

    ctx.fillStyle = sleeveColor;
    px(ctx, 25, armY - 3, 5, 8);
    ctx.fillStyle = sleeveShadow;
    px(ctx, 29, armY - 3, 1, 7);
    ctx.fillStyle = sleeveColor;
    px(ctx, 23, armY - 5, 4, 4);
    ctx.fillStyle = handColor;
    px(ctx, 22, armY - 7, 4, 3);
    ctx.fillStyle = handShadow;
    px(ctx, 22, armY - 5, 4, 1);

  } else if (status === 'idle') {
    // ---- IDLE: arms at sides, relaxed ----
    ctx.fillStyle = sleeveColor;
    px(ctx, 2, armY + 1, 5, 7);
    ctx.fillStyle = sleeveShadow;
    px(ctx, 2, armY + 1, 1, 6);
    ctx.fillStyle = lighten(sleeveColor, 0.1);
    px(ctx, 4, armY + 1, 2, 6);
    ctx.fillStyle = handColor;
    px(ctx, 3, armY + 8, 3, 3);
    ctx.fillStyle = handShadow;
    px(ctx, 3, armY + 10, 3, 1);

    ctx.fillStyle = sleeveColor;
    px(ctx, 25, armY + 1, 5, 7);
    ctx.fillStyle = sleeveShadow;
    px(ctx, 29, armY + 1, 1, 6);
    ctx.fillStyle = lighten(sleeveColor, 0.1);
    px(ctx, 26, armY + 1, 2, 6);
    ctx.fillStyle = handColor;
    px(ctx, 26, armY + 8, 3, 3);
    ctx.fillStyle = handShadow;
    px(ctx, 26, armY + 10, 3, 1);

  } else {
    // ---- DEFAULT: arms at sides ----
    ctx.fillStyle = sleeveColor;
    px(ctx, 2, armY, 5, 8);
    ctx.fillStyle = sleeveShadow;
    px(ctx, 2, armY, 1, 7);
    px(ctx, 6, armY + 1, 1, 6);
    ctx.fillStyle = handColor;
    px(ctx, 3, armY + 8, 4, 3);
    ctx.fillStyle = handShadow;
    px(ctx, 3, armY + 10, 4, 1);

    ctx.fillStyle = sleeveColor;
    px(ctx, 25, armY, 5, 8);
    ctx.fillStyle = sleeveShadow;
    px(ctx, 29, armY, 1, 7);
    px(ctx, 25, armY + 1, 1, 6);
    ctx.fillStyle = handColor;
    px(ctx, 25, armY + 8, 4, 3);
    ctx.fillStyle = handShadow;
    px(ctx, 25, armY + 10, 4, 1);
  }
}
