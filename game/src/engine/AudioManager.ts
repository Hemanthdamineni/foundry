// Web Audio API wrapper, sound loading, playback control

import { AUDIO } from '../utils/constants';

type SoundType = 'click' | 'hover' | 'discovery' | 'danger' | 'ambient1' | 'ambient2' | 'ambient3';

export class AudioManager {
  private context: AudioContext | null = null;
  private buffers: Map<string, AudioBuffer> = new Map();
  private ambientSource: AudioBufferSourceNode | null = null;
  private gainNode: GainNode | null = null;
  private volume: number = 0.7;
  private muted: boolean = false;
  private initialized: boolean = false;

  async initialize(): Promise<void> {
    if (this.initialized) return;
    
    try {
      this.context = new (window.AudioContext || (window as any).webkitAudioContext)();
      this.gainNode = this.context.createGain();
      this.gainNode.connect(this.context.destination);
      this.gainNode.gain.value = this.volume;
      this.initialized = true;
    } catch (e) {
      console.warn('Web Audio API not supported:', e);
    }
  }

  private async loadSound(url: string): Promise<AudioBuffer | null> {
    if (!this.context) return null;
    
    try {
      const response = await fetch(url);
      if (!response.ok) return null;
      const arrayBuffer = await response.arrayBuffer();
      return await this.context.decodeAudioData(arrayBuffer);
    } catch (e) {
      console.warn(`Failed to load sound ${url}:`, e);
      return null;
    }
  }

  async preloadSounds(): Promise<void> {
    if (!this.context) return;

    const soundUrls: Record<SoundType, string> = AUDIO;
    for (const [key, url] of Object.entries(soundUrls)) {
      const buffer = await this.loadSound(url);
      if (buffer) {
        this.buffers.set(key, buffer);
      }
    }
  }

  playSound(type: SoundType): void {
    if (!this.context || !this.gainNode || this.muted) return;

    const buffer = this.buffers.get(type);
    if (!buffer) return;

    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.gainNode);
    source.start(0);
  }

  playAmbient(type: 'ambient1' | 'ambient2' | 'ambient3'): void {
    if (!this.context || !this.gainNode || this.muted) return;

    this.stopAmbient();

    const buffer = this.buffers.get(type);
    if (!buffer) return;

    this.ambientSource = this.context.createBufferSource();
    this.ambientSource.buffer = buffer;
    this.ambientSource.loop = true;
    this.ambientSource.connect(this.gainNode);
    this.ambientSource.start(0);
  }

  stopAmbient(): void {
    if (this.ambientSource) {
      try {
        this.ambientSource.stop();
      } catch (e) {
        // Already stopped
      }
      this.ambientSource = null;
    }
  }

  setVolume(volume: number): void {
    this.volume = Math.max(0, Math.min(1, volume));
    if (this.gainNode) {
      this.gainNode.gain.value = this.muted ? 0 : this.volume;
    }
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    if (this.gainNode) {
      this.gainNode.gain.value = muted ? 0 : this.volume;
    }
  }

  getIsInitialized(): boolean {
    return this.initialized;
  }

  getContext(): AudioContext | null {
    return this.context;
  }
}
