import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useOfficeStore } from '@/stores/office-store';
import {
  getCharacterCatalog,
  saveAssignments,
  SPRITE_FRAME_W,
  SPRITE_FRAME_H,
} from '@/engine/character/sprite-loader';
import { getSpriteCollection, rebuildCache } from '@/engine/character/prerender';

const PREVIEW_SCALE = 4;
const PREVIEW_W = SPRITE_FRAME_W * PREVIEW_SCALE;
const PREVIEW_H = SPRITE_FRAME_H * PREVIEW_SCALE;

export default function CharacterSelectModal() {
  const agentId = useOfficeStore((s) => s.characterModalAgent);
  const closeModal = useOfficeStore((s) => s.closeCharacterModal);
  const bumpVersion = useOfficeStore((s) => s.bumpCharacterVersion);
  const addToast = useOfficeStore((s) => s.addToast);

  const catalog = getCharacterCatalog();
  const [selected, setSelected] = useState<string | null>(null);
  const canvasRefs = useRef<Map<string, HTMLCanvasElement>>(new Map());

  // Load current assignment when modal opens
  useEffect(() => {
    if (!agentId) return;
    const collection = getSpriteCollection();
    if (collection) {
      setSelected(collection.assignments[agentId] ?? null);
    }
  }, [agentId]);

  // Draw character previews
  useEffect(() => {
    if (!agentId) return;
    const collection = getSpriteCollection();
    if (!collection) return;

    for (const def of catalog) {
      const canvas = canvasRefs.current.get(def.id);
      if (!canvas) continue;
      const ctx = canvas.getContext('2d');
      if (!ctx) continue;

      ctx.clearRect(0, 0, PREVIEW_W, PREVIEW_H);
      ctx.imageSmoothingEnabled = false;

      // Draw idle-down frame from the character's spritesheet
      const sheets = collection.characters.get(def.id);
      const idleSheet = sheets?.get('idle');
      if (idleSheet) {
        ctx.drawImage(
          idleSheet,
          0, 0, SPRITE_FRAME_W, SPRITE_FRAME_H,
          0, 0, PREVIEW_W, PREVIEW_H,
        );
      }
    }
  }, [agentId, catalog]);

  const handleSave = () => {
    if (!agentId || !selected) return;

    const collection = getSpriteCollection();
    const currentAssignments = collection?.assignments ?? {};
    const newAssignments = { ...currentAssignments, [agentId]: selected };

    saveAssignments(newAssignments);

    // Update the sprite collection's assignments in-place for rebuildCache
    if (collection) {
      collection.assignments = newAssignments;
    }

    rebuildCache();
    bumpVersion();

    addToast({
      id: `toast-char-${Date.now()}`,
      type: 'success',
      title: 'Character Changed',
      message: `${agentId} is now ${selected}`,
    });
    closeModal();
  };

  return (
    <AnimatePresence>
      {agentId && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={closeModal}
        >
          <motion.div
            initial={{ scale: 0.9 }}
            animate={{ scale: 1 }}
            exit={{ scale: 0.9 }}
            className="bg-[#3A2410] border-2 border-[#5C3A1A] w-72"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-[#5C3A1A]">
              <span className="font-pixel text-[8px] text-amber-300">
                CHARACTER: {agentId.toUpperCase()}
              </span>
              <button
                onClick={closeModal}
                className="font-pixel text-[10px] text-gray-500 hover:text-gray-200 px-1"
              >
                X
              </button>
            </div>

            {/* Character Grid */}
            <div className="p-3 grid grid-cols-2 gap-3">
              {catalog.map((def) => (
                <button
                  key={def.id}
                  onClick={() => setSelected(def.id)}
                  className={`flex flex-col items-center gap-1 p-2 border-2 transition-colors ${
                    selected === def.id
                      ? 'border-amber-400 bg-[#4A3420]'
                      : 'border-[#5C3A1A] bg-[#2D1B0E] hover:border-amber-700'
                  }`}
                >
                  <canvas
                    ref={(el) => {
                      if (el) canvasRefs.current.set(def.id, el);
                    }}
                    width={PREVIEW_W}
                    height={PREVIEW_H}
                    style={{
                      width: PREVIEW_W,
                      height: PREVIEW_H,
                      imageRendering: 'pixelated',
                    }}
                  />
                  <span className="font-pixel text-[6px] text-gray-300">
                    {def.name}
                  </span>
                </button>
              ))}
            </div>

            {/* Footer */}
            <div className="px-3 py-2 border-t border-[#5C3A1A] flex gap-2">
              <button
                onClick={closeModal}
                className="pixel-btn text-[6px] flex-1"
              >
                CANCEL
              </button>
              <button
                onClick={handleSave}
                disabled={!selected}
                className="pixel-btn text-[6px] flex-1 !bg-amber-700 hover:!bg-amber-600 disabled:opacity-50"
              >
                SELECT
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
