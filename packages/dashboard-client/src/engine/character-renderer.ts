/**
 * LPC-style character renderer
 * Draws 24x32 pixel characters in RPG Maker / LPC proportions
 * 2.5-head tall, front-facing with walk animation support
 */

import { AGENT_COLORS, CHAR_W, CHAR_H, type AgentColors } from './sprite-config';

// Animation frame data
// Walk cycle: 4 frames (stand, step-right, stand, step-left)
// Work cycle: 2 frames (arms up/down for typing)

export interface CharacterFrame {
  walkFrame: number; // 0-3 for walk cycle
  armFrame: number;  // 0-1 for working arm movement
  isBlinking: boolean;
}

/**
 * Draw an LPC-style character at position (0,0) — caller should translate ctx
 * Character is drawn centered horizontally, bottom-aligned at y=CHAR_H
 */
export function drawCharacter(
  ctx: CanvasRenderingContext2D,
  domain: string,
  status: string,
  frame: CharacterFrame,
) {
  const colors = AGENT_COLORS[domain] ?? AGENT_COLORS.frontend;
  const walkOffset = getWalkOffset(frame.walkFrame);
  const isWorking = status === 'working';
  const isThinking = status === 'thinking';
  const isError = status === 'error';
  const isIdle = status === 'idle';

  ctx.save();

  // Shadow
  ctx.fillStyle = 'rgba(0,0,0,0.2)';
  ctx.beginPath();
  ctx.ellipse(CHAR_W / 2, CHAR_H - 1, 8, 3, 0, 0, Math.PI * 2);
  ctx.fill();

  // ---- LEGS ----
  drawLegs(ctx, colors, walkOffset, isIdle);

  // ---- BODY / TORSO ----
  drawBody(ctx, colors, domain);

  // ---- ARMS ----
  drawArms(ctx, colors, isWorking, isThinking, frame.armFrame);

  // ---- HEAD ----
  drawHead(ctx, colors, frame.isBlinking, isError, isThinking, isWorking, isIdle);

  // ---- HAIR ----
  drawHair(ctx, colors);

  // ---- DOMAIN ACCESSORIES ----
  drawAccessory(ctx, domain, colors);

  ctx.restore();
}

function getWalkOffset(walkFrame: number): number {
  // Returns y-offset for bob during walk: 0, -1, 0, -1
  return walkFrame % 2 === 1 ? -1 : 0;
}

function drawLegs(ctx: CanvasRenderingContext2D, c: AgentColors, walkOffset: number, isIdle: boolean) {
  const legY = 24;
  const legH = 6;
  const footY = legY + legH;

  if (isIdle) {
    // Legs together (sitting/relaxed)
    ctx.fillStyle = c.pants;
    ctx.fillRect(8, legY, 4, legH);
    ctx.fillRect(12, legY, 4, legH);
    // Shoes
    ctx.fillStyle = c.shoes;
    ctx.fillRect(7, footY, 5, 2);
    ctx.fillRect(12, footY, 5, 2);
  } else {
    // Walking pose with offset
    const stepL = walkOffset;
    const stepR = -walkOffset;
    ctx.fillStyle = c.pants;
    ctx.fillRect(8, legY + stepL, 4, legH);
    ctx.fillRect(12, legY + stepR, 4, legH);
    // Shoes
    ctx.fillStyle = c.shoes;
    ctx.fillRect(7, footY + stepL, 5, 2);
    ctx.fillRect(12, footY + stepR, 5, 2);
  }
}

function drawBody(ctx: CanvasRenderingContext2D, c: AgentColors, domain: string) {
  const bodyY = 14;
  const bodyH = 11;

  // Main torso
  ctx.fillStyle = c.body;
  ctx.fillRect(6, bodyY, 12, bodyH);

  // Body shadow (right side)
  ctx.fillStyle = c.bodyDark;
  ctx.fillRect(15, bodyY + 1, 3, bodyH - 2);

  // Collar / accent stripe
  ctx.fillStyle = c.accent;
  ctx.fillRect(9, bodyY, 6, 2);

  // Belt
  ctx.fillStyle = c.bodyDark;
  ctx.fillRect(7, bodyY + bodyH - 1, 10, 2);
  // Belt buckle
  ctx.fillStyle = c.accent;
  ctx.fillRect(11, bodyY + bodyH - 1, 2, 2);

  // Domain-specific shirt detail
  if (domain === 'git') {
    // Git branch icon on shirt
    ctx.fillStyle = c.accent;
    ctx.fillRect(11, bodyY + 4, 1, 4);
    ctx.fillRect(11, bodyY + 6, 3, 1);
    ctx.fillRect(14, bodyY + 5, 1, 2);
  }
}

