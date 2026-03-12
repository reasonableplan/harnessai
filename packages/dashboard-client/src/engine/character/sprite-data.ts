/**
 * Pixel-map sprite definitions for all 5 agent characters.
 * Each sprite is a 32×48 string grid — every row EXACTLY 32 characters.
 * '.' = transparent, all other chars map via buildPalette().
 *
 * Palette key:
 *   O = outline (near-black)     s = skin        S = skin shadow
 *   h = hair base   H = hair dark    l = hair highlight
 *   b = body        B = body dark    L = body highlight
 *   a = accent      A = accent dark
 *   p = pants       P = pants dark   Q = pants highlight
 *   x = shoes       X = shoe sole    Y = shoe highlight
 *   w = white (eye whites)
 *   e = eye iris    E = eye pupil
 *   r = blush       m = mouth
 *   k = belt/dark   c = collar       n = nose shadow
 *   g = glasses frame  G = lens tint
 *   d = detail (buttons, patterns)
 *   t = headphone/accessory accent
 *   T = accessory dark
 */

import { lighten, darken } from './draw-utils';
import type { AgentColors } from '../sprite-config';

export interface SpritePatch {
  startRow: number;
  rows: string[];
}

export interface CharacterSpriteSet {
  base: string[];
  blinkPatch?: SpritePatch;
  walkPatches?: SpritePatch[];
  workPatches?: SpritePatch[];
}

// ---- Palette builder ----

export function buildPalette(c: AgentColors): Record<string, string> {
  return {
    O: '#1A0F0A',
    s: c.skin,
    S: c.skinShadow,
    n: darken(c.skinShadow, 0.12),
    h: c.hair,
    H: darken(c.hair, 0.3),
    l: lighten(c.hair, 0.35),
    b: c.body,
    B: c.bodyDark,
    L: lighten(c.body, 0.22),
    a: c.accent,
    A: darken(c.accent, 0.25),
    p: c.pants,
    P: darken(c.pants, 0.25),
    Q: lighten(c.pants, 0.18),
    x: c.shoes,
    X: darken(c.shoes, 0.35),
    Y: lighten(c.shoes, 0.2),
    w: '#FFFFFF',
    e: lighten(c.accent, 0.15),
    E: '#1A0A00',
    r: '#FF9090',
    m: '#8A4040',
    k: darken(c.bodyDark, 0.4),
    c: lighten(c.accent, 0.3),
    d: darken(c.body, 0.15),
    g: '#C8A840',
    G: 'rgba(255,215,0,0.15)',
    t: c.accent,
    T: darken(c.accent, 0.3),
  };
}

// ---- Render from sprite grid ----

export function renderSprite(
  ctx: CanvasRenderingContext2D,
  grid: string[],
  palette: Record<string, string>,
  patches?: SpritePatch[],
): void {
  const finalGrid = [...grid];
  if (patches) {
    for (const patch of patches) {
      for (let i = 0; i < patch.rows.length; i++) {
        if (patch.startRow + i < finalGrid.length) {
          finalGrid[patch.startRow + i] = patch.rows[i];
        }
      }
    }
  }

  for (let y = 0; y < finalGrid.length; y++) {
    const row = finalGrid[y];
    for (let x = 0; x < row.length; x++) {
      const ch = row[x];
      if (ch === '.') continue;
      const color = palette[ch];
      if (color) {
        ctx.fillStyle = color;
        ctx.fillRect(x, y, 1, 1);
      }
    }
  }
}

// ================================================================
// DIRECTOR — short brown hair, gold glasses, purple royal suit
// Each row is EXACTLY 32 characters
// ================================================================

