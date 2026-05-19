// Main Canvas rendering component

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { CanvasRenderer } from '../engine/CanvasRenderer';
import { TextEngine } from '../engine/TextEngine';
import { GameStateManager } from '../engine/GameStateManager';
import { AudioManager } from '../engine/AudioManager';
import { useGameLoop } from '../hooks/useGameLoop';
import { useKeyboard } from '../hooks/useKeyboard';
import { COLORS, CANVAS, TIMINGS } from '../utils/constants';
import { StoryNode, Choice, GamePhase } from '../types/game';

interface GameCanvasProps {
  gameState: GameStateManager;
  audioManager: AudioManager;
  onChoice: (index: number) => void;
  onNextLevel: () => void;
  onTogglePause: () => void;
  onToggleSettings: () => void;
}

export const GameCanvas: React.FC<GameCanvasProps> = ({
  gameState,
  audioManager,
  onChoice,
  onNextLevel,
  onTogglePause,
  onToggleSettings,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<CanvasRenderer | null>(null);
  const textEngineRef = useRef<TextEngine | null>(null);
  const [hoveredChoice, setHoveredChoice] = useState<number | null>(null);
  const [choiceBounds, setChoiceBounds] = useState<Array<{ x: number; y: number; w: number; h: number }>>([]);
  const [gameStateSnapshot, setGameStateSnapshot] = useState(gameState.getState());
  const [currentNode, setCurrentNode] = useState<StoryNode | null>(null);

  // Subscribe to game state changes
  useEffect(() => {
    const unsubscribe = gameState.subscribe((state) => {
      setGameStateSnapshot(state);
      const node = gameState.getCurrentNode();
      setCurrentNode(node);

      if (node && state.phase === 'playing') {
        textEngineRef.current = new TextEngine(
          node.text,
          state.settings.textSpeed
        );
      }

      // Play ambient sound on level change
      if (state.phase === 'playing') {
        const level = gameState.getCurrentLevel();
        if (level) {
          const ambientMap: Record<number, 'ambient1' | 'ambient2' | 'ambient3'> = {
            0: 'ambient1',
            1: 'ambient2',
            2: 'ambient3',
          };
          audioManager.playAmbient(ambientMap[level.id - 1] ?? 'ambient1');
        }
      }
    });

    // Initialize with current node
    const node = gameState.getCurrentNode();
    setCurrentNode(node);
    if (node) {
      textEngineRef.current = new TextEngine(
        node.text,
        gameState.getState().settings.textSpeed
      );
    }

    return unsubscribe;
  }, [gameState, audioManager]);

  // Canvas setup
  useEffect(() => {
    if (!canvasRef.current) return;

    const canvas = canvasRef.current;
    rendererRef.current = new CanvasRenderer(canvas);

    const handleResize = () => {
      if (rendererRef.current) {
        const rect = canvas.getBoundingClientRect();
        rendererRef.current.resize(rect.width, rect.height);
      }
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Click handler for choices
  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !rendererRef.current) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const state = gameStateSnapshot;

    // Handle menu click
    if (state.phase === 'menu') {
      audioManager.initialize().then(() => {
        gameState.startGame(0);
        audioManager.playSound('click');
      });
      return;
    }

    // Handle click to skip text animation
    if (state.phase === 'playing' && textEngineRef.current && !textEngineRef.current.getIsComplete()) {
      textEngineRef.current.skip();
      audioManager.playSound('click');
      return;
    }

    // Handle choice clicks
    if (state.phase === 'playing' && textEngineRef.current?.getIsComplete() && currentNode?.choices.length) {
      for (let i = 0; i < choiceBounds.length; i++) {
        const bounds = choiceBounds[i];
        if (x >= bounds.x && x <= bounds.x + bounds.w && y >= bounds.y && y <= bounds.y + bounds.h) {
          audioManager.playSound(currentNode.choices[i].soundEffect ?? 'click');
          onChoice(i);
          return;
        }
      }
    }

    // Handle end screen click
    if (state.phase === 'ended') {
      gameState.reset();
      audioManager.playSound('click');
      return;
    }

    // Handle transition click
    if (state.phase === 'transition') {
      onNextLevel();
      audioManager.playSound('click');
      return;
    }
  }, [gameStateSnapshot, currentNode, choiceBounds, gameState, audioManager, onChoice, onNextLevel]);

  // Mouse move for hover effects
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    let newHover: number | null = null;
    for (let i = 0; i < choiceBounds.length; i++) {
      const bounds = choiceBounds[i];
      if (x >= bounds.x && x <= bounds.x + bounds.w && y >= bounds.y && y <= bounds.y + bounds.h) {
        newHover = i;
        break;
      }
    }

    if (newHover !== hoveredChoice) {
      setHoveredChoice(newHover);
      if (newHover !== null && gameStateSnapshot.phase === 'playing') {
        audioManager.playSound('hover');
      }
    }
  }, [choiceBounds, hoveredChoice, gameStateSnapshot.phase, audioManager]);

  // Keyboard handler
  const handleKey = useCallback((key: string) => {
    const state = gameStateSnapshot;

    if (state.phase === 'menu' && (key === 'enter' || key === ' ')) {
      audioManager.initialize().then(() => {
        gameState.startGame(0);
        audioManager.playSound('click');
      });
      return;
    }

    if (key === 'p' || key === 'escape') {
      if (state.phase === 'playing' || state.phase === 'choice') {
        onTogglePause();
        audioManager.playSound('click');
      } else if (state.phase === 'paused') {
        onTogglePause();
        audioManager.playSound('click');
      }
      return;
    }

    if (state.phase === 'playing' && textEngineRef.current && !textEngineRef.current.getIsComplete()) {
      if (key === ' ' || key === 'enter') {
        textEngineRef.current.skip();
        audioManager.playSound('click');
      }
      return;
    }

    // Number keys for choices
    if (state.phase === 'playing' && textEngineRef.current?.getIsComplete() && currentNode?.choices.length) {
      const num = parseInt(key, 10);
      if (num >= 1 && num <= currentNode.choices.length) {
        const choiceIndex = num - 1;
        audioManager.playSound(currentNode.choices[choiceIndex].soundEffect ?? 'click');
        onChoice(choiceIndex);
        return;
      }
    }

    // Arrow keys for choice navigation
    if (state.phase === 'playing' && textEngineRef.current?.getIsComplete() && currentNode?.choices.length) {
      if (key === 'arrowdown' || key === 'arrowright') {
        setHoveredChoice(prev => {
          const next = prev === null ? 0 : Math.min(prev + 1, currentNode.choices.length - 1);
          return next;
        });
      } else if (key === 'arrowup' || key === 'arrowleft') {
        setHoveredChoice(prev => {
          const next = prev === null ? currentNode.choices.length - 1 : Math.max(prev - 1, 0);
          return next;
        });
      } else if (key === 'enter' && hoveredChoice !== null) {
        audioManager.playSound(currentNode.choices[hoveredChoice].soundEffect ?? 'click');
        onChoice(hoveredChoice);
      }
    }

    if (state.phase === 'ended' && (key === 'enter' || key === ' ')) {
      gameState.reset();
      audioManager.playSound('click');
    }

    if (state.phase === 'transition' && (key === 'enter' || key === ' ')) {
      onNextLevel();
      audioManager.playSound('click');
    }
  }, [gameStateSnapshot, currentNode, hoveredChoice, gameState, audioManager, onChoice, onNextLevel, onTogglePause]);

  useKeyboard(handleKey, true);

  // Game loop for rendering
  const render = useCallback((_deltaTime: number, time: number) => {
    const renderer = rendererRef.current;
    if (!renderer) return;

    const { width, height } = renderer.getDimensions();
    renderer.clear();
    renderer.fillBackground(COLORS.background);

    // Draw ambient particles
    renderer.drawParticles(50, COLORS.accent, time);

    const state = gameStateSnapshot;
    const padding = CANVAS.padding;
    const textWidth = width - padding * 2;

    // Render based on phase
    if (state.phase === 'menu') {
      renderMenu(renderer, width, height, time);
    } else if (state.phase === 'playing' || state.phase === 'choice') {
      const text = textEngineRef.current?.getVisibleText() ?? '';
      const bounds = renderGame(renderer, width, height, text, currentNode, hoveredChoice, state, time);
      setChoiceBounds(bounds);

      // Update text engine
      if (textEngineRef.current && state.phase === 'playing') {
        textEngineRef.current.update(time);
      }
    } else if (state.phase === 'paused') {
      const text = textEngineRef.current?.getVisibleText() ?? '';
      renderGame(renderer, width, height, text, currentNode, hoveredChoice, state, time);
      renderPauseOverlay(renderer, width, height);
    } else if (state.phase === 'transition') {
      renderTransition(renderer, width, height, time);
    } else if (state.phase === 'ended') {
      renderEnding(renderer, width, height, state.score, time);
    }
  }, [gameStateSnapshot, currentNode, hoveredChoice]);

  useGameLoop(render, true);

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: '100%',
        height: 'auto',
        aspectRatio: `${CANVAS.minWidth} / ${CANVAS.minHeight}`,
        cursor: gameStateSnapshot.phase === 'playing' ? 'text' : 'pointer',
        borderRadius: '8px',
        border: `1px solid ${COLORS.border}`,
      }}
      onClick={handleClick}
      onMouseMove={handleMouseMove}
      tabIndex={0}
      role="application"
      aria-label="Text Adventure Game Canvas"
    />
  );
};

