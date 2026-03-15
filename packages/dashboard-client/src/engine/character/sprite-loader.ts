/**
 * Modern Interiors character sprite loader
 *
 * Loads individual character spritesheets from /assets/characters/modern/
 * and extracts 16×32 frames per pose and direction.
 *
 * Spritesheet layout (per character):
 *   {name}-idle.png       (64×32)  → 4 frames  (1/dir × 4 dirs: down, right, up, left)
 *   {name}-idle-anim.png  (384×32) → 24 frames (6/dir × 4 dirs)
 *   {name}-sit.png        (384×32) → 24 frames (6/dir × 4 dirs)
 *   {name}-sit2.png       (384×32) → 24 frames
 *   {name}-run.png        (384×32) → 24 frames (6/dir × 4 dirs)
 */

// ---- Constants ----

/** Raw pixel size of one frame in the spritesheet */
export const SPRITE_FRAME_W = 16;
export const SPRITE_FRAME_H = 32;

/** Direction offsets within 24-frame sheets (6 frames per direction).
 *  Modern Interiors layout: RIGHT(0-5), UP(6-11), LEFT(12-17), DOWN(18-23) */
const DIR_DOWN = 18;
const DIR_LEFT = 12;
const DIR_RIGHT = 0;
const DIR_UP = 6;

/** Direction offsets within 4-frame idle sheets (1 frame per direction).
 *  idle.png layout: DOWN(0), RIGHT(1), UP(2), LEFT(3) */
const IDLE_DOWN = 0;

// ---- Types ----

type PoseSheet = 'idle' | 'idle-anim' | 'sit' | 'sit2' | 'run';

export interface CharacterDef {
  id: string;
  name: string;
}

export interface SpriteCollection {
  characters: Map<string, Map<PoseSheet, HTMLImageElement>>;
  assignments: Record<string, string>;
  defs: CharacterDef[];
}

// ---- Character catalog ----

const CHARACTERS = ['adam', 'alex', 'amelia', 'bob'] as const;

const CHARACTER_DEFS: CharacterDef[] = [
  { id: 'adam', name: 'Adam' },
  { id: 'alex', name: 'Alex' },
  { id: 'amelia', name: 'Amelia' },
  { id: 'bob', name: 'Bob' },
];

const DEFAULT_ASSIGNMENTS: Record<string, string> = {
  director: 'bob',
  orchestration: 'bob', // server sends "orchestration" for director agent
  git: 'alex',
  frontend: 'amelia',
  backend: 'adam',
  docs: 'amelia', // shared — badge distinguishes
};

const POSE_SHEETS: PoseSheet[] = ['idle', 'idle-anim', 'sit', 'sit2', 'run'];

// ---- Frame extraction ----

interface FrameRef {
  sheet: PoseSheet;
  frameIndex: number;
}

/** Map agent status + animation frame to a specific spritesheet frame.
 *
 * Desk statuses (working, thinking, waiting, error) use idle-anim facing UP
 * so characters appear at their desk looking at the computer (back to camera).
 */
function getFrameRef(status: string, animFrame: number): FrameRef {
  switch (status) {
    case 'idle':
      return { sheet: 'idle', frameIndex: IDLE_DOWN };
    case 'working':
      return { sheet: 'idle-anim', frameIndex: DIR_UP + (animFrame % 6) };
    case 'thinking':
      return { sheet: 'idle-anim', frameIndex: DIR_UP + (animFrame % 6) };
    case 'error':
      return { sheet: 'idle-anim', frameIndex: DIR_UP };
    case 'waiting':
      return { sheet: 'idle-anim', frameIndex: DIR_UP + (animFrame % 6) };
    case 'searching':
      return { sheet: 'run', frameIndex: DIR_RIGHT + (animFrame % 6) };
    case 'delivering':
      return { sheet: 'run', frameIndex: DIR_LEFT + (animFrame % 6) };
    case 'reviewing':
      return { sheet: 'idle-anim', frameIndex: DIR_DOWN + (animFrame % 6) };
    default:
      return { sheet: 'idle', frameIndex: IDLE_DOWN };
  }
}

// ---- Image loading ----

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

async function loadCharacterSheets(name: string): Promise<Map<PoseSheet, HTMLImageElement>> {
  const sheets = new Map<PoseSheet, HTMLImageElement>();
  const basePath = `/assets/characters/modern/${name}`;

  await Promise.all(
    POSE_SHEETS.map(async (sheet) => {
      try {
        const img = await loadImage(`${basePath}-${sheet}.png`);
        sheets.set(sheet, img);
      } catch {
        if (import.meta.env.DEV) console.warn(`[sprite-loader] Failed to load ${basePath}-${sheet}.png`);
      }
    }),
  );

  return sheets;
}

// ---- Public API ----

/** Load all character spritesheets */
export async function loadAllSprites(): Promise<SpriteCollection> {
  const characters = new Map<string, Map<PoseSheet, HTMLImageElement>>();

  await Promise.all(
    CHARACTERS.map(async (name) => {
      const sheets = await loadCharacterSheets(name);
      if (sheets.size > 0) {
        characters.set(name, sheets);
      }
    }),
  );

  let assignments = { ...DEFAULT_ASSIGNMENTS };
  try {
    const saved = localStorage.getItem('agent-character-assignments');
    if (saved) {
      assignments = { ...assignments, ...JSON.parse(saved) };
    }
  } catch { /* ignore */ }

  return { characters, assignments, defs: CHARACTER_DEFS };
}

/** Save character assignments to localStorage */
export function saveAssignments(assignments: Record<string, string>): void {
  try {
    localStorage.setItem('agent-character-assignments', JSON.stringify(assignments));
  } catch { /* ignore */ }
}

// ---- Reusable offscreen canvas for getSpriteFrame ----
let _reusableCanvas: HTMLCanvasElement | null = null;

function getReusableCanvas(): HTMLCanvasElement {
  if (!_reusableCanvas) {
    _reusableCanvas = document.createElement('canvas');
    _reusableCanvas.width = SPRITE_FRAME_W;
    _reusableCanvas.height = SPRITE_FRAME_H;
  }
  return _reusableCanvas;
}

/**
 * Get a rendered 16×32 frame canvas for a domain + status + animation frame.
 * Returns null if sprites aren't loaded.
 *
 * NOTE: 반환된 canvas는 재사용되므로, 호출자는 즉시 drawImage()로
 * 대상 canvas에 복사해야 한다. 다음 호출 시 내용이 덮어씌워진다.
 */
export function getSpriteFrame(
  collection: SpriteCollection,
  domain: string,
  status: string,
  animFrame: number,
): HTMLCanvasElement | null {
  const charId = collection.assignments[domain] ?? DEFAULT_ASSIGNMENTS[domain] ?? 'adam';
  const sheets = collection.characters.get(charId);
  if (!sheets) return null;

  const ref = getFrameRef(status, animFrame);
  const sheet = sheets.get(ref.sheet);
  if (!sheet) return null;

  const canvas = getReusableCanvas();
  const ctx = canvas.getContext('2d')!;
  ctx.clearRect(0, 0, SPRITE_FRAME_W, SPRITE_FRAME_H);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(
    sheet,
    ref.frameIndex * SPRITE_FRAME_W, 0,
    SPRITE_FRAME_W, SPRITE_FRAME_H,
    0, 0,
    SPRITE_FRAME_W, SPRITE_FRAME_H,
  );
  return canvas;
}

/** Get the full character catalog */
export function getCharacterCatalog(): CharacterDef[] {
  return CHARACTER_DEFS;
}