const directorBase: string[] = [
  //0123456789012345678901234567890123
  '..........OOOOOOhhhOOO..........', // 0  hair top
  '.........OhhlllhhhhhhlhO........', // 1
  '........OhhllllhhHHhhhhhO.......', // 2
  '........OhhlllhhhHHhhhhHO.......', // 3
  '........OhhhhhhhhHHhhhhHO.......', // 4
  '.......OOhhhhhhhhhhhhhhhOO......', // 5  head outline
  '.......OsssssssssssssssssO......', // 6
  '.......OsssssssssssssssssO......', // 7
  '.......OsOgOOOgsssOgOOOgsO......', // 8  glasses
  '.......OsOgwEgsssOgwEOgsO.......', // 9  eyes w/ glasses
  '.......OsOgwwgsssOgwwOgsO.......', // 10
  '.......OssOOOOsssssOOOOssO......', // 11 glasses bottom
  '.......OsssssssSnSssssssO.......', // 12 nose
  '.......OssrsssssssssssrssO......', // 13 cheeks
  '.......OsssssssmmmsssssssO......', // 14 mouth
  '........OsssssssssssssssO.......', // 15
  '........OssssssssssssssO........', // 16
  '.........OsssssssssssO..........', // 17 chin
  '..........OOssssssOO............', // 18 neck top
  '...........OssSSSsO.............', // 19 neck
  '........OOBBBBcccBBBBOO.........', // 20 shoulders
  '........OLbbbbcacbbbbBO.........', // 21 collar
  '........OLbbbbbbbbbbbBO.........', // 22
  '........OLbbbbddbbbbbBO.........', // 23 buttons
  '........OLbbbbddbbbbbBO.........', // 24
  '........OBbbbbbbbbbbbBO.........', // 25
  '........OkkkkkaAakkkkkkO........', // 26 belt
  '........OkkAAAAAAAAkkkO.........', // 27 buckle
  '...OOO..OBbbbbbbbbbbbBO..OOO....', // 28 arms start
  '...ObBO.OBbbbbbbbbbbbBO.OBbO....', // 29
  '...ObbO.ObbbbbbbbbbbbbbO.ObbO...', // 30
  '...ObbO.ObbbbbbbbbbbbbbO.ObbO...', // 31
  '...OsSO.ObbbbbbbbbbbbbBO.OSsO...', // 32 hands
  '...OSSO.ObbbbbbbbbbbbbBO.OSSO...', // 33
  '........OOBBBBBBBBBBBBbOO.......', // 34
  '........OOPPPPPPPPPPPPPOO.......', // 35 pants start
  '.........OQpppOO.OOpppQO........', // 36
  '.........OppppO...OpppPO........', // 37
  '.........OppppO...OppppO........', // 38
  '.........OppppO...OppppO........', // 39
  '.........OppppO...OppppO........', // 40
  '.........OPpppO...OpppPO........', // 41
  '.........OPPppO...OppPPO........', // 42
  '.........OOPPPO...OPPPOO........', // 43
  '........OOxxxxO...OxxxxOO.......', // 44 shoes
  '........OYxxxxO...OxxxxYO.......', // 45
  '........OxxxxxO...OxxxxxO.......', // 46
  '.......OOXXXXOO...OOXXXXOO......', // 47 soles
];

const directorBlink: SpritePatch = {
  startRow: 9,
  rows: [
    '.......OsOgOOgsssOgOOOgsO.......', // closed eyes
    '.......OsOgOOgsssOgOOOgsO.......',
  ],
};

const directorWalk0: SpritePatch = {
  startRow: 36,
  rows: [
    '.........OQpppOO.OOpppQO........',
    '........OQppppO....OppPO........',
    '........OppppO......OpppO.......',
    '........OppppO......OpppO.......',
    '.........OpppO.....OppppO.......',
    '.........OPppO....OpppPO........',
    '.........OPPpO...OppPPO.........',
    '..........OPPO...OPPOO..........',
    '.........OxxxxO.OxxxxO..........',
    '.........OxxxxO.OxxxxO..........',
    '........OxxxxxO.OxxxxxO.........',
    '.......OOXXXXOO.OOXXXXOO........',
  ],
};

const directorWalk1: SpritePatch = {
  startRow: 36,
  rows: [
    '.........OQpppOO.OOpppQO........',
    '.........OppPO....OQpppO........',
    '........OpppO......OppppO.......',
    '........OpppO......OppppO.......',
    '.........OppppO.....OpppO.......',
    '........OPpppO....OPppO.........',
    '.........OPPppO...OPPpO.........',
    '..........OOPPO...OPPOO.........',
    '..........OxxxxO.OxxxxO.........',
    '..........OxxxxO.OxxxxO.........',
    '.........OxxxxxO.OxxxxxO........',
    '........OOXXXXOO.OOXXXXOO.......',
  ],
};