function drawArms(
  ctx: CanvasRenderingContext2D,
  c: AgentColors,
  isWorking: boolean,
  isThinking: boolean,
  armFrame: number,
) {
  const armY = 15;

  if (isWorking) {
    // Arms forward (typing) — bobbing
    const offset = armFrame === 0 ? 0 : -1;
    // Left arm
    ctx.fillStyle = c.body;
    ctx.fillRect(3, armY + offset, 4, 8);
    ctx.fillStyle = c.skin;
    ctx.fillRect(3, armY + 7 + offset, 4, 3);
    // Right arm
    ctx.fillStyle = c.body;
    ctx.fillRect(17, armY - offset, 4, 8);
    ctx.fillStyle = c.skin;
    ctx.fillRect(17, armY + 7 - offset, 4, 3);
  } else if (isThinking) {
    // One hand on chin
    ctx.fillStyle = c.body;
    ctx.fillRect(2, armY, 4, 8);
    ctx.fillStyle = c.skin;
    ctx.fillRect(2, armY + 7, 4, 3);
    // Right arm up to chin
    ctx.fillStyle = c.body;
    ctx.fillRect(18, armY - 4, 4, 8);
    ctx.fillStyle = c.skin;
    ctx.fillRect(18, armY - 5, 4, 3);
  } else {
    // Arms down (default)
    ctx.fillStyle = c.body;
    ctx.fillRect(2, armY, 4, 8);
    ctx.fillStyle = c.skin;
    ctx.fillRect(2, armY + 7, 4, 3);
    ctx.fillStyle = c.body;
    ctx.fillRect(18, armY, 4, 8);
    ctx.fillStyle = c.skin;
    ctx.fillRect(18, armY + 7, 4, 3);
  }
}

