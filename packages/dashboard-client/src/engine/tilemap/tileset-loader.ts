/**
 * Tileset image loader — async loading with per-tileset failure isolation.
 * Pattern matches sprite-loader.ts for consistency.
 */

const TILESET_PATHS = {
  roomBuilder: '/assets/tilesets/room-builder-16x16.png',
  modernInteriors: '/assets/tilesets/modern-interiors-16x16.png',
  kitchen: '/assets/tilesets/kitchen-16x16.png',
} as const;

export interface TilesetCache {
  roomBuilder: HTMLImageElement | null;
  modernInteriors: HTMLImageElement | null;
  kitchen: HTMLImageElement | null;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

/** Load all tileset images. Each tileset loads independently — failure is per-tileset, not global. */
export async function loadAllTilesets(): Promise<TilesetCache> {
  const cache: TilesetCache = {
    roomBuilder: null,
    modernInteriors: null,
    kitchen: null,
  };

  const entries = Object.entries(TILESET_PATHS) as [keyof TilesetCache, string][];
  await Promise.allSettled(
    entries.map(async ([key, src]) => {
      try {
        cache[key] = await loadImage(src);
      } catch {
        if (import.meta.env.DEV) console.warn(`[tileset-loader] Failed to load ${src}`);
      }
    }),
  );

  return cache;
}