const directorWork0: SpritePatch = {
  startRow: 28,
  rows: [
    '...OOO..OBbbbbbbbbbbbBO..OOO....',
    '..OBbO..OBbbbbbbbbbbbBO.OBbO....',
    '..ObbBO.ObbbbbbbbbbbbbbO.ObbO...',
    '.OBbbO..ObbbbbbbbbbbbbbO.ObbO...',
    '.OsSO...ObbbbbbbbbbbbbBO.OSsO...',
    '.OSSO...ObbbbbbbbbbbbbBO.OSSO...',
  ],
};

const directorWork1: SpritePatch = {
  startRow: 28,
  rows: [
    '...OOO..OBbbbbbbbbbbbBO..OOO....',
    '...ObBO.OBbbbbbbbbbbbBO..OBbO...',
    '...ObbO.ObbbbbbbbbbbbbbO.ObbBO..',
    '...ObbO.ObbbbbbbbbbbbbbO..ObbO..',
    '...OsSO.ObbbbbbbbbbbbbBO..OSsO..',
    '...OSSO.ObbbbbbbbbbbbbBO..OSSO..',
  ],
};

// ================================================================
// GIT — spiky black hair, orange scarf, red vest
// ================================================================

const gitBase: string[] = [
  '..............OhO...............', // 0 spike top — WRONG, let me fix
  '..........OOhhhhhOO.............',
  '.........OhhlllhhlhhO...........',
  '........OhhllOhlOllhhO..........',
  '.......OhhlhO.OhOlhlhO..........',
  '.....OOhhhhhhhhhhhhhhhhOO.......',
  '.....OhhhhhhhhhhhhhhhhhhhO......',
  '.....OssssssssssssssssssO.......',
  '.....OsssssssssssssssssO........',
  '.....OssOOsssssssssOOssO........',
  '.....OssOwEOsssssOweOssO........',
  '.....OssOwwOsssssOwwOssO........',
  '.....OsssssssSnSsssssssO........',
  '.....OssrsssssssssssrssO........',
  '.....OsssssssmmmssssssO.........',
  '......OsssssssssssssssO.........',
  '......OssssssssssssssO..........',
  '.......OssssssssssssO...........',
  '........OOssssssOO..............',
  '.........OssSSSsO...............',
  '.......OOaaaaaaaaaaOO...........',
  '.......OaaAAAAAAAAaaO...........',
  '......OOBBBBBcBBBBBOO...........',
  '......OLbbbbcacbbbbbO...........',
  '......OLbbbbbbbbbbbBO...........',
  '......OBbbbbbbbbbbbBO...........',
  '......OkkkkkAAAkkkkkO...........',
  '......OkAAAAAAAAAAAAkO..........',
  '..OOO.OBbbbbbbbbbbBO.OOO........',
  '..ObBO.OBbbbbbbbbbbBO.ObBO......',
  '..ObbO.ObbbbbbbbbbbbO.ObbO......',
  '..ObbO.ObbbbbbbbbbbbO.ObbO......',
  '..OsSO.ObbbbbbbbbbbbO.OSsO......',
  '..OSSO.ObbbbbbbbbbbbO.OSSO......',
  '......OOBBBBBBBBBBBBbOO.........',
  '......OOPPPPPPPPPPPPOO..........',
  '.......OQpppOO.OOpppQO..........',
  '.......OppppO...OpppPO..........',
  '.......OppppO...OppppO..........',
  '.......OppppO...OppppO..........',
  '.......OppppO...OppppO..........',
  '.......OPpppO...OpppPO..........',
  '.......OPPppO...OppPPO..........',
  '.......OOPPPO...OPPPOO..........',
  '......OOxxxxO...OxxxxOO.........',
  '......OYxxxxO...OxxxxYO.........',
  '......OxxxxxO...OxxxxxO.........',
  '.....OOXXXXOO...OOXXXXOO........',
];

const gitBlink: SpritePatch = {
  startRow: 10,
  rows: [
    '.....OssOOOOsssssOOOOssO........',
    '.....OssssssssssssssssssO.......',
  ],
};