function drawHead(
  ctx: CanvasRenderingContext2D,
  c: AgentColors,
  isBlinking: boolean,
  isError: boolean,
  isThinking: boolean,
  isWorking: boolean,
  isIdle: boolean,
) {
  const headX = 6;
  const headY = 2;
  const headW = 12;
  const headH = 13;

  // Neck
  ctx.fillStyle = c.skin;
  ctx.fillRect(10, 12, 4, 4);

  // Head shape
  ctx.fillStyle = c.skin;
  ctx.fillRect(headX, headY, headW, headH);

  // Face shadow
  ctx.fillStyle = c.skinShadow;
  ctx.fillRect(headX + headW - 3, headY + 2, 3, headH - 4);

  // Ears
  ctx.fillStyle = c.skin;
  ctx.fillRect(headX - 2, headY + 4, 2, 4);
  ctx.fillRect(headX + headW, headY + 4, 2, 4);

  // Eyes
  if (isBlinking) {
    // Blink — horizontal lines
    ctx.fillStyle = '#333333';
    ctx.fillRect(headX + 2, headY + 6, 3, 1);
    ctx.fillRect(headX + headW - 5, headY + 6, 3, 1);
  } else {
    // Open eyes
    // White
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(headX + 2, headY + 5, 3, 3);
    ctx.fillRect(headX + headW - 5, headY + 5, 3, 3);
    // Pupil
    ctx.fillStyle = '#333333';
    ctx.fillRect(headX + 3, headY + 6, 2, 2);
    ctx.fillRect(headX + headW - 4, headY + 6, 2, 2);
    // Eye highlight
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(headX + 3, headY + 6, 1, 1);
    ctx.fillRect(headX + headW - 4, headY + 6, 1, 1);
  }

  // Eyebrows (error = angry, thinking = raised)
  if (isError) {
    ctx.fillStyle = '#333333';
    // Angry eyebrows (V shape)
    ctx.fillRect(headX + 2, headY + 4, 3, 1);
    ctx.fillRect(headX + 3, headY + 3, 1, 1);
    ctx.fillRect(headX + headW - 5, headY + 4, 3, 1);
    ctx.fillRect(headX + headW - 4, headY + 3, 1, 1);
  } else if (isThinking) {
    ctx.fillStyle = '#333333';
    ctx.fillRect(headX + 2, headY + 3, 3, 1);
    ctx.fillRect(headX + headW - 5, headY + 3, 3, 1);
  }

  // Nose
  ctx.fillStyle = c.skinShadow;
  ctx.fillRect(headX + headW / 2 - 1, headY + 8, 2, 2);

  // Mouth
  if (isError) {
    // Frown
    ctx.fillStyle = '#CC3333';
    ctx.fillRect(headX + 4, headY + 11, 1, 1);
    ctx.fillRect(headX + 5, headY + 10, 2, 1);
    ctx.fillRect(headX + 7, headY + 11, 1, 1);
  } else if (isIdle) {
    // Smile
    ctx.fillStyle = '#AA8866';
    ctx.fillRect(headX + 4, headY + 10, 1, 1);
    ctx.fillRect(headX + 5, headY + 11, 2, 1);
    ctx.fillRect(headX + 7, headY + 10, 1, 1);
  } else if (isWorking) {
    // Focused line
    ctx.fillStyle = '#AA8866';
    ctx.fillRect(headX + 5, headY + 10, 2, 1);
  } else {
    // Neutral
    ctx.fillStyle = '#AA8866';
    ctx.fillRect(headX + 5, headY + 10, 2, 1);
  }

  // Cheeks (blush when idle/happy)
  if (isIdle) {
    ctx.fillStyle = 'rgba(255,136,136,0.3)';
    ctx.fillRect(headX + 1, headY + 9, 2, 2);
    ctx.fillRect(headX + headW - 3, headY + 9, 2, 2);
  }
}

function drawHair(ctx: CanvasRenderingContext2D, c: AgentColors) {
  const headX = 6;
  const headY = 2;
  const headW = 12;

  ctx.fillStyle = c.hair;

  switch (c.hairStyle) {
    case 'short':
      // Short hair — top cap
      ctx.fillRect(headX - 1, headY - 2, headW + 2, 5);
      ctx.fillRect(headX, headY - 3, headW, 2);
      break;

    case 'spiky':
      // Spiky hair — jagged top
      ctx.fillRect(headX - 1, headY - 1, headW + 2, 4);
      // Spikes
      ctx.fillRect(headX, headY - 4, 2, 3);
      ctx.fillRect(headX + 3, headY - 5, 2, 4);
      ctx.fillRect(headX + 6, headY - 6, 2, 5);
      ctx.fillRect(headX + 9, headY - 4, 2, 3);
      break;

    case 'long':
      // Long hair — top + sides
      ctx.fillRect(headX - 1, headY - 2, headW + 2, 5);
      ctx.fillRect(headX, headY - 3, headW, 2);
      // Side hair flowing down
      ctx.fillRect(headX - 2, headY, 3, 12);
      ctx.fillRect(headX + headW - 1, headY, 3, 12);
      break;

    case 'curly':
      // Curly hair — rounded bumps
      ctx.fillRect(headX - 1, headY - 2, headW + 2, 5);
      // Curls
      ctx.fillRect(headX - 2, headY - 3, 3, 3);
      ctx.fillRect(headX + 2, headY - 4, 3, 3);
      ctx.fillRect(headX + 6, headY - 4, 3, 3);
      ctx.fillRect(headX + 10, headY - 3, 3, 3);
      break;

    case 'ponytail':
      // Top hair + ponytail
      ctx.fillRect(headX - 1, headY - 2, headW + 2, 5);
      ctx.fillRect(headX, headY - 3, headW, 2);
      // Ponytail (behind head, to the right)
      ctx.fillRect(headX + headW, headY + 2, 3, 4);
      ctx.fillRect(headX + headW + 1, headY + 5, 2, 6);
      // Hair tie
      ctx.fillStyle = c.accent;
      ctx.fillRect(headX + headW, headY + 5, 3, 2);
      break;
  }
}

