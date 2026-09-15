(function () {
  const api = typeof browser !== "undefined" ? browser : chrome;
  console.log("[Gemini Bridge] Content script loaded on Gemini page.");

  function injectBadge() {
    if (document.getElementById("gemini-bridge-status")) return;
    const badge = document.createElement("div");
    badge.id = "gemini-bridge-status";
    badge.style.cssText = "position: fixed; top: 12px; left: 50%; transform: translateX(-50%); z-index: 999999; padding: 6px 14px; background: #10a37f; color: white; font-family: system-ui, -apple-system, sans-serif; font-size: 13px; font-weight: 600; border-radius: 18px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); transition: all 0.3s ease;";
    badge.innerText = "⚡ Gemini Bridge: Active";
    document.body.appendChild(badge);
  }

  function setBadgeState(state, text) {
    const badge = document.getElementById("gemini-bridge-status");
    if (!badge) return;
    if (state === "processing") {
      badge.style.background = "#e37400";
      badge.innerText = "⏳ Gemini Bridge: Processing...";
    } else if (state === "error") {
      badge.style.background = "#d93025";
      badge.innerText = `❌ Gemini Bridge: ${text || "Error"}`;
    } else {
      badge.style.background = "#10a37f";
      badge.innerText = "⚡ Gemini Bridge: Active";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectBadge);
  } else {
    injectBadge();
  }

  let isProcessing = false;

  api.runtime.onMessage.addListener((data) => {
    if (data.command === "generate") {
      isProcessing = false;
      handleGenerate(data.id, data.prompt, data.new_chat, data.image_data, data.include_thoughts, data.thinking);
    }
  });

  function getInputElement() {
    return document.querySelector('rich-textarea div[contenteditable="true"]') ||
           document.querySelector('div[contenteditable="true"]') ||
           document.querySelector('textarea');
  }

  function getSendButton() {
    return document.querySelector('button.send-button') ||
           document.querySelector('button[aria-label*="Send"]') ||
           document.querySelector('button[aria-label*="ส่ง"]') ||
           document.querySelector('.send-button-container button');
  }

  function getNewChatButton() {
    return document.querySelector('a[aria-label*="New chat"]') ||
           document.querySelector('button[aria-label*="New chat"]') ||
           document.querySelector('div[aria-label*="New chat"]') ||
           document.querySelector('a[href="/app"]') ||
           document.querySelector('.new-chat-button');
  }

  async function toggleThinkingMode(enable) {
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    const pickerBtn = Array.from(document.querySelectorAll('button')).find((btn) => {
      const label = btn.getAttribute('aria-label') || '';
      return /mode picker/i.test(label);
    });

    if (!pickerBtn) {
      console.warn('[Gemini Bridge] Mode picker button not found.');
      return false;
    }

    const btnContent = `${pickerBtn.getAttribute('aria-label') || ''} ${pickerBtn.textContent || ''}`;
    const isCurrentlyExtended = /extended|thinking/i.test(btnContent);

    if (enable === isCurrentlyExtended) {
      return true;
    }

    pickerBtn.click();
    await sleep(350);

    const dismissMenu = async () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await sleep(250);
    };

    const menuContainer = document.querySelector('.cdk-overlay-container, [role="menu"]');
    const items = menuContainer
      ? Array.from(menuContainer.querySelectorAll('[role="menuitem"], .mat-mdc-menu-item, button'))
      : [];

    let targetItem = null;
    if (enable) {
      targetItem = items.find((el) => {
        const text = `${el.getAttribute('aria-label') || ''} ${el.textContent || ''}`;
        return /extended|thinking/i.test(text);
      });
    } else {
      targetItem = items.find((el) => {
        const text = `${el.getAttribute('aria-label') || ''} ${el.textContent || ''}`;
        return /flash/i.test(text) && !/extended|thinking/i.test(text);
      });
    }

    if (targetItem) {
      targetItem.click();
      await sleep(350);
      if (document.querySelector('.cdk-overlay-container [role="menu"]')) {
        await dismissMenu();
      }
      return true;
    }

    console.warn(`[Gemini Bridge] Failed to find menu option for enable=${enable}`);
    await dismissMenu();
    return false;
  }

  function getResponseContent(element, includeThoughts) {
    if (!element) return { text: "" };
    const clone = element.cloneNode(true);
    const thoughtEls = clone.querySelectorAll('thought-container, .thought-process, .thinking-container, details.thought-details, .thought-header, .thinking-content, details');
    
    let thoughtsText = "";
    thoughtEls.forEach(el => {
      thoughtsText += (el.innerText || el.textContent || "") + "\n";
      el.remove();
    });

    const cleanText = (clone.innerText || clone.textContent || "").trim();

    if (includeThoughts && thoughtsText.trim()) {
      return {
        text: `> Thinking Process:\n${thoughtsText.trim()}\n\n${cleanText || element.innerText.trim()}`
      };
    }
    return { text: cleanText || element.innerText.trim() };
  }

  async function uploadImage(base64DataUrl) {
    const fileInput = document.querySelector('input[type="file"]');
    if (!fileInput) return false;

    try {
      const res = await fetch(base64DataUrl);
      const blob = await res.blob();
      const file = new File([blob], "image.png", { type: blob.type || "image/png" });

      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      fileInput.dispatchEvent(new Event("input", { bubbles: true }));

      await new Promise(r => setTimeout(r, 1200));
      return true;
    } catch (e) {
      console.error("[Gemini Bridge] Image upload error:", e);
      return false;
    }
  }

  function setNativeValue(element, value) {
    element.focus();
    document.execCommand('insertText', false, value);
    if (!element.textContent.trim()) {
      element.innerText = value;
    }
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function getLatestResponseElement() {
    const list = document.querySelectorAll('message-content, .model-response-text, .response-container-content, model-response');
    return list.length > 0 ? list[list.length - 1] : null;
  }

  async function handleGenerate(requestId, promptText, shouldStartNewChat, imageDataUrl, includeThoughts, thinkingParam) {
    isProcessing = true;
    setBadgeState("processing");
    try {
      if (shouldStartNewChat) {
        const newChatBtn = getNewChatButton();
        if (newChatBtn) {
          console.log("[Gemini Bridge] Resetting chat session...");
          newChatBtn.click();
          await new Promise(r => setTimeout(r, 1000));
        }
      }

      // Check and toggle thinking mode if specified
      if (thinkingParam !== undefined) {
        await toggleThinkingMode(thinkingParam);
      }

      if (promptText === "__DUMP_BUTTONS__") {
        const btns = Array.from(document.querySelectorAll('button, [role="button"], [role="switch"], [role="menuitem"], a')).map(b => ({
          tag: b.tagName,
          label: b.getAttribute('aria-label'),
          text: (b.innerText || b.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60),
          classes: (b.className || '').toString().slice(0, 60),
          role: b.getAttribute('role'),
          href: b.getAttribute('href')
        })).filter(b => b.label || b.text);
        setBadgeState("idle");
        isProcessing = false;
        api.runtime.sendMessage({
          type: "complete",
          id: requestId,
          text: JSON.stringify(btns, null, 2)
        });
        return;
      }

      if (imageDataUrl) {
        console.log("[Gemini Bridge] Uploading image payload...");
        await uploadImage(imageDataUrl);
      }

      const inputEl = getInputElement();
      if (!inputEl) {
        throw new Error("Input text element not found on Gemini web page.");
      }

      // Clear existing input
      inputEl.focus();
      document.execCommand('selectAll', false, null);
      document.execCommand('delete', false, null);

      // Insert new prompt
      setNativeValue(inputEl, promptText);

      await new Promise(r => setTimeout(r, 300));

      const sendBtn = getSendButton();
      if (!sendBtn || sendBtn.disabled || sendBtn.getAttribute('aria-disabled') === 'true') {
        throw new Error("Send button not found or disabled.");
      }

      const initialEl = getLatestResponseElement();
      const initialText = initialEl ? (getResponseContent(initialEl, includeThoughts).text || "") : "";
      let generationStarted = false;

      sendBtn.click();

      // Poll response text & monitor generation completion status
      let lastText = "";
      let stableCount = 0;

      await new Promise((resolve) => {
        const timer = setInterval(() => {
          const targetResponseEl = getLatestResponseElement();
          const parsed = getResponseContent(targetResponseEl, includeThoughts);
          const currentText = parsed.text;

          const isGenerating = document.querySelector('button[aria-label*="Stop"]') !== null ||
                               document.querySelector('button[aria-label*="หยุด"]') !== null;

          if (isGenerating || targetResponseEl !== initialEl || (currentText && currentText !== initialText)) {
            generationStarted = true;
          }

          if (currentText !== lastText) {
            lastText = currentText;
            stableCount = 0;
            if (currentText && generationStarted) {
              api.runtime.sendMessage({
                type: "chunk",
                id: requestId,
                text: currentText
              });
            }
          } else if (currentText.length > 0 && generationStarted) {
            stableCount++;
          }

          if (generationStarted && !isGenerating && currentText.length > 0 && stableCount >= 2) {
            clearInterval(timer);
            resolve();
          }
        }, 300);

        setTimeout(() => {
          clearInterval(timer);
          resolve();
        }, 120000);
      });

      const finalEl = getLatestResponseElement();
      const parsedFinal = getResponseContent(finalEl, includeThoughts);
      const finalContent = parsedFinal.text || lastText;
      console.log(`[Gemini Bridge] Generation complete (${finalContent.length} chars). Sending to background...`);

      api.runtime.sendMessage({
        type: "complete",
        id: requestId,
        text: finalContent
      });

      setBadgeState("active");

    } catch (err) {
      console.error("[Gemini Bridge] Prompt generation error:", err);
      setBadgeState("error", err.message);
      api.runtime.sendMessage({
        type: "error",
        id: requestId,
        error: err.message
      });
    } finally {
      isProcessing = false;
    }
  }
})();
