// Game constants

export const COLORS = {
  background: '#0a0a0f',
  text: '#e0e0e0',
  textDim: '#888888',
  accent: '#00ff88',
  accentDim: '#00aa55',
  danger: '#ff4444',
  warning: '#ffaa00',
  choiceBg: '#1a1a2e',
  choiceHover: '#2a2a4e',
  choiceSelected: '#3a3a6e',
  hudBg: 'rgba(10, 10, 15, 0.9)',
  overlayBg: 'rgba(0, 0, 0, 0.8)',
  border: '#333344',
};

export const TIMINGS = {
  defaultTextSpeed: 30, // characters per second
  fastTextSpeed: 60,
  slowTextSpeed: 15,
  transitionDuration: 1000, // ms
  choiceHoverDelay: 100, // ms
};

export const CANVAS = {
  minWidth: 800,
  minHeight: 600,
  maxWidth: 1200,
  maxHeight: 800,
  padding: 40,
  textLineHeight: 28,
  choiceHeight: 50,
  choiceGap: 12,
  hudHeight: 50,
};

export const STORAGE_KEY = 'text-adventure-save';

export const AUDIO = {
  click: '/assets/audio/click.wav',
  hover: '/assets/audio/hover.wav',
  discovery: '/assets/audio/event-discovery.wav',
  danger: '/assets/audio/event-danger.wav',
  ambient1: '/assets/audio/ambient-level1.wav',
  ambient2: '/assets/audio/ambient-level2.wav',
  ambient3: '/assets/audio/ambient-level3.wav',
};
