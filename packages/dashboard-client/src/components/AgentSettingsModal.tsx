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

const MODELS = [
  'claude-sonnet-4-20250514',
  'claude-opus-4-20250514',
  'claude-haiku-4-5-20251001',
];

interface ConfigForm {
  claudeModel: string;
  maxTokens: number;
  temperature: number;
  tokenBudget: number;
  taskTimeoutMs: number;
  pollIntervalMs: number;
}

const DEFAULTS: ConfigForm = {
  claudeModel: 'claude-sonnet-4-20250514',
  maxTokens: 4096,
  temperature: 0.7,
  tokenBudget: 10_000_000,
  taskTimeoutMs: 300_000,
  pollIntervalMs: 10_000,
};

type SettingsTab = 'config' | 'character';

const PREVIEW_SCALE = 4;
const PREVIEW_W = SPRITE_FRAME_W * PREVIEW_SCALE;
const PREVIEW_H = SPRITE_FRAME_H * PREVIEW_SCALE;

export default function AgentSettingsModal() {
  const agentId = useOfficeStore((s) => s.settingsModalAgent);
  const closeModal = useOfficeStore((s) => s.closeSettingsModal);
  const addToast = useOfficeStore((s) => s.addToast);
  const bumpVersion = useOfficeStore((s) => s.bumpCharacterVersion);

  const [tab, setTab] = useState<SettingsTab>('config');
  const [form, setForm] = useState<ConfigForm>(DEFAULTS);
  const [saving, setSaving] = useState(false);
  const initialLoadDoneRef = useRef(false);

  // Character state
  const catalog = getCharacterCatalog();
  const [selectedChar, setSelectedChar] = useState<string | null>(null);
  const canvasRefs = useRef<Map<string, HTMLCanvasElement>>(new Map());

  // Reset tab when modal opens
  useEffect(() => {
    if (agentId) setTab('config');
  }, [agentId]);

  // Load config
  useEffect(() => {
    if (!agentId) return;
    initialLoadDoneRef.current = false;
    setForm(DEFAULTS);

    let cancelled = false;
    const baseUrl = import.meta.env.VITE_API_URL ?? '';
    fetch(`${baseUrl}/api/agents/${agentId}/config`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (cancelled) return;
        if (data.config) {
          setForm({
            claudeModel: data.config.claudeModel ?? DEFAULTS.claudeModel,
            maxTokens: data.config.maxTokens ?? DEFAULTS.maxTokens,
            temperature: data.config.temperature ?? DEFAULTS.temperature,
            tokenBudget: data.config.tokenBudget ?? DEFAULTS.tokenBudget,
            taskTimeoutMs: data.config.taskTimeoutMs ?? DEFAULTS.taskTimeoutMs,
            pollIntervalMs: data.config.pollIntervalMs ?? DEFAULTS.pollIntervalMs,
          });
        }
        initialLoadDoneRef.current = true;
      })
      .catch(() => {
        if (!cancelled && !initialLoadDoneRef.current) setForm(DEFAULTS);
      });
    return () => { cancelled = true; };
  }, [agentId]);

  // Load current character assignment
  useEffect(() => {
    if (!agentId) return;
    const collection = getSpriteCollection();
    if (collection) {
      setSelectedChar(collection.assignments[agentId] ?? null);
    }
  }, [agentId]);

  // Draw character previews when character tab is active
  useEffect(() => {
    if (!agentId || tab !== 'character') return;
    const collection = getSpriteCollection();
    if (!collection) return;

    for (const def of catalog) {
      const canvas = canvasRefs.current.get(def.id);
      if (!canvas) continue;
      const ctx = canvas.getContext('2d');
      if (!ctx) continue;

      ctx.clearRect(0, 0, PREVIEW_W, PREVIEW_H);
      ctx.imageSmoothingEnabled = false;

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
  }, [agentId, tab, catalog]);

  const handleSaveConfig = async () => {
    if (!agentId) return;
    setSaving(true);
    try {
      const baseUrl = import.meta.env.VITE_API_URL ?? '';
      const res = await fetch(`${baseUrl}/api/agents/${agentId}/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        addToast({
          id: `toast-config-${Date.now()}`,
          type: 'success',
          title: 'Config Saved',
          message: `${agentId} configuration updated`,
        });
        closeModal();
      } else {
        addToast({
          id: `toast-config-err-${Date.now()}`,
          type: 'error',
          title: 'Save Failed',
          message: `Server returned ${res.status}`,
        });
      }
    } catch {
      addToast({
        id: `toast-config-err-${Date.now()}`,
        type: 'error',
        title: 'Save Failed',
        message: 'Failed to save configuration',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleSaveCharacter = () => {
    if (!agentId || !selectedChar) return;

    const collection = getSpriteCollection();
    const currentAssignments = collection?.assignments ?? {};
    const newAssignments = { ...currentAssignments, [agentId]: selectedChar };

    saveAssignments(newAssignments);

    if (collection) {
      collection.assignments = newAssignments;
    }

    rebuildCache();
    bumpVersion();

    addToast({
      id: `toast-char-${Date.now()}`,
      type: 'success',
      title: 'Character Changed',
      message: `${agentId} is now ${selectedChar}`,
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
            className="bg-[#3A2410] border-2 border-[#5C3A1A] w-80 max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-[#5C3A1A]">
              <span className="font-pixel text-[8px] text-amber-300">
                SETTINGS: {agentId.toUpperCase()}
              </span>
              <button
                onClick={closeModal}
                className="font-pixel text-[10px] text-gray-500 hover:text-gray-200 px-1"
              >
                X
              </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-[#5C3A1A]">
              <button
                onClick={() => setTab('config')}
                className={`flex-1 py-1.5 font-pixel text-[7px] transition-colors ${
                  tab === 'config'
                    ? 'text-amber-300 bg-[#4A3420] border-b-2 border-amber-400'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                CONFIG
              </button>
              <button
                onClick={() => setTab('character')}
                className={`flex-1 py-1.5 font-pixel text-[7px] transition-colors ${
                  tab === 'character'
                    ? 'text-amber-300 bg-[#4A3420] border-b-2 border-amber-400'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                CHARACTER
              </button>
            </div>

            {/* Config Tab */}
            {tab === 'config' && (
              <>
                <div className="p-3 space-y-3">
                  {/* Model */}
                  <div>
                    <label className="font-pixel text-[6px] text-gray-400 block mb-1">MODEL</label>
                    <select
                      value={form.claudeModel}
                      onChange={(e) => setForm({ ...form, claudeModel: e.target.value })}
                      className="w-full bg-[#2D1B0E] border border-[#5C3A1A] text-gray-200 font-pixel text-[6px] px-2 py-1"
                    >
                      {MODELS.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>

                  {/* Max Tokens */}
                  <div>
                    <label className="font-pixel text-[6px] text-gray-400 block mb-1">MAX TOKENS</label>
                    <input
                      type="number"
                      min={100}
                      max={200000}
                      value={form.maxTokens}
                      onChange={(e) => setForm({ ...form, maxTokens: Number(e.target.value) })}
                      className="w-full bg-[#2D1B0E] border border-[#5C3A1A] text-gray-200 font-pixel text-[6px] px-2 py-1"
                    />
                  </div>

                  {/* Temperature */}
                  <div>
                    <label className="font-pixel text-[6px] text-gray-400 block mb-1">
                      TEMPERATURE ({form.temperature.toFixed(2)})
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={form.temperature}
                      onChange={(e) => setForm({ ...form, temperature: Number(e.target.value) })}
                      className="w-full"
                    />
                  </div>

                  {/* Token Budget */}
                  <div>
                    <label className="font-pixel text-[6px] text-gray-400 block mb-1">TOKEN BUDGET</label>
                    <input
                      type="number"
                      min={1000}
                      max={100000000}
                      value={form.tokenBudget}
                      onChange={(e) => setForm({ ...form, tokenBudget: Number(e.target.value) })}
                      className="w-full bg-[#2D1B0E] border border-[#5C3A1A] text-gray-200 font-pixel text-[6px] px-2 py-1"
                    />
                  </div>

                  {/* Task Timeout */}
                  <div>
                    <label className="font-pixel text-[6px] text-gray-400 block mb-1">
                      TASK TIMEOUT (ms)
                    </label>
                    <input
                      type="number"
                      min={5000}
                      max={3600000}
                      value={form.taskTimeoutMs}
                      onChange={(e) => setForm({ ...form, taskTimeoutMs: Number(e.target.value) })}
                      className="w-full bg-[#2D1B0E] border border-[#5C3A1A] text-gray-200 font-pixel text-[6px] px-2 py-1"
                    />
                  </div>

                  {/* Poll Interval */}
                  <div>
                    <label className="font-pixel text-[6px] text-gray-400 block mb-1">
                      POLL INTERVAL (ms)
                    </label>
                    <input
                      type="number"
                      min={1000}
                      max={300000}
                      value={form.pollIntervalMs}
                      onChange={(e) => setForm({ ...form, pollIntervalMs: Number(e.target.value) })}
                      className="w-full bg-[#2D1B0E] border border-[#5C3A1A] text-gray-200 font-pixel text-[6px] px-2 py-1"
                    />
                  </div>
                </div>

                {/* Config Footer */}
                <div className="px-3 py-2 border-t border-[#5C3A1A] flex gap-2">
                  <button
                    onClick={closeModal}
                    className="pixel-btn text-[6px] flex-1"
                  >
                    CANCEL
                  </button>
                  <button
                    onClick={handleSaveConfig}
                    disabled={saving}
                    className="pixel-btn text-[6px] flex-1 !bg-amber-700 hover:!bg-amber-600"
                  >
                    {saving ? 'SAVING...' : 'SAVE'}
                  </button>
                </div>
              </>
            )}

            {/* Character Tab */}
            {tab === 'character' && (
              <>
                <div className="p-3 grid grid-cols-2 gap-3">
                  {catalog.map((def) => (
                    <button
                      key={def.id}
                      onClick={() => setSelectedChar(def.id)}
                      className={`flex flex-col items-center gap-1 p-2 border-2 transition-colors ${
                        selectedChar === def.id
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

                {/* Character Footer */}
                <div className="px-3 py-2 border-t border-[#5C3A1A] flex gap-2">
                  <button
                    onClick={closeModal}
                    className="pixel-btn text-[6px] flex-1"
                  >
                    CANCEL
                  </button>
                  <button
                    onClick={handleSaveCharacter}
                    disabled={!selectedChar}
                    className="pixel-btn text-[6px] flex-1 !bg-amber-700 hover:!bg-amber-600 disabled:opacity-50"
                  >
                    SELECT
                  </button>
                </div>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
