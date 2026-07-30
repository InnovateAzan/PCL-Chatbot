(function () {
  function getEmbedUrl(rawValue) {
    try {
      const url = new URL(rawValue, window.location.href);
      if (!url.searchParams.has("embed")) {
        url.searchParams.set("embed", "1");
      }
      return url.toString();
    } catch (error) {
      return rawValue;
    }
  }

  function mountWidget() {
    const script = document.currentScript;
    const rawEmbedUrl =
      script?.dataset.embedUrl || window.PCL_GPT_EMBED_URL || "";

    if (!rawEmbedUrl) {
      console.error(
        "OneDesk Assistant loader requires data-embed-url or window.PCL_GPT_EMBED_URL."
      );
      return;
    }

    const width = Number(script?.dataset.width || 460);
    const height = Number(script?.dataset.height || 720);
    const zIndex = Number(script?.dataset.zIndex || 2147483000);
    const defaultOpen = script?.dataset.open === "true";
    const embedUrl = getEmbedUrl(rawEmbedUrl);

    const style = document.createElement("style");
    style.textContent = `
      .pcl-gpt-host {
        position: fixed;
        right: 24px;
        bottom: 24px;
        z-index: ${zIndex};
        font-family: Aptos, "Segoe UI", sans-serif;
      }

      .pcl-gpt-launcher {
        display: inline-flex;
        align-items: center;
        gap: 12px;
        min-width: 152px;
        height: 48px;
        padding: 0 20px;
        border: none;
        border-radius: 999px;
        background: #ffffff;
        color: #0b8a3e;
        box-shadow: 0 18px 40px rgba(18, 71, 41, 0.2);
        font-size: 1rem;
        font-weight: 700;
        cursor: pointer;
      }

      .pcl-gpt-launcher-dot {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: #0b8a3e;
        box-shadow: 0 0 0 5px rgba(11, 138, 62, 0.12);
      }

      .pcl-gpt-panel {
        position: absolute;
        right: 0;
        bottom: 62px;
        width: min(${width}px, calc(100vw - 20px));
        height: min(${height}px, calc(100vh - 96px));
        border-radius: 28px;
        overflow: hidden;
        box-shadow: 0 26px 56px rgba(18, 71, 41, 0.22);
        background: transparent;
        opacity: 1;
        transform: translateY(0);
        transform-origin: bottom right;
        transition: opacity 180ms ease, transform 180ms ease;
      }

      .pcl-gpt-panel.hidden {
        opacity: 0;
        transform: translateY(14px) scale(0.97);
        pointer-events: none;
      }

      .pcl-gpt-frame {
        width: 100%;
        height: 100%;
        border: none;
        background: transparent;
      }

      @media (max-width: 700px) {
        .pcl-gpt-host {
          right: 10px;
          bottom: 10px;
        }

        .pcl-gpt-panel {
          bottom: 58px;
          width: min(${width}px, calc(100vw - 10px));
          height: min(${height}px, calc(100vh - 76px));
        }
      }
    `;

    const host = document.createElement("div");
    host.className = "pcl-gpt-host";

    const launcher = document.createElement("button");
    launcher.type = "button";
    launcher.className = "pcl-gpt-launcher";
    launcher.setAttribute("aria-expanded", String(defaultOpen));
    launcher.innerHTML = `
      <span>OneDesk Assistant</span>
      <span class="pcl-gpt-launcher-dot" aria-hidden="true"></span>
    `;

    const panel = document.createElement("div");
    panel.className = `pcl-gpt-panel${defaultOpen ? "" : " hidden"}`;

    const frame = document.createElement("iframe");
    frame.className = "pcl-gpt-frame";
    frame.title = "OneDesk Assistant";
    frame.src = embedUrl;

    panel.appendChild(frame);
    host.appendChild(panel);
    host.appendChild(launcher);
    document.head.appendChild(style);
    document.body.appendChild(host);

    launcher.addEventListener("click", () => {
      const isOpen = !panel.classList.contains("hidden");
      panel.classList.toggle("hidden", isOpen);
      launcher.setAttribute("aria-expanded", String(!isOpen));
    });
  }

  if (document.body) {
    mountWidget();
    return;
  }

  window.addEventListener("DOMContentLoaded", mountWidget, { once: true });
})();
