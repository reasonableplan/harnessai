import { useEffect } from 'react';
import { useOfficeStore } from '@/stores/office-store';
import { apiGet, apiPut } from '@/utils/api';

export default function HooksPanel() {
  const hooksList = useOfficeStore((s) => s.hooksList);
  const setHooks = useOfficeStore((s) => s.setHooks);
  const updateHookEnabled = useOfficeStore((s) => s.updateHookEnabled);
  const addToast = useOfficeStore((s) => s.addToast);

  useEffect(() => {
    let cancelled = false;
    apiGet('/api/hooks')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (!cancelled && data.hooks) setHooks(data.hooks);
      })
      .catch(() => {
        // silently fail — hooks are optional
      });
    return () => { cancelled = true; };
  }, [setHooks]);

  const handleToggle = async (hookId: string, enabled: boolean) => {
    // Optimistic update
    updateHookEnabled(hookId, enabled);

    try {
      const res = await apiPut(`/api/hooks/${hookId}/toggle`, { enabled });
      if (!res.ok) throw new Error();
    } catch {
      // Revert
      updateHookEnabled(hookId, !enabled);
      addToast({
        id: `toast-hook-err-${Date.now()}`,
        type: 'error',
        title: 'Toggle Failed',
        message: `Failed to toggle hook "${hookId}"`,
      });
    }
  };

  if (hooksList.length === 0) return null;

  return (
    <div>
      <span className="font-pixel text-[6px] text-gray-400">HOOKS</span>
      <div className="mt-1 space-y-1">
        {hooksList.map((hook) => (
          <div
            key={hook.id}
            className="flex items-center justify-between bg-[#2D1B0E] p-1.5 border border-[#5C3A1A]"
          >
            <div className="flex-1 min-w-0">
              <div className="font-pixel text-[6px] text-gray-200 truncate">{hook.name}</div>
              {hook.description && (
                <div className="font-pixel text-[4px] text-gray-500 truncate">
                  {hook.description}
                </div>
              )}
              <div className="font-pixel text-[4px] text-gray-600">{hook.event}</div>
            </div>
            <button
              onClick={() => handleToggle(hook.id, !hook.enabled)}
              className={`ml-2 w-8 h-4 rounded-full flex-shrink-0 flex items-center transition-colors ${
                hook.enabled ? 'bg-green-600' : 'bg-gray-700'
              }`}
            >
              <div
                className={`w-3 h-3 bg-white rounded-full transition-transform ${
                  hook.enabled ? 'translate-x-4' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