function drawAccessory(ctx: CanvasRenderingContext2D, domain: string, c: AgentColors) {
  switch (domain) {
    case 'director':
      // Sunglasses (PM style) — covers eyes fully (y 5-10)
      ctx.fillStyle = '#111111';
      ctx.fillRect(7, 5, 5, 5);
      ctx.fillRect(13, 5, 5, 5);
      // Bridge
      ctx.fillRect(12, 6, 1, 2);
      // Lens glare
      ctx.fillStyle = 'rgba(255,255,255,0.25)';
      ctx.fillRect(8, 6, 2, 1);
      ctx.fillRect(14, 6, 2, 1);
      // Temple arms
      ctx.fillStyle = '#111111';
      ctx.fillRect(5, 6, 2, 1);
      ctx.fillRect(18, 6, 2, 1);
      break;

    case 'frontend':
      // Glasses
      ctx.strokeStyle = '#61DAFB';
      ctx.lineWidth = 1;
      ctx.strokeRect(7, 6, 4, 3);
      ctx.strokeRect(13, 6, 4, 3);
      // Bridge
      ctx.fillStyle = '#61DAFB';
      ctx.fillRect(11, 7, 2, 1);
      break;

    case 'backend':
      // Headphones
      ctx.fillStyle = '#68A063';
      ctx.fillRect(4, 1, 3, 5);
      ctx.fillRect(17, 1, 3, 5);
      // Headband
      ctx.fillRect(5, -1, 14, 2);
      break;

    case 'docs':
      // Notebook in hand
      ctx.fillStyle = '#F7DF1E';
      ctx.fillRect(20, 18, 5, 7);
      ctx.fillStyle = '#C9B100';
      ctx.fillRect(20, 18, 5, 1);
      // Lines on notebook
      ctx.fillStyle = '#888888';
      ctx.fillRect(21, 20, 3, 1);
      ctx.fillRect(21, 22, 3, 1);
      break;
  }
}

/**
 * Pre-render character frames to offscreen canvases for performance
 * Returns a map of domain -> { frames: canvas[] } for each status
 */
export function prerenderCharacters(): Map<string, HTMLCanvasElement[]> {
  const cache = new Map<string, HTMLCanvasElement[]>();
  const domains = ['director', 'git', 'frontend', 'backend', 'docs'];
  const statuses = ['idle', 'working', 'thinking', 'error', 'waiting', 'searching', 'delivering', 'reviewing'];

  for (const domain of domains) {
    for (const status of statuses) {
      const frames: HTMLCanvasElement[] = [];
      const walkFrames = (status === 'delivering' || status === 'searching') ? 4 : 1;
      const armFrames = status === 'working' ? 2 : 1;
      const totalFrames = Math.max(walkFrames, armFrames);

      for (let i = 0; i < totalFrames; i++) {
        const canvas = document.createElement('canvas');
        canvas.width = CHAR_W + 8; // extra for accessories overflow
        canvas.height = CHAR_H + 12; // extra top padding for hair spikes
        const fCtx = canvas.getContext('2d')!;
        fCtx.imageSmoothingEnabled = false;

        fCtx.save();
        fCtx.translate(4, 8); // padding: 4 left, 8 top for tall hair
        drawCharacter(fCtx, domain, status, {
          walkFrame: i % walkFrames,
          armFrame: i % armFrames,
          isBlinking: false,
        });
        fCtx.restore();

        frames.push(canvas);
      }

      // Also add a blink frame (same as frame 0 but blinking)
      const blinkCanvas = document.createElement('canvas');
      blinkCanvas.width = CHAR_W + 8;
      blinkCanvas.height = CHAR_H + 12;
      const bCtx = blinkCanvas.getContext('2d')!;
      bCtx.imageSmoothingEnabled = false;
      bCtx.save();
      bCtx.translate(4, 8);
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