function renderMenu(
  renderer: CanvasRenderer,
  width: number,
  height: number,
  time: number
): void {
  const centerX = width / 2;
  const centerY = height / 2;

  // Title
  renderer.drawText('TEXT ADVENTURE', centerX, centerY - 100, {
    color: COLORS.accent,
    fontSize: 42,
    align: 'center',
    fontFamily: "'Courier New', monospace",
  });

  // Subtitle
  renderer.drawText('A Journey Through Choice and Consequence', centerX, centerY - 50, {
    color: COLORS.textDim,
    fontSize: 16,
    align: 'center',
  });

  // Start prompt with pulse effect
  const pulse = 0.7 + Math.sin(time * 0.003) * 0.3;
  renderer.drawText('Click or Press ENTER to Begin', centerX, centerY + 50, {
    color: `rgba(0, 255, 136, ${pulse})`,
    fontSize: 20,
    align: 'center',
  });

  // Controls hint
  renderer.drawText('Arrow Keys: Navigate Choices | Enter: Select | P: Pause | 1-9: Quick Select', centerX, height - 60, {
    color: COLORS.textDim,
    fontSize: 12,
    align: 'center',
  });
}

function renderGame(
  renderer: CanvasRenderer,
  width: number,
  height: number,
  text: string,
  currentNode: StoryNode | null,
  hoveredChoice: number | null,
  state: any,
  time: number
): Array<{ x: number; y: number; w: number; h: number }> {
  const padding = CANVAS.padding;
  const textWidth = width - padding * 2;
  const bounds: Array<{ x: number; y: number; w: number; h: number }> = [];

  // HUD
  renderHUD(renderer, width, state);

  // Story text
  const textStartY = CANVAS.hudHeight + padding;
  renderer.drawText(text, padding, textStartY, {
    color: COLORS.text,
    fontSize: 18,
    maxWidth: textWidth,
    lineHeight: CANVAS.textLineHeight,
  });

  // Choices (only if text is complete)
  if (currentNode?.choices.length && text.length >= (currentNode.text?.length ?? 0)) {
    const choicesStartY = textStartY + 200;
    const choiceHeight = CANVAS.choiceHeight;
    const choiceGap = CANVAS.choiceGap;

    currentNode.choices.forEach((choice: Choice, index: number) => {
      const y = choicesStartY + index * (choiceHeight + choiceGap);
      const isHovered = hoveredChoice === index;

      renderer.drawRect(padding, y, textWidth, choiceHeight, {
        fill: isHovered ? COLORS.choiceHover : COLORS.choiceBg,
        stroke: isHovered ? COLORS.accent : COLORS.border,
        strokeWidth: isHovered ? 2 : 1,
        radius: 6,
      });

      const choiceText = `${index + 1}. ${choice.text}`;
      renderer.drawText(choiceText, padding + 15, y + 15, {
        color: isHovered ? COLORS.accent : COLORS.text,
        fontSize: 16,
        maxWidth: textWidth - 30,
      });

      bounds.push({ x: padding, y, w: textWidth, h: choiceHeight });
    });
  }

  return bounds;
}

