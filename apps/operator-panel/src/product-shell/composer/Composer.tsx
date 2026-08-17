import { useState } from 'react';

export function Composer({ disabled = false, onSend }: { disabled?: boolean; onSend: (message: string) => void }) {
  const [value, setValue] = useState('');
  const submit = () => {
    const message = value.trim();
    if (!message || disabled) return;
    onSend(message);
    setValue('');
  };
  return <form className="ps-composer" onSubmit={(event) => { event.preventDefault(); submit(); }}>
    <textarea aria-label="Message ImperaOS" value={value} disabled={disabled}
      placeholder="Describe the outcome you need…" onChange={(event) => setValue(event.target.value)} />
    <button type="submit" disabled={disabled || !value.trim()}>{disabled ? 'Running' : 'Send'}</button>
  </form>;
}
