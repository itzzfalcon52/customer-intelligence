import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { SignalExplorer } from './SignalExplorer';

export function DemoDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (open && !dialog?.open) dialog?.showModal();
    if (!open && dialog?.open) dialog.close();
    if (open) {
      const previous = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = previous;
      };
    }
  }, [open]);
  return (
    <dialog
      className="demo-dialog"
      ref={ref}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      aria-labelledby="demo-title"
    >
      <div className="dialog-top">
        <div>
          <span className="eyebrow">TAKE A CLOSER LOOK</span>
          <h2 id="demo-title">From a signal to a next step.</h2>
        </div>
        <button
          className="icon-button"
          aria-label="Close product tour"
          onClick={onClose}
        >
          <X />
        </button>
      </div>
      {open && <SignalExplorer idPrefix="dialog" />}
    </dialog>
  );
}
