// localStorage save/load utilities

import { STORAGE_KEY } from './constants';
import { GameState } from '../types/game';

export function saveGame(state: Partial<GameState>): void {
  try {
    const existing = loadGame();
    const merged = { ...existing, ...state };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  } catch (e) {
    console.warn('Failed to save game:', e);
  }
}

export function loadGame(): Partial<GameState> | null {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    if (data) {
      return JSON.parse(data);
    }
  } catch (e) {
    console.warn('Failed to load game:', e);
  }
  return null;
}

export function clearSave(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (e) {
    console.warn('Failed to clear save:', e);
  }
}

export function hasSave(): boolean {
  return loadGame() !== null;
}
