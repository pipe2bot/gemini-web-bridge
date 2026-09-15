const api = typeof browser !== "undefined" ? browser : chrome;

console.log("[Gemini Bridge] Background script loaded.");

let socket = null;

function connect() {
  const wsUrl = "ws://127.0.0.1:8765";
  console.log(`[Gemini Bridge BG] Connecting to ${wsUrl}...`);

  try {
    socket = new WebSocket(wsUrl);
  } catch (err) {
    console.error("[Gemini Bridge BG] Failed to construct WebSocket:", err);
    setTimeout(connect, 3000);
    return;
  }

  socket.onopen = () => {
    console.log("[Gemini Bridge BG] SUCCESS: Connected to local WebSocket server!");
    socket.send(JSON.stringify({ role: "extension", type: "register" }));
  };

  socket.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data);
      console.log("[Gemini Bridge BG] Received command from server:", data);

      if (data.command === "generate") {
        let tabs = await api.tabs.query({ url: "*://gemini.google.com/*" });
        
        // Auto-open Gemini tab if not present!
        if (!tabs || tabs.length === 0) {
          console.log("[Gemini Bridge BG] No Gemini tab open. Auto-launching https://gemini.google.com/app...");
          const newTab = await api.tabs.create({ url: "https://gemini.google.com/app", active: true });
          
          await new Promise((resolve) => {
            function listener(tabId, changeInfo) {
              if (tabId === newTab.id && changeInfo.status === "complete") {
                api.tabs.onUpdated.removeListener(listener);
                setTimeout(resolve, 3500); // Wait for content script to mount
              }
            }
            api.tabs.onUpdated.addListener(listener);
          });
          tabs = [newTab];
        }

        // Target the active or matching tab with valid content script
        let targetTab = tabs.find(t => t.active && t.lastFocusedWindow) || tabs.find(t => t.active) || tabs[0];
        console.log(`[Gemini Bridge BG] Forwarding prompt to tab ID ${targetTab.id} (${targetTab.url})`);

        const orderedTabs = targetTab ? [targetTab, ...tabs.filter(t => t.id !== targetTab.id)] : tabs;
        let sent = false;
        for (const tab of orderedTabs) {
          try {
            await api.tabs.sendMessage(tab.id, data);
            sent = true;
            break;
          } catch (e) {
            console.warn(`[Gemini Bridge BG] Failed on tab ${tab.id}:`, e.message);
          }
        }
        if (!sent) {
          socket.send(JSON.stringify({
            type: "error",
            id: data.id,
            error: "Content script sendMessage failed: No tab accepted connection. Refresh Gemini tab."
          }));
        }
      }
    } catch (err) {
      console.error("[Gemini Bridge BG] Error handling message:", err);
    }
  };

  socket.onclose = (ev) => {
    console.warn(`[Gemini Bridge BG] WebSocket closed (code: ${ev.code}). Reconnecting in 3s...`);
    setTimeout(connect, 3000);
  };

  socket.onerror = (err) => {
    console.error("[Gemini Bridge BG] WebSocket error:", err);
  };
}

api.runtime.onMessage.addListener((message, sender) => {
  console.log("[Gemini Bridge BG] Received message from content script:", message);
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(message));
  } else {
    console.warn("[Gemini Bridge BG] Cannot forward message: WebSocket is not connected.");
  }
});

connect();