function renderHUD(
  renderer: CanvasRenderer,
  width: number,
  state: any
): void {
  renderer.drawRect(0, 0, width, CANVAS.hudHeight, {
    fill: COLORS.hudBg,
  });

  // Level
  const level = state.currentLevel + 1;
  const levelName = state.levels?.[state.currentLevel]?.name ?? `Level ${level}`;
  renderer.drawText(`Chapter ${level}: ${levelName}`, 15, 15, {
    color: COLORS.accent,
    fontSize: 14,
  });

  // Score
  const scoreText = `Score: ${state.score}`;
  const scoreWidth = renderer.getContext().measureText(scoreText).width;
  renderer.drawText(scoreText, width - scoreWidth - 15, 15, {
    color: COLORS.accent,
    fontSize: 14,
  });
}

function renderPauseOverlay(
  renderer: CanvasRenderer,
  width: number,
  height: number
): void {
  renderer.drawRect(0, 0, width, height, {
    fill: COLORS.overlayBg,
  });

  const centerX = width / 2;
  const centerY = height / 2;

  renderer.drawText('PAUSED', centerX, centerY - 30, {
    color: COLORS.accent,
    fontSize: 32,
    align: 'center',
  });

  renderer.drawText('Press P or ESC to Resume', centerX, centerY + 20, {
    color: COLORS.textDim,
    fontSize: 16,
    align: 'center',
  });
}

