import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConversationProvider } from "@elevenlabs/react";
import "./index.css";
import App from "./App";

// Installed on a Mac it opens as its own window. Start it small, like a widget that lives on the screen.
try {
  if (window.matchMedia("(display-mode: standalone)").matches && window.location.pathname === "/app") {
    window.resizeTo(380, 580);
  }
} catch {
  /* a normal browser tab ignores this */
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConversationProvider>
      <App />
    </ConversationProvider>
  </StrictMode>,
);
