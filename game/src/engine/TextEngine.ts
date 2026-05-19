// Typewriter text animation on Canvas

export class TextEngine {
  private fullText: string;
  private visibleChars: number;
  private charsPerSecond: number;
  private lastUpdateTime: number;
  private isComplete: boolean;

  constructor(text: string, charsPerSecond: number = 30) {
    this.fullText = text;
    this.visibleChars = 0;
    this.charsPerSecond = charsPerSecond;
    this.lastUpdateTime = performance.now();
    this.isComplete = false;
  }

  update(currentTime: number): void {
    if (this.isComplete) return;

    const elapsed = currentTime - this.lastUpdateTime;
    const charsToAdd = (this.charsPerSecond * elapsed) / 1000;
    this.visibleChars = Math.min(
      this.visibleChars + charsToAdd,
      this.fullText.length
    );
    this.lastUpdateTime = currentTime;

    if (this.visibleChars >= this.fullText.length) {
      this.isComplete = true;
    }
  }

  getVisibleText(): string {
    return this.fullText.substring(0, Math.floor(this.visibleChars));
  }

  skip(): void {
    this.visibleChars = this.fullText.length;
    this.isComplete = true;
  }

  getIsComplete(): boolean {
    return this.isComplete;
  }

  reset(text?: string, charsPerSecond?: number): void {
    this.fullText = text ?? this.fullText;
    this.charsPerSecond = charsPerSecond ?? this.charsPerSecond;
    this.visibleChars = 0;
    this.lastUpdateTime = performance.now();
    this.isComplete = false;
  }

  getProgress(): number {
    return this.visibleChars / this.fullText.length;
  }
}
