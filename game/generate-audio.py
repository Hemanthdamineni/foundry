#!/usr/bin/env python3
"""Generate placeholder audio files as simple WAV tones."""
import wave
import struct
import math
import os

def generate_tone(filename, frequency, duration, sample_rate=44100, amplitude=0.3):
    """Generate a simple sine wave tone."""
    num_samples = int(sample_rate * duration)
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes per sample
        wav_file.setframerate(sample_rate)
        
        for i in range(num_samples):
            # Generate sine wave with fade in/out
            t = i / sample_rate
            fade = min(1, t * 10) * min(1, (duration - t) * 10)
            sample = amplitude * fade * math.sin(2 * math.pi * frequency * t)
            # Convert to 16-bit integer
            packed = struct.pack('h', int(sample * 32767))
            wav_file.writeframes(packed)

# Audio directory
audio_dir = '/home/zorro-omarchy/Desktop/Coding-Things/System/Tools/Servers/Ai-Agent-Server/game/public/assets/audio'

# Generate placeholder sounds
sounds = {
    'click.mp3': (800, 0.1),      # Short high click
    'hover.mp3': (600, 0.05),     # Very short soft hover
    'event-discovery.mp3': (523, 0.5),  # C5 - pleasant discovery
    'event-danger.mp3': (200, 0.6),     # Low danger sound
    'ambient-level1.mp3': (220, 3.0),   # A3 - mysterious ambient
    'ambient-level2.mp3': (262, 3.0),   # C4 - tense ambient
    'ambient-level3.mp3': (330, 3.0),   # E4 - epic ambient
}

for filename, (freq, duration) in sounds.items():
    filepath = os.path.join(audio_dir, filename.replace('.mp3', '.wav'))
    generate_tone(filepath, freq, duration)
    print(f"Generated {filepath}")

print("All placeholder audio files generated!")
