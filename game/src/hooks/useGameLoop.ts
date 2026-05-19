// requestAnimationFrame game loop with delta time

import { useEffect, useRef, useCallback } from 'react';

export function useGameLoop(
  callback: (deltaTime: number, time: number) => void,
  isActive: boolean
): void {
  const callbackRef = useRef(callback);
  const frameRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);

  callbackRef.current = callback;

  const loop = useCallback((time: number) => {
    if (lastTimeRef.current === 0) {
      lastTimeRef.current = time;
    }
    
    const deltaTime = time - lastTimeRef.current;
    lastTimeRef.current = time;

    callbackRef.current(deltaTime, time);
    frameRef.current = requestAnimationFrame(loop);
  }, []);

  useEffect(() => {
    if (isActive) {
      lastTimeRef.current = 0;
      frameRef.current = requestAnimationFrame(loop);
    } else {
      lastTimeRef.current = 0;
    }

    return () => {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, [isActive, loop]);
}
