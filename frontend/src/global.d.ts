// Present only inside the Mac app (desktop/preload.js). In a normal browser tab it is undefined.
interface Window {
  memoryLane?: {
    desktop: boolean;
    surface: () => void;
    mic: (open: boolean) => void;
  };
}
