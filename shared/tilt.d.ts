export function attachTilt(plane: HTMLElement, options?: { disabled?: boolean }): {
  reset(): void; setDisabled(value: boolean): void; destroy(): void;
};
