import React, { useEffect, useState } from 'react';
import { GameStateManager } from './engine/GameStateManager';
import { AudioManager } from './engine/AudioManager';
import { GameCanvas } from './components/GameCanvas';
import { storyData } from './data/storyData';
import { saveGame, loadGame, hasSave } from './utils/storage';

const App: React.FC = () => {
  const [gameState] = useState(() => new GameStateManager(storyData));
  const [audioManager] = useState(() => new AudioManager());
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Load saved game if exists
  useEffect(() => {
    const saved = loadGame();
    if (saved && saved.phase && saved.phase !== 'menu') {
      gameState.loadState(saved);
    }
  }, [gameState]);

  // Auto-save on state changes
  useEffect(() => {
    const unsubscribe = gameState.subscribe((state) => {
      if (state.phase !== 'menu' && state.phase !== 'loading') {
        saveGame({
          phase: state.phase,
          currentLevel: state.currentLevel,
          currentNode: state.currentNode,
          score: state.score,
          history: state.history,
          settings: state.settings,
        });
      }
    });

    return unsubscribe;
  }, [gameState]);

  const handleChoice = (index: number) => {
    const result = gameState.makeChoice(index);
    
    if (result.levelComplete) {
      // Will transition to next level
    }
  };

  const handleNextLevel = () => {
    gameState.nextLevel();
  };

  const handleTogglePause = () => {
    const state = gameState.getState();
    if (state.phase === 'paused') {
      gameState.resume();
    } else {
      gameState.pause();
    }
  };

  const handleToggleSettings = () => {
    setIsSettingsOpen(prev => !prev);
  };

  return (
    <div style={{ 
      width: '100%', 
      maxWidth: 1000, 
      margin: '0 auto',
      padding: '20px',
    }}>
      <GameCanvas
        gameState={gameState}
        audioManager={audioManager}
        onChoice={handleChoice}
        onNextLevel={handleNextLevel}
        onTogglePause={handleTogglePause}
        onToggleSettings={handleToggleSettings}
      />
      
      {isSettingsOpen && (
        <SettingsPanel
          gameState={gameState}
          onClose={() => setIsSettingsOpen(false)}
        />
      )}
    </div>
  );
};

interface SettingsPanelProps {
  gameState: GameStateManager;
  onClose: () => void;
}

const SettingsPanel: React.FC<SettingsPanelProps> = ({ gameState, onClose }) => {
  const state = gameState.getState();
  const { settings } = state;

  const updateSetting = <K extends keyof typeof settings>(key: K, value: (typeof settings)[K]) => {
    gameState.updateSettings({ [key]: value });
    
    if (key === 'volume') {
      // Volume update handled by audio manager
    }
    if (key === 'muted') {
      // Mute update handled by audio manager
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: '50%',
      left: '50%',
      transform: 'translate(-50%, -50%)',
      background: '#1a1a2e',
      border: '1px solid #333344',
      borderRadius: '8px',
      padding: '30px',
      minWidth: '300px',
      zIndex: 1000,
      color: '#e0e0e0',
      fontFamily: "'Courier New', monospace",
    }}>
      <h2 style={{ color: '#00ff88', marginBottom: '20px', fontSize: '20px' }}>Settings</h2>
      
      <div style={{ marginBottom: '15px' }}>
        <label style={{ display: 'block', marginBottom: '5px', color: '#888888' }}>
          Text Speed: {settings.textSpeed} chars/sec
        </label>
        <input
          type="range"
          min="10"
          max="80"
          value={settings.textSpeed}
          onChange={(e) => updateSetting('textSpeed', parseInt(e.target.value, 10))}
          style={{ width: '100%' }}
        />
      </div>

      <div style={{ marginBottom: '15px' }}>
        <label style={{ display: 'block', marginBottom: '5px', color: '#888888' }}>
          Volume: {Math.round(settings.volume * 100)}%
        </label>
        <input
          type="range"
          min="0"
          max="100"
          value={settings.volume * 100}
          onChange={(e) => updateSetting('volume', parseInt(e.target.value, 10) / 100)}
          style={{ width: '100%' }}
        />
      </div>

      <div style={{ marginBottom: '20px' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={settings.muted}
            onChange={(e) => updateSetting('muted', e.target.checked)}
          />
          <span style={{ color: '#888888' }}>Mute All Sounds</span>
        </label>
      </div>

      <button
        onClick={onClose}
        style={{
          background: '#00ff88',
          color: '#0a0a0f',
          border: 'none',
          padding: '10px 20px',
          borderRadius: '4px',
          cursor: 'pointer',
          fontFamily: "'Courier New', monospace",
          fontSize: '14px',
          fontWeight: 'bold',
        }}
      >
        Close
      </button>
    </div>
  );
};

export default App;
