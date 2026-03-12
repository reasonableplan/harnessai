import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useOfficeStore } from '@/stores/office-store';

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

export default function AgentSettingsModal() {
  const agentId = useOfficeStore((s) => s.settingsModalAgent);
  const closeModal = useOfficeStore((s) => s.closeSettingsModal);
  const addToast = useOfficeStore((s) => s.addToast);

  const [form, setForm] = useState<ConfigForm>(DEFAULTS);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!agentId) return;
    setForm(DEFAULTS); // Reset immediately to prevent stale form from previous agent

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
      })
      .catch(() => {
        if (!cancelled) setForm(DEFAULTS);
      });
    return () => { cancelled = true; };
  }, [agentId]);

  const handleSave = async () => {
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

            {/* Form */}
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
                  value={form.pollIntervalMs}
                  onChange={(e) => setForm({ ...form, pollIntervalMs: Number(e.target.value) })}
                  className="w-full bg-[#2D1B0E] border border-[#5C3A1A] text-gray-200 font-pixel text-[6px] px-2 py-1"
                />
              </div>
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
                disabled={saving}
                className="pixel-btn text-[6px] flex-1 !bg-amber-700 hover:!bg-amber-600"
              >
                {saving ? 'SAVING...' : 'SAVE'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
