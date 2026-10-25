export interface PlaybackState {
  ready: boolean; playing: boolean; time: number; duration: number;
  renders: number; ended: boolean; error: string;
}
declare global { interface Window { __xiPlayback?: PlaybackState } }
