import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useOfficeStore, type ToastState } from '@/stores/office-store';

const TYPE_STYLES: Record<string, { bg: string; border: string; icon: string }> = {
  success: { bg: 'bg-green-900/80', border: 'border-green-500', icon: '[+]' },
  error: { bg: 'bg-red-900/80', border: 'border-red-500', icon: '[!]' },
  info: { bg: 'bg-blue-900/80', border: 'border-blue-500', icon: '[i]' },
  warning: { bg: 'bg-yellow-900/80', border: 'border-yellow-500', icon: '[?]' },
};

function Toast({ toast }: { toast: ToastState }) {
  const removeToast = useOfficeStore((s) => s.removeToast);
  const style = TYPE_STYLES[toast.type] ?? TYPE_STYLES.info;

  useEffect(() => {
    const timer = setTimeout(() => removeToast(toast.id), 5000);
    return () => clearTimeout(timer);
  }, [toast.id, removeToast]);

  return (
    <motion.div
      layout
      initial={{ x: 100, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 100, opacity: 0 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      className={`${style.bg} border-l-4 ${style.border} px-3 py-2 min-w-[200px] max-w-[280px] cursor-pointer`}
      onClick={() => removeToast(toast.id)}
    >
      <div className="flex items-start gap-1.5">
        <span className="font-pixel text-[8px] text-gray-300">{style.icon}</span>
        <div>
          <div className="font-pixel text-[7px] text-gray-100">{toast.title}</div>
          <div className="font-pixel text-[5px] text-gray-400 mt-0.5">{toast.message}</div>
        </div>
      </div>
    </motion.div>
  );
}

export default function ToastContainer() {
  const toasts = useOfficeStore((s) => s.toasts);

  return (
    <div className="fixed top-14 right-4 z-40 flex flex-col gap-2">
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <Toast key={toast.id} toast={toast} />
        ))}
      </AnimatePresence>
    </div>
  );
}