const gitWalk0: SpritePatch = {
  startRow: 36,
  rows: [
    '.......OQpppOO.OOpppQO..........',
    '......OQppppO....OppPO..........',
    '......OppppO......OpppO.........',
    '......OppppO......OpppO.........',
    '.......OpppO.....OppppO.........',
    '.......OPppO....OpppPO..........',
    '.......OPPpO...OppPPO...........',
    '........OPPO...OPPOO............',
    '.......OxxxxO.OxxxxO............',
    '.......OxxxxO.OxxxxO............',
    '......OxxxxxO.OxxxxxO...........',
    '.....OOXXXXOO.OOXXXXOO..........',
  ],
};

const gitWalk1: SpritePatch = {
  startRow: 36,
  rows: [
    '.......OQpppOO.OOpppQO..........',
    '.......OppPO....OQpppO..........',
    '......OpppO......OppppO.........',
    '......OpppO......OppppO.........',
    '.......OppppO.....OpppO.........',
    '......OPpppO....OPppO...........',
    '.......OPPppO...OPPpO...........',
    '........OOPPO...OPPOO...........',
    '........OxxxxO.OxxxxO...........',
    '........OxxxxO.OxxxxO...........',
    '.......OxxxxxO.OxxxxxO..........',
    '......OOXXXXOO.OOXXXXOO.........',
  ],
};

const gitWork0: SpritePatch = {
  startRow: 28,
  rows: [
    '..OOO.OBbbbbbbbbbbBO.OOO........',
    '.OBbO.OBbbbbbbbbbbBO.ObBO.......',
    '.ObbBO.ObbbbbbbbbbbbO.ObbO......',
    'OBbbO..ObbbbbbbbbbbbO.ObbO......',
    'OsSO...ObbbbbbbbbbbbO.OSsO......',
    'OSSO...ObbbbbbbbbbbbO.OSSO......',
  ],
};

const gitWork1: SpritePatch = {
  startRow: 28,
  rows: [
    '..OOO.OBbbbbbbbbbbBO.OOO........',
    '..ObBO.OBbbbbbbbbbbBO..ObBO.....',
    '..ObbO.ObbbbbbbbbbbbO..ObbBO....',
    '..ObbO.ObbbbbbbbbbbbO...ObbO....',
    '..OsSO.ObbbbbbbbbbbbO...OSsO....',
    '..OSSO.ObbbbbbbbbbbbO...OSSO....',
  ],
};

// ================================================================
// FRONTEND — long auburn hair, teal headband, teal top
// ================================================================

