// Keyboard navigation hook with key mapping

import { useEffect, useRef, useCallback } from 'react';

type KeyHandler = (key: string) => void;

export function useKeyboard(onKey: KeyHandler, isActive: boolean): void {
  const handlerRef = useRef(onKey);
  handlerRef.current = onKey;

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!isActive) return;
    
    const key = e.key.toLowerCase();
    const allowedKeys = [
      'arrowup', 'arrowdown', 'arrowleft', 'arrowright',
      'enter', 'escape', 'space', 'tab',
      '1', '2', '3', '4', '5', '6', '7', '8', '9',
      'p', 'm', 's', 'l',
    ];

    if (allowedKeys.includes(key)) {
      e.preventDefault();
      handlerRef.current(key);
    }
  }, [isActive]);

  useEffect(() => {
    if (isActive) {
      window.addEventListener('keydown', handleKeyDown);
    }

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isActive, handleKeyDown]);
}
