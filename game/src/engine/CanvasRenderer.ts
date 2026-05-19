// Core Canvas drawing utilities and context management

import { CanvasDimensions, COLORS } from '../types/game';

export class CanvasRenderer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private dimensions: CanvasDimensions;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    const dpr = window.devicePixelRatio || 1;
    this.dimensions = {
      width: canvas.clientWidth,
      height: canvas.clientHeight,
      dpr,
    };
    canvas.width = this.dimensions.width * dpr;
    canvas.height = this.dimensions.height * dpr;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Failed to get Canvas context');
    this.ctx = ctx;
    this.ctx.scale(dpr, dpr);
  }

  getContext(): CanvasRenderingContext2D {
    return this.ctx;
  }

  getDimensions(): CanvasDimensions {
    return this.dimensions;
  }

  clear(): void {
    const { width, height, dpr } = this.dimensions;
    this.ctx.clearRect(0, 0, width, height);
  }

  fillBackground(color: string = COLORS.background): void {
    const { width, height } = this.dimensions;
    this.ctx.fillStyle = color;
    this.ctx.fillRect(0, 0, width, height);
  }

  drawText(
    text: string,
    x: number,
    y: number,
    options: {
      color?: string;
      fontSize?: number;
      fontFamily?: string;
      maxWidth?: number;
      lineHeight?: number;
      align?: CanvasTextAlign;
    } = {}
  ): void {
    const {
      color = COLORS.text,
      fontSize = 18,
      fontFamily = "'Courier New', monospace",
      maxWidth,
      lineHeight = 28,
      align = 'left',
    } = options;

    this.ctx.fillStyle = color;
    this.ctx.font = `${fontSize}px ${fontFamily}`;
    this.ctx.textAlign = align;
    this.ctx.textBaseline = 'top';

    if (maxWidth && this.ctx.measureText(text).width > maxWidth) {
      // Word wrap
      const words = text.split(' ');
      let line = '';
      let currentY = y;

      for (const word of words) {
        const testLine = line + word + ' ';
        if (this.ctx.measureText(testLine).width > maxWidth && line !== '') {
          this.ctx.fillText(line.trim(), x, currentY);
          line = word + ' ';
          currentY += lineHeight;
        } else {
          line = testLine;
        }
      }
      this.ctx.fillText(line.trim(), x, currentY);
    } else {
      this.ctx.fillText(text, x, y);
    }
  }

  drawRect(
    x: number,
    y: number,
    width: number,
    height: number,
    options: {
      fill?: string;
      stroke?: string;
      strokeWidth?: number;
      radius?: number;
    } = {}
  ): void {
    const { fill, stroke, strokeWidth = 1, radius = 0 } = options;

    this.ctx.beginPath();
    if (radius > 0) {
      this.roundRect(x, y, width, height, radius);
    } else {
      this.ctx.rect(x, y, width, height);
    }

    if (fill) {
      this.ctx.fillStyle = fill;
      this.ctx.fill();
    }
    if (stroke) {
      this.ctx.strokeStyle = stroke;
      this.ctx.lineWidth = strokeWidth;
      this.ctx.stroke();
    }
  }

  private roundRect(
    x: number,
    y: number,
    width: number,
    height: number,
    radius: number
  ): void {
    this.ctx.moveTo(x + radius, y);
    this.ctx.lineTo(x + width - radius, y);
    this.ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    this.ctx.lineTo(x + width, y + height - radius);
    this.ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    this.ctx.lineTo(x + radius, y + height);
    this.ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    this.ctx.lineTo(x, y + radius);
    this.ctx.quadraticCurveTo(x, y, x + radius, y);
    this.ctx.closePath();
  }

  drawParticles(
    count: number,
    color: string,
    time: number
  ): void {
    const { width, height } = this.dimensions;
    this.ctx.fillStyle = color;
    
    for (let i = 0; i < count; i++) {
      const x = ((i * 137.5 + time * 0.02) % width);
      const y = ((i * 89.3 + time * 0.01) % height);
      const size = 1 + Math.sin(i + time * 0.001) * 0.5;
      this.ctx.globalAlpha = 0.3 + Math.sin(i * 2 + time * 0.002) * 0.2;
      this.ctx.beginPath();
      this.ctx.arc(x, y, size, 0, Math.PI * 2);
      this.ctx.fill();
    }
    this.ctx.globalAlpha = 1;
  }

  resize(width: number, height: number): void {
    const dpr = window.devicePixelRatio || 1;
    this.dimensions = { width, height, dpr };
    this.canvas.width = width * dpr;
    this.canvas.height = height * dpr;
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.scale(dpr, dpr);
  }
}