const frontendBase: string[] = [
  '.........OOhhhhhhhhOO...........',
  '........OhhlllhhhhhlhO..........',
  '.......OhhllllhhhhhllhO.........',
  '.......OhhlllllhhhllllhO........',
  '.......OhhhhhhhHHhhhhhhO........',
  '......OOaaaaaaaaaaaaaaaaOO......',
  '......OsssssssssssssssssO.......',
  '.OhO..OsssssssssssssssssO..OhO..',
  '.OhO..OssOOsssssssssOOssO..OhO..',
  '.OhO..OssOwEOsssssOwEOssO..OhO..',
  '.OhO..OssOwwOsssssOwwOssO..OhO..',
  '.OhO..OsssssssssssssssssO..OhO..',
  '.OhO..OsssssssSnSsssssssO..OhO..',
  '.OhO..OssrssssssssssssrssO.OhO..',
  '.OhO..OsssssssmmmssssssssO.OhO..',
  '.OhO...OsssssssssssssssO...OhO..',
  '.OhO...OssssssssssssssO....OhO..',
  '.OhO....OssssssssssssO.....OhO..',
  '.OhO.....OOssssssOO........OhO..',
  '.OhO......OssSSSsO.........OhO..',
  '.OhO...OOBBBBcccBBBBOO.....OhO..',
  '.OhO...OLbbbbcacbbbbBO.....OhO..',
  '.OhO...OLbbbbbbbbbbbBO.....OhO..',
  '.OhO...OLbbbbbbbbbbbBO.....OhO..',
  '.OhO...OLbbbbddbbbbbBO.....OhO..',
  '.OhO...OBbbbbbbbbbbbBO.....OhO..',
  '.OhO...OkkkkkAAAkkkkkO.....OhO..',
  '.OhO...OkAAAAAAAAAAAAkO....OhO..',
  '.OhOOOOOBbbbbbbbbbbBOOOOOO.OhO..',
  '.OhOBbbOBbbbbbbbbbbBOBbbbO.OhO..',
  '.OhObbBO.ObbbbbbbbbbO.ObbO.OhO..',
  '.OhObbBO.ObbbbbbbbbbO.ObbO.OhO..',
  '.OhOsSO..ObbbbbbbbbbO..OsOOOhO..',
  '.OhOSSO..ObbbbbbbbbbO..OSOOOhO..',
  '.OhO...OOBBBBBBBBBBBBbOO...OhO..',
  '.OhO...OOPPPPPPPPPPPPOO....OhO..',
  '.OhO....OQpppOO.OOpppQO...OhO...',
  '.OhO....OppppO...OpppPO...OhO...',
  '.OhO....OppppO...OppppO...OhO...',
  '.OhO....OppppO...OppppO...OhO...',
  '.OhO....OppppO...OppppO...OhO...',
  '.OHO....OPpppO...OpppPO...OHO...',
  '..O.....OPPppO...OppPPO....O....',
  '........OOPPPO...OPPPOO.........',
  '.......OOxxxxO...OxxxxOO........',
  '.......OYxxxxO...OxxxxYO........',
  '.......OxxxxxO...OxxxxxO........',
  '......OOXXXXOO...OOXXXXOO.......',
];

const frontendBlink: SpritePatch = {
  startRow: 9,
  rows: [
    '.OhO..OssOOOOsssssOOOOssO..OhO..',
    '.OhO..OssssssssssssssssssO..OhO.',
  ],
};

const frontendWalk0: SpritePatch = {
  startRow: 36,
  rows: [
    '.OhO....OQpppOO.OOpppQO...OhO...',
    '.OhO...OQppppO....OppPO...OhO...',
    '.OhO...OppppO......OpppO..OhO...',
    '.OhO...OppppO......OpppO..OhO...',
    '.OhO....OpppO.....OppppO..OhO...',
    '.OhO....OPppO....OpppPO...OhO...',
    '.OHO....OPPpO...OppPPO....OHO...',
    '..O......OPPO...OPPOO......O....',
    '........OxxxxO.OxxxxO...........',
    '........OxxxxO.OxxxxO...........',
    '.......OxxxxxO.OxxxxxO..........',
    '......OOXXXXOO.OOXXXXOO.........',
  ],
};

const frontendWalk1: SpritePatch = {
  startRow: 36,
  rows: [
    '.OhO....OQpppOO.OOpppQO...OhO...',
    '.OhO....OppPO....OQpppO...OhO...',
    '.OhO...OpppO......OppppO..OhO...',
    '.OhO...OpppO......OppppO..OhO...',
    '.OhO....OppppO.....OpppO..OhO...',
    '.OhO...OPpppO....OPppO....OhO...',
    '.OHO....OPPppO...OPPpO....OHO...',
    '..O......OOPPO...OPPOO.....O....',
    '.........OxxxxO.OxxxxO..........',
    '.........OxxxxO.OxxxxO..........',
    '........OxxxxxO.OxxxxxO.........',
    '.......OOXXXXOO.OOXXXXOO........',
  ],
};

const frontendWork0: SpritePatch = {
  startRow: 28,
  rows: [
    '.OhOOOOOBbbbbbbbbbbBOOOOOO.OhO..',
    '.OhOBbbOBbbbbbbbbbbBOBbbbO.OhO..',
    '.OhObbBO.ObbbbbbbbbbO.ObbO.OhO..',
    '.OhObbBO.ObbbbbbbbbbO.ObbO.OhO..',
    '.OhOsSO..ObbbbbbbbbbO..OsOOOhO..',
    '.OhOSSO..ObbbbbbbbbbO..OSOOOhO..',
  ],
};

