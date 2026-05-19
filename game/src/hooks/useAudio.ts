// React hook for audio context and playback

import { useRef, useEffect, useCallback } from 'react';
import { AudioManager } from '../engine/AudioManager';

export function useAudio(): AudioManager {
  const managerRef = useRef<AudioManager | null>(null);

  useEffect(() => {
    if (!managerRef.current) {
      managerRef.current = new AudioManager();
    }
  }, []);

  const initialize = useCallback(async () => {
    if (managerRef.current && !managerRef.current.getIsInitialized()) {
      await managerRef.current.initialize();
      await managerRef.current.preloadSounds();
    }
  }, []);

  useEffect(() => {
    return () => {
      if (managerRef.current) {
        managerRef.current.stopAmbient();
      }
    };
  }, []);

  return managerRef.current!;
}
