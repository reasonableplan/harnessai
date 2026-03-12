import { useRef, useState, useEffect, useCallback } from 'react';
import { useOfficeStore } from '@/stores/office-store';
import OfficeCanvas from '@/engine/OfficeCanvas';
import CharacterOverlay from './CharacterOverlay';
import { CANVAS_W, CANVAS_H } from '@/engine/sprite-config';

export default function OfficeScene() {
  const selectedAgent = useOfficeStore((s) => s.selectedAgent);
  const selectAgent = useOfficeStore((s) => s.selectAgent);

  // Track the actual rendered size of the canvas for overlay scaling
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [overlayScale, setOverlayScale] = useState(1);

  useEffect(() => {
    function updateScale() {
      const el = wrapperRef.current;
      if (!el) return;
      // The canvas renders with object-fit:contain inside this wrapper.
      // Compute the actual rendered canvas size to scale the overlay to match.
      const rect = el.getBoundingClientRect();
      const canvasAspect = CANVAS_W / CANVAS_H;
      const elemAspect = rect.width / rect.height;
      if (elemAspect > canvasAspect) {
        // Pillarboxed — height is the constraint
        setOverlayScale(rect.height / CANVAS_H);
      } else {
        // Letterboxed — width is the constraint
        setOverlayScale(rect.width / CANVAS_W);
      }
    }

    updateScale();
    window.addEventListener('resize', updateScale);
    return () => window.removeEventListener('resize', updateScale);
  }, []);

  const handleAgentClick = useCallback(
    (id: string | null) => {
      const current = useOfficeStore.getState().selectedAgent;
      selectAgent(current === id ? null : id);
    },
    [selectAgent],
  );

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-[#2D1B0E]">
      <div
        ref={wrapperRef}
        className="relative"
        style={{ width: '100%', height: '100%', maxHeight: 'calc(100vh - 120px)' }}
      >
        {/* Canvas-based office scene */}
        <OfficeCanvas onAgentClick={handleAgentClick} />

        {/* DOM overlay for speech bubbles — scaled to match canvas rendered area */}
        <div
          className="absolute pointer-events-none"
          style={{
            left: '50%',
            top: '50%',
            width: CANVAS_W,
            height: CANVAS_H,
            transform: `translate(-50%, -50%) scale(${overlayScale})`,
            transformOrigin: 'center center',
          }}
        >
          <CharacterOverlay />
        </div>
      </div>
    </div>
  );
}