const frontendWork1: SpritePatch = {
  startRow: 28,
  rows: [
    '.OhOOOOOBbbbbbbbbbbBOOOOOO.OhO..',
    '.OhOBbbOBbbbbbbbbbbBOBbbbO.OhO..',
    '.OhObbBO.ObbbbbbbbbbO..ObbO.OhO.',
    '.OhObbBO.ObbbbbbbbbbO..ObbO.OhO.',
    '.OhOsSO..ObbbbbbbbbbO...OsOOOhO.',
    '.OhOSSO..ObbbbbbbbbbO...OSOOOhO.',
  ],
};

// ================================================================
// BACKEND — curly dark hair, green headphones, green shirt
// ================================================================

const backendBase: string[] = [
  '........OOhhhhhhhhhOO...........',
  '.......OhhlllhhhhlllhO..........',
  '......OhhllOhllhOllhhhO.........',
  '.....OhhhlOhhhhhOlhhhhhO........',
  '.....OhhhhhhhHHHhhhhhhhO........',
  '....OtOOhhhhhhhhhhhhhOOtO.......',
  '....OtOssssssssssssssOtOO.......',
  '....OtOsssssssssssssssOtO.......',
  '....OtOssOOsssssssOOssOtO.......',
  '....OtOssOwEOsssOwEOssOtO.......',
  '....OtOssOwwOsssOwwOssOtO.......',
  '....OtOssssssssssssssssOtO......',
  '...OTtOsssssssSnSsssssOtTO......',
  '...OttOssrssssssssssrsOttO......',
  '...OTtOssssssmmmssssssOtTO......',
  '....OtO.OsssssssssssO.OtO.......',
  '....OTO..OssssssssssO..OTO......',
  '.........OssssssssssO...........',
  '..........OOssssssOO............',
  '...........OssSSSsO.............',
  '........OOBBBBcccBBBBOO.........',
  '........OLbbbbcacbbbbBO.........',
  '........OLbbbbbbbbbbbBO.........',
  '........OLbbbbddbbbbbBO.........',
  '........OLbbbbddbbbbbBO.........',
  '........OBbbbbbbbbbbbBO.........',
  '........OkkkkkAAAkkkkkO.........',
  '........OkAAAAAAAAAAAAkO........',
  '..OOO...OBbbbbbbbbbbBO...OOO....',
  '..ObBO..OBbbbbbbbbbbBO..ObBO....',
  '..ObbO..ObbbbbbbbbbbbO..ObbO....',
  '..ObbO..ObbbbbbbbbbbbO..ObbO....',
  '..OsSO..ObbbbbbbbbbbbO..OSsO....',
  '..OSSO..ObbbbbbbbbbbbO..OSSO....',
  '........OOBBBBBBBBBBBBbOO.......',
  '........OOPPPPPPPPPPPPOO........',
  '.........OQpppOO.OOpppQO........',
  '.........OppppO...OpppPO........',
  '.........OppppO...OppppO........',
  '.........OppppO...OppppO........',
  '.........OppppO...OppppO........',
  '.........OPpppO...OpppPO........',
  '.........OPPppO...OppPPO........',
  '.........OOPPPO...OPPPOO........',
  '........OOxxxxO...OxxxxOO.......',
  '........OYxxxxO...OxxxxYO.......',
  '........OxxxxxO...OxxxxxO.......',
  '.......OOXXXXOO...OOXXXXOO......',
];

const backendBlink: SpritePatch = {
  startRow: 9,
  rows: [
    '....OtOssOOOOsssOOOOssOtO.......',
    '....OtOssssssssssssssssOtO......',
  ],
};

const backendWalk0: SpritePatch = {
  startRow: 36,
  rows: [
    '.........OQpppOO.OOpppQO........',
    '........OQppppO....OppPO........',
    '........OppppO......OpppO.......',
    '........OppppO......OpppO.......',
    '.........OpppO.....OppppO.......',
    '.........OPppO....OpppPO........',
    '.........OPPpO...OppPPO.........',
    '..........OPPO...OPPOO..........',
    '.........OxxxxO.OxxxxO..........',
    '.........OxxxxO.OxxxxO..........',
    '........OxxxxxO.OxxxxxO.........',
    '.......OOXXXXOO.OOXXXXOO........',
  ],
};

