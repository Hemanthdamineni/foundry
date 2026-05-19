// Game state types and interfaces

export type GamePhase = 'loading' | 'menu' | 'playing' | 'paused' | 'choice' | 'transition' | 'ended';

export interface Choice {
  id: string;
  text: string;
  scoreDelta: number;
  nextNode: string;
  soundEffect?: 'discovery' | 'danger' | 'neutral';
}

export interface StoryNode {
  id: string;
  text: string;
  choices: Choice[];
  background?: string;
  ambientSound?: string;
  isEnding?: boolean;
}

export interface LevelConfig {
  id: number;
  name: string;
  description: string;
  startNode: string;
  nodes: Record<string, StoryNode>;
  ambientTrack: string;
}

export interface GameState {
  phase: GamePhase;
  currentLevel: number;
  currentNode: string | null;
  score: number;
  history: string[];
  textProgress: number;
  selectedChoice: number | null;
  settings: GameSettings;
}

export interface GameSettings {
  textSpeed: number; // characters per second
  volume: number; // 0-1
  muted: boolean;
  fullscreen: boolean;
}

export interface CanvasDimensions {
  width: number;
  height: number;
  dpr: number;
}