function renderTransition(
  renderer: CanvasRenderer,
  width: number,
  height: number,
  time: number
): void {
  const centerX = width / 2;
  const centerY = height / 2;

  // Fade effect
  const alpha = 0.5 + Math.sin(time * 0.002) * 0.3;
  renderer.drawRect(0, 0, width, height, {
    fill: `rgba(0, 0, 0, ${alpha})`,
  });

  renderer.drawText('Chapter Complete', centerX, centerY - 40, {
    color: COLORS.accent,
    fontSize: 28,
    align: 'center',
  });

  const pulse = 0.7 + Math.sin(time * 0.003) * 0.3;
  renderer.drawText('Click or Press ENTER to Continue', centerX, centerY + 20, {
    color: `rgba(0, 255, 136, ${pulse})`,
    fontSize: 18,
    align: 'center',
  });
}

function renderEnding(
  renderer: CanvasRenderer,
  width: number,
  height: number,
  score: number,
  time: number
): void {
  const centerX = width / 2;
  const centerY = height / 2;
  const padding = CANVAS.padding;
  const textWidth = width - padding * 2;

  renderer.drawText('THE END', centerX, centerY - 100, {
    color: COLORS.accent,
    fontSize: 36,
    align: 'center',
  });

  renderer.drawText(`Final Score: ${score}`, centerX, centerY - 50, {
    color: COLORS.text,
    fontSize: 24,
    align: 'center',
  });

  const pulse = 0.7 + Math.sin(time * 0.003) * 0.3;
  renderer.drawText('Click or Press ENTER to Play Again', centerX, centerY + 20, {
    color: `rgba(0, 255, 136, ${pulse})`,
    fontSize: 18,
    align: 'center',
  });
}