const backendWalk1: SpritePatch = {
  startRow: 36,
  rows: [
    '.........OQpppOO.OOpppQO........',
    '.........OppPO....OQpppO........',
    '........OpppO......OppppO.......',
    '........OpppO......OppppO.......',
    '.........OppppO.....OpppO.......',
    '........OPpppO....OPppO.........',
    '.........OPPppO...OPPpO.........',
    '..........OOPPO...OPPOO.........',
    '..........OxxxxO.OxxxxO.........',
    '..........OxxxxO.OxxxxO.........',
    '.........OxxxxxO.OxxxxxO........',
    '........OOXXXXOO.OOXXXXOO.......',
  ],
};

const backendWork0: SpritePatch = {
  startRow: 28,
  rows: [
    '..OOO...OBbbbbbbbbbbBO...OOO....',
    '.OBbO...OBbbbbbbbbbbBO..ObBO....',
    '.ObbBO..ObbbbbbbbbbbbO..ObbO....',
    'OBbbO...ObbbbbbbbbbbbO..ObbO....',
    'OsSO....ObbbbbbbbbbbbO..OSsO....',
    'OSSO....ObbbbbbbbbbbbO..OSSO....',
  ],
};

const backendWork1: SpritePatch = {
  startRow: 28,
  rows: [
    '..OOO...OBbbbbbbbbbbBO...OOO....',
    '..ObBO..OBbbbbbbbbbbBO...ObBO...',
    '..ObbO..ObbbbbbbbbbbbO...ObbBO..',
    '..ObbO..ObbbbbbbbbbbbO....ObbO..',
    '..OsSO..ObbbbbbbbbbbbO....OSsO..',
    '..OSSO..ObbbbbbbbbbbbO....OSSO..',
  ],
};

// ================================================================
// DOCS — ponytail chestnut hair, pencil behind ear, gold shirt
// ================================================================

const docsBase: string[] = [
  '...........OOhhhhhOO............',
  '..........OhhlllhhhHO...........',
  '.........OhhllllhhhhHO..........',
  '.........OhhlllhhhhhHO..........',
  '.........OhhhhhhhhhhhO..........',
  '........OOhhhhhhhhhhhOO.........',
  '........OsssssssssssssO.........',
  '........OssssssssssssssO........',
  '........OssOOsssssssOOssO.......',
  '........OssOwEOsssOwEOssO..OkO..',
  '........OssOwwOsssOwwOssO..OkO..',
  '........OsssssssssssssssO..OkO..',
  '........OsssssssSnSsssssO..OaO..',
  '........OssrsssssssssrssO.......',
  '........OsssssssmmmssssssO......',
  '.........OsssssssssssssO........',
  '.........OssssssssssssO...OhhO..',
  '..........OsssssssssO....OhhlO..',
  '...........OOsssssOO.....OhhhO..',
  '............OsSSSsO......OhhlO..',
  '.........OOBBBcccBBBOO...OhhhO..',
  '.........OLbbbcacbbbBO...OhhlO..',
  '.........OLbbbbbbbbbBO...OhhHO..',
  '.........OLbbbbbbbbbBO...OhHHO..',
  '.........OLbbbddbbbbbO...OHhHO..',
  '.........OBbbbbbbbbbBO...OhhhO..',
  '.........OkkkkkAAAkkkkO..OhhhO..',
  '.........OkAAAAAAAAAAAAO.OhhhO..',
  '...OOO...OBbbbbbbbbbBO...OhO....',
  '...ObBO..OBbbbbbbbbbBO..........',
  '...ObbO..ObbbbbbbbbbbbO.........',
  '...ObbO..ObbbbbbbbbbbbO.........',
  '...OsSO..ObbbbbbbbbbbbO.........',
  '...OSSO..ObbbbbbbbbbbbO.........',
  '.........OOBBBBBBBBBBBBbOO......',
  '.........OOPPPPPPPPPPPPOO.......',
  '..........OQpppOO.OOpppQO.......',
  '..........OppppO...OpppPO.......',
  '..........OppppO...OppppO.......',
  '..........OppppO...OppppO.......',
  '..........OppppO...OppppO.......',
  '..........OPpppO...OpppPO.......',
  '..........OPPppO...OppPPO.......',
  '..........OOPPPO...OPPPOO.......',
  '.........OOxxxxO...OxxxxOO......',
  '.........OYxxxxO...OxxxxYO......',
  '.........OxxxxxO...OxxxxxO......',
  '........OOXXXXOO...OOXXXXOO.....',
];

