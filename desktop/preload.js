// The only bridge between the web page and the Mac app. The page can bring the window up and
// report whether the microphone is open. It cannot touch the system in any other way.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("memoryLane", {
  desktop: true,
  surface: () => ipcRenderer.send("surface"),
  mic: (open) => ipcRenderer.send("mic", Boolean(open)),
});

// the global shortcut reaches the page as an ordinary DOM event
ipcRenderer.on("talk-toggle", () => window.dispatchEvent(new CustomEvent("ml-talk")));
