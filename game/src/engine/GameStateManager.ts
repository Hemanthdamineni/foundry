// Centralized state: score, level, current node, history

import { GameState, GamePhase, GameSettings, StoryNode, LevelConfig } from '../types/game';
import { TIMINGS } from '../utils/constants';

const defaultSettings: GameSettings = {
  textSpeed: TIMINGS.defaultTextSpeed,
  volume: 0.7,
  muted: false,
  fullscreen: false,
};

export class GameStateManager {
  private state: GameState;
  private levels: LevelConfig[];
  private listeners: Array<(state: GameState) => void>;

  constructor(levels: LevelConfig[]) {
    this.levels = levels;
    this.listeners = [];
    this.state = {
      phase: 'menu',
      currentLevel: 0,
      currentNode: null,
      score: 0,
      history: [],
      textProgress: 0,
      selectedChoice: null,
      settings: defaultSettings,
    };
  }

  getState(): GameState {
    return { ...this.state };
  }

  subscribe(listener: (state: GameState) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }

  private notify(): void {
    const stateCopy = { ...this.state };
    this.listeners.forEach(listener => listener(stateCopy));
  }

  startGame(levelIndex: number = 0): void {
    const level = this.levels[levelIndex];
    if (!level) return;

    this.state = {
      ...this.state,
      phase: 'playing',
      currentLevel: levelIndex,
      currentNode: level.startNode,
      score: 0,
      history: [],
      textProgress: 0,
      selectedChoice: null,
    };
    this.notify();
  }

  loadState(partial: Partial<GameState>): void {
    this.state = {
      ...this.state,
      ...partial,
      phase: partial.phase ?? 'playing',
    };
    this.notify();
  }

  updateTextProgress(progress: number): void {
    this.state.textProgress = progress;
    this.notify();
  }

  selectChoice(index: number): void {
    this.state.selectedChoice = index;
    this.state.phase = 'choice';
    this.notify();
  }

  makeChoice(choiceIndex: number): { node: StoryNode | null; levelComplete: boolean } {
    const currentLevel = this.levels[this.state.currentLevel];
    if (!currentLevel || !this.state.currentNode) {
      return { node: null, levelComplete: false };
    }

    const currentNode = currentLevel.nodes[this.state.currentNode];
    if (!currentNode || !currentNode.choices[choiceIndex]) {
      return { node: null, levelComplete: false };
    }

    const choice = currentNode.choices[choiceIndex];
    this.state.score += choice.scoreDelta;
    this.state.history.push(choice.id);

    // Check if this is an ending
    const nextNode = currentLevel.nodes[choice.nextNode];
    if (nextNode?.isEnding) {
      // Check if there are more levels
      if (this.state.currentLevel < this.levels.length - 1) {
        this.state.phase = 'transition';
        this.notify();
        return { node: nextNode, levelComplete: true };
      } else {
        this.state.phase = 'ended';
        this.notify();
        return { node: nextNode, levelComplete: false };
      }
    }

    this.state.currentNode = choice.nextNode;
    this.state.phase = 'playing';
    this.state.textProgress = 0;
    this.state.selectedChoice = null;
    this.notify();

    return { node: nextNode, levelComplete: false };
  }

  nextLevel(): void {
    const nextLevelIndex = this.state.currentLevel + 1;
    if (nextLevelIndex >= this.levels.length) {
      this.state.phase = 'ended';
      this.notify();
      return;
    }

    const level = this.levels[nextLevelIndex];
    this.state = {
      ...this.state,
      currentLevel: nextLevelIndex,
      currentNode: level.startNode,
      phase: 'playing',
      textProgress: 0,
      selectedChoice: null,
    };
    this.notify();
  }

  pause(): void {
    if (this.state.phase === 'playing' || this.state.phase === 'choice') {
      this.state.phase = 'paused';
      this.notify();
    }
  }

  resume(): void {
    if (this.state.phase === 'paused') {
      this.state.phase = 'playing';
      this.notify();
    }
  }

  updateSettings(settings: Partial<GameSettings>): void {
    this.state.settings = { ...this.state.settings, ...settings };
    this.notify();
  }

  getCurrentNode(): StoryNode | null {
    const level = this.levels[this.state.currentLevel];
    if (!level || !this.state.currentNode) return null;
    return level.nodes[this.state.currentNode] ?? null;
  }

  getCurrentLevel(): LevelConfig | null {
    return this.levels[this.state.currentLevel] ?? null;
  }

  getLevels(): LevelConfig[] {
    return this.levels;
  }

  reset(): void {
    this.state = {
      phase: 'menu',
      currentLevel: 0,
      currentNode: null,
      score: 0,
      history: [],
      textProgress: 0,
      selectedChoice: null,
      settings: defaultSettings,
    };
    this.notify();
  }
}
