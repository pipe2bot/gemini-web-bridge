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
      handleGenerate(data.id, data.prompt, data.new_chat, data.image_data, data.include_thoughts, data.thinking, data.model);
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

  async function setGeminiModel(modelName = 'gemini-web', enableThinking = undefined) {
    const normalizedModel = String(modelName).toLowerCase();
    let targetBase = 'flash'; // Always 3.8 Flash, never Flash-Lite
    if (normalizedModel.includes('pro')) {
      targetBase = 'pro';
    } else if (normalizedModel.includes('lite')) {
      targetBase = 'flash-lite';
    }

    let targetThinking = false;
    if (typeof enableThinking === 'boolean') {
      targetThinking = enableThinking;
    } else if (normalizedModel.includes('thinking')) {
      targetThinking = true;
    }

    const getPickerBtn = () => {
      return document.querySelector('[data-test-id="bard-mode-menu-button"]') ||
             Array.from(document.querySelectorAll('button')).find((b) => {
               const label = (b.getAttribute('aria-label') || b.textContent || '').toLowerCase();
               return label.includes('mode picker') || (label.includes('currently') && (label.includes('flash') || label.includes('pro')));
             });
    };

    const pickerBtn = getPickerBtn();
    if (!pickerBtn) return false;

    const parseCurrent = () => {
      const label = (pickerBtn.getAttribute('aria-label') || pickerBtn.textContent || '').toLowerCase();
      const thinking = label.includes('extended');
      let base = 'unknown';
      if (label.includes('flash-lite') || label.includes('flash lite')) {
        base = 'flash-lite';
      } else if (label.includes('flash')) {
        base = 'flash';
      } else if (label.includes('pro')) {
        base = 'pro';
      }
      return { base, thinking };
    };

    let current = parseCurrent();
    if (current.base === targetBase && current.thinking === targetThinking) {
      return true;
    }

    const openMenu = async () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await new Promise(r => setTimeout(r, 150));
      if (!document.querySelector('gem-menu-item')) {
        pickerBtn.click();
        for (let i = 0; i < 20; i++) {
          if (document.querySelector('gem-menu-item')) break;
          await new Promise(r => setTimeout(r, 50));
        }
      }
    };

    const dismissMenu = async () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await new Promise(r => setTimeout(r, 150));
    };

    // 1. If base model differs, open menu and select base model
    if (current.base !== targetBase) {
      await openMenu();
      const items = Array.from(document.querySelectorAll('gem-menu-item, [role="menuitem"]'));
      let row = null;
      if (targetBase === 'flash') {
        row = items.find(el => {
          const txt = (el.textContent || '').toLowerCase();
          return (txt.includes('3.8 flash') || txt.includes('all-around help')) ||
                 (txt.includes('flash') && !txt.includes('lite'));
        });
      } else if (targetBase === 'pro') {
        row = items.find(el => (el.textContent || '').toLowerCase().includes('pro'));
      } else if (targetBase === 'flash-lite') {
        row = items.find(el => (el.textContent || '').toLowerCase().includes('lite'));
      }
      if (row) {
        row.click();
        await new Promise(r => setTimeout(r, 350));
      }
      await dismissMenu();
      current = parseCurrent();
    }

    // 2. If thinking mode differs, open menu and toggle Extended thinking
    if (current.thinking !== targetThinking) {
      await openMenu();
      const items = Array.from(document.querySelectorAll('gem-menu-item, [role="menuitem"]'));
      const thinkingRow = items.find(el => (el.textContent || '').toLowerCase().includes('extended thinking'));
      if (thinkingRow) {
        thinkingRow.click();
        await new Promise(r => setTimeout(r, 350));
      }
      await dismissMenu();
    }

    current = parseCurrent();
    return current.base === targetBase && current.thinking === targetThinking;
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

  async function uploadAttachment(base64DataUrl) {
    const response = await fetch(base64DataUrl);
    const blob = await response.blob();
    const mimeType = blob.type || 'application/octet-stream';
    const isImage = mimeType.startsWith('image/');
    const inputSelector = isImage
      ? 'input[type="file"][accept*="image"]'
      : 'input[type="file"]:not([accept*="image"]), input[type="file"]';

    let fileInput = document.querySelector(inputSelector);

    if (!fileInput) {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await new Promise((r) => setTimeout(r, 200));

      const ta = document.querySelector('rich-textarea');
      const container = ta ? (ta.closest('.input-area') || ta.closest('form') || ta.parentElement.parentElement) : document;
      const uploadBtn = (container && container.querySelector('button[aria-label*="Upload & tools"]')) ||
                        (container && container.querySelector('button[aria-label*="Upload"]')) ||
                        Array.from(document.querySelectorAll('button')).find(b =>
                          /upload & tools/i.test(b.getAttribute('aria-label') || '')
                        );

      if (!uploadBtn) {
        throw new Error('Upload button not found in Gemini Web UI.');
      }
      uploadBtn.click();

      const menuStart = Date.now();
      while (!fileInput && Date.now() - menuStart < 3000) {
        await new Promise((r) => setTimeout(r, 100));
        fileInput = document.querySelector(inputSelector);
      }

      if (!fileInput) {
        fileInput = document.querySelector('input[type="file"]');
      }
      if (!fileInput) {
        throw new Error('File input failed to appear after opening upload menu.');
      }
    }

    // Dismiss any open CDK overlay menu
    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Escape',
        code: 'Escape',
        bubbles: true,
        cancelable: true,
      })
    );
    await new Promise((r) => setTimeout(r, 200));

    const extension = mimeType.includes('/') ? mimeType.split('/')[1].split('+')[0] : 'bin';
    const file = new File([blob], `attachment_${Date.now()}.${extension}`, {
      type: mimeType,
    });

    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;

    fileInput.dispatchEvent(new Event('input', { bubbles: true }));
    fileInput.dispatchEvent(new Event('change', { bubbles: true }));

    await new Promise((resolve, reject) => {
      const timeout = 30000;
      const startTime = Date.now();

      const checkInterval = setInterval(() => {
        const isLoading = document.querySelector('.gem-attachment-loading-container, .gem-attachment-content.loading');
        const isComplete = document.querySelector('img.gem-attachment-style-img, .gem-attachment-content, [class*="attachment"]');

        if (!isLoading && isComplete) {
          clearInterval(checkInterval);
          resolve();
        } else if (Date.now() - startTime > timeout) {
          clearInterval(checkInterval);
          if (isComplete) {
            resolve();
          } else {
            reject(new Error('File upload timed out or failed to attach.'));
          }
        }
      }, 100);
    });
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

  async function handleGenerate(requestId, promptText, shouldStartNewChat, imageDataUrl, includeThoughts, thinkingParam, modelParam) {
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

      // Enforce target model and thinking mode
      await setGeminiModel(modelParam || 'gemini-web', thinkingParam);

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

      if (promptText === "__DUMP_INPUTS__") {
        const inputs = Array.from(document.querySelectorAll('input')).map(i => ({
          tag: i.tagName,
          type: i.type,
          name: i.name,
          id: i.id,
          classes: i.className,
          accept: i.accept
        }));
        setBadgeState("idle");
        isProcessing = false;
        api.runtime.sendMessage({
          type: "complete",
          id: requestId,
          text: JSON.stringify(inputs, null, 2)
        });
        return;
      }

      if (promptText && promptText.startsWith("__EVAL__:")) {
        (async () => {
          let result = "";
          try {
            const raw = eval(promptText.slice(9));
            const val = raw instanceof Promise ? await raw : raw;
            result = JSON.stringify(val);
          } catch (e) {
            result = "Error: " + e.message;
          }
          setBadgeState("idle");
          isProcessing = false;
          api.runtime.sendMessage({
            type: "complete",
            id: requestId,
            text: String(result)
          });
        })();
        return;
      }

      if (imageDataUrl) {
        console.log("[Gemini Bridge] Uploading attachment payload...");
        const urls = Array.isArray(imageDataUrl) ? imageDataUrl : [imageDataUrl];
        for (const url of urls) {
          await uploadAttachment(url);
        }
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