const docsBlink: SpritePatch = {
  startRow: 9,
  rows: [
    '........OssOOOOsssOOOOssO..OkO..',
    '........OssssssssssssssssO..OkO.',
  ],
};

const docsWalk0: SpritePatch = {
  startRow: 36,
  rows: [
    '..........OQpppOO.OOpppQO.......',
    '.........OQppppO....OppPO.......',
    '.........OppppO......OpppO......',
    '.........OppppO......OpppO......',
    '..........OpppO.....OppppO......',
    '..........OPppO....OpppPO.......',
    '..........OPPpO...OppPPO........',
    '...........OPPO...OPPOO.........',
    '..........OxxxxO.OxxxxO.........',
    '..........OxxxxO.OxxxxO.........',
    '.........OxxxxxO.OxxxxxO........',
    '........OOXXXXOO.OOXXXXOO.......',
  ],
};

const docsWalk1: SpritePatch = {
  startRow: 36,
  rows: [
    '..........OQpppOO.OOpppQO.......',
    '..........OppPO....OQpppO.......',
    '.........OpppO......OppppO......',
    '.........OpppO......OppppO......',
    '..........OppppO.....OpppO......',
    '.........OPpppO....OPppO........',
    '..........OPPppO...OPPpO........',
    '...........OOPPO...OPPOO........',
    '...........OxxxxO.OxxxxO........',
    '...........OxxxxO.OxxxxO........',
    '..........OxxxxxO.OxxxxxO.......',
    '.........OOXXXXOO.OOXXXXOO......',
  ],
};

const docsWork0: SpritePatch = {
  startRow: 28,
  rows: [
    '...OOO...OBbbbbbbbbbBO..OhO.....',
    '..OBbO...OBbbbbbbbbbBO..........',
    '..ObbBO..ObbbbbbbbbbbbO.........',
    '.OBbbO...ObbbbbbbbbbbbO.........',
    '.OsSO....ObbbbbbbbbbbbO.........',
    '.OSSO....ObbbbbbbbbbbbO.........',
  ],
};

const docsWork1: SpritePatch = {
  startRow: 28,
  rows: [
    '...OOO...OBbbbbbbbbbBO...OhO....',
    '...ObBO..OBbbbbbbbbbBO..........',
    '...ObbO..ObbbbbbbbbbbbO.........',
    '...ObbO..ObbbbbbbbbbbbO.........',
    '...OsSO..ObbbbbbbbbbbbO.........',
    '...OSSO..ObbbbbbbbbbbbO.........',
  ],
};

// ================================================================
// Sprite registry
// ================================================================

const SPRITES: Record<string, CharacterSpriteSet> = {
  director: {
    base: directorBase,
    blinkPatch: directorBlink,
    walkPatches: [directorWalk0, directorWalk1],
    workPatches: [directorWork0, directorWork1],
  },
  git: {
    base: gitBase,
    blinkPatch: gitBlink,
    walkPatches: [gitWalk0, gitWalk1],
    workPatches: [gitWork0, gitWork1],
  },
  frontend: {
    base: frontendBase,
    blinkPatch: frontendBlink,
    walkPatches: [frontendWalk0, frontendWalk1],
    workPatches: [frontendWork0, frontendWork1],
  },
  backend: {
    base: backendBase,
    blinkPatch: backendBlink,
    walkPatches: [backendWalk0, backendWalk1],
    workPatches: [backendWork0, backendWork1],
  },
  docs: {
    base: docsBase,
    blinkPatch: docsBlink,
    walkPatches: [docsWalk0, docsWalk1],
    workPatches: [docsWork0, docsWork1],
  },
};

export function getCharacterSprite(domain: string): CharacterSpriteSet {
  return SPRITES[domain] ?? SPRITES.frontend;
}
