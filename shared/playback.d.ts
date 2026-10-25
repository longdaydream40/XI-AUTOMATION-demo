import type { PlaybackState } from './index';
export function createPlayback(options: {
  duration: number; render(time: number): void; ready: Promise<unknown>;
  entry?: number; freeze?: number | null; reset?(): void; clickTarget?: HTMLElement | null;
}): { start(from?: number): void; stop(): void; destroy(): void; state: PlaybackState };
