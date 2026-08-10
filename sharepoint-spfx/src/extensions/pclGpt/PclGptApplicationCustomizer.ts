import { BaseApplicationCustomizer } from "@microsoft/sp-application-base";

const WIDGET_VERSION = "20260806-1";
const DEFAULT_CHATBOT_URL = "http://127.0.0.1:5500/embed.html";
const DEFAULT_API_BASE_URL = "https://volley-facial-lumpish.ngrok-free.dev/api";
const DEFAULT_API_RESOURCE = "api://befd94d3-9bc9-414f-81ec-a89a041384f7";
const API_TOKEN_MESSAGE_TYPE = "onedesk-api-token";
const API_TOKEN_REQUEST_MESSAGE_TYPE = "pcl-gpt:api-token-request";

export interface IPclGptApplicationCustomizerProperties {
  enabled?: boolean;
  chatbotUrl?: string;
  apiBaseUrl?: string;
  apiResource?: string;
  oneDeskPath?: string;
  enableClientDebugLogs?: boolean;
}

interface IAadTokenProvider {
  getToken(resource: string): Promise<string>;
}

interface IAadTokenProviderFactory {
  getTokenProvider(): Promise<IAadTokenProvider>;
}

interface ITokenAwareContext {
  aadTokenProviderFactory?: IAadTokenProviderFactory;
}

export default class PclGptApplicationCustomizer
  extends BaseApplicationCustomizer<IPclGptApplicationCustomizerProperties> {

  private root: HTMLDivElement | undefined;
  private launcherButton: HTMLButtonElement | undefined;
  private panel: HTMLDivElement | undefined;
  private overlay: HTMLDivElement | undefined;
  private debugLogsEnabled = false;

  public onInit(): Promise<void> {
    this.debugLogsEnabled = this.properties.enableClientDebugLogs === true;
    const currentPath = window.location.pathname
      .toLowerCase()
      .replace(/\/+$/, "");

    const expectedPath = (
      this.properties.oneDeskPath ||
      "/sitepages/onedesk.aspx"
    )
      .toLowerCase()
      .replace(/\/+$/, "");

    const isOneDeskPage =
      currentPath === expectedPath ||
      currentPath.indexOf(expectedPath) >= 0;

    this.logInfo("extension_loaded", {
      widgetVersion: WIDGET_VERSION,
      chatbotUrl: this.properties.chatbotUrl || DEFAULT_CHATBOT_URL,
      apiBaseUrl: this.properties.apiBaseUrl || DEFAULT_API_BASE_URL,
      currentPath,
      expectedPath,
      oneDeskPageMatched: isOneDeskPage,
    });

    if (!isOneDeskPage) {
      this.logInfo("extension_hidden_not_on_onedesk_page", {
        currentPath,
        expectedPath,
      });
      return Promise.resolve();
    }

    if (this.properties.enabled === false) {
      this.logInfo("extension_disabled");
      return Promise.resolve();
    }

    this.renderLauncher();

    window.addEventListener(
      "message",
      this.handleWidgetMessage
    );

    window.addEventListener(
      "keydown",
      this.handleEscapeKey
    );
    this.logInfo("launcher_rendered");

    return Promise.resolve();
  }

  private renderLauncher(): void {
    if (document.getElementById("pcl-gpt-sharepoint-root")) {
      return;
    }

    this.root = document.createElement("div");
    this.root.id = "pcl-gpt-sharepoint-root";

    this.root.style.position = "fixed";
    this.root.style.right = "28px";
    this.root.style.bottom = "28px";
    this.root.style.zIndex = "999999";
    this.root.style.overflow = "visible";
    this.root.style.fontFamily =
      "Aptos, Segoe UI, Arial, sans-serif";

    this.launcherButton = document.createElement("button");
    this.launcherButton.type = "button";
    this.launcherButton.setAttribute(
      "aria-label",
      "Open OneDesk Assistant"
    );
    this.launcherButton.setAttribute(
      "aria-expanded",
      "false"
    );

    this.launcherButton.style.display = "inline-flex";
    this.launcherButton.style.alignItems = "center";
    this.launcherButton.style.gap = "12px";
    this.launcherButton.style.padding = "0";
    this.launcherButton.style.border = "0";
    this.launcherButton.style.background = "transparent";
    this.launcherButton.style.cursor = "pointer";

    const label = document.createElement("span");
    label.textContent = "OneDesk Assistant";

    label.style.minWidth = "154px";
    label.style.height = "44px";
    label.style.padding = "0 28px";
    label.style.display = "inline-flex";
    label.style.alignItems = "center";
    label.style.justifyContent = "center";
    label.style.borderRadius = "999px";
    label.style.background = "#ffffff";
    label.style.boxShadow =
      "0 14px 34px rgba(18, 71, 41, 0.12)";
    label.style.color = "#0b8a3e";
    label.style.fontSize = "17px";
    label.style.fontWeight = "700";
    label.style.boxSizing = "border-box";
    label.style.transition =
      "transform 160ms ease, box-shadow 160ms ease";

    const mark = document.createElement("span");

    mark.style.width = "50px";
    mark.style.height = "50px";
    mark.style.display = "inline-grid";
    mark.style.placeItems = "center";
    mark.style.borderRadius = "50%";
    mark.style.background = "#ffffff";
    mark.style.boxShadow =
      "0 14px 34px rgba(18, 71, 41, 0.12)";
    mark.style.boxSizing = "border-box";
    mark.style.transition =
      "transform 160ms ease, box-shadow 160ms ease";

    const logo = document.createElement("img");
    logo.src = this.getLogoUrl();
    logo.alt = "Pakistan Cables";

    logo.style.width = "34px";
    logo.style.height = "34px";
    logo.style.objectFit = "contain";
    logo.style.display = "block";

    mark.appendChild(logo);

    this.launcherButton.appendChild(label);
    this.launcherButton.appendChild(mark);

    this.launcherButton.addEventListener(
      "mouseenter",
      () => {
        label.style.transform = "translateY(-2px)";
        mark.style.transform = "translateY(-2px)";
      }
    );

    this.launcherButton.addEventListener(
      "mouseleave",
      () => {
        label.style.transform = "translateY(0)";
        mark.style.transform = "translateY(0)";
      }
    );

    this.launcherButton.addEventListener(
      "click",
      () => {
        this.openPanel();
      }
    );

    this.root.appendChild(this.launcherButton);
    document.body.appendChild(this.root);
  }

  private openPanel(): void {
    if (
      !this.root ||
      !this.launcherButton
    ) {
      return;
    }

    if (this.panel) {
      this.panel.style.display = "block";
      if (this.overlay) {
        this.overlay.style.display = "block";
      }
      this.launcherButton.style.display = "none";
      this.launcherButton.setAttribute(
        "aria-expanded",
        "true"
      );
      this.applyResponsivePanelSize();
      window.addEventListener(
        "resize",
        this.applyResponsivePanelSize
      );
      return;
    }

    this.launcherButton.style.display = "none";
    this.launcherButton.setAttribute(
      "aria-expanded",
      "true"
    );

    this.overlay = document.createElement("div");
    this.overlay.id = "pcl-gpt-sharepoint-overlay";

    this.overlay.style.position = "fixed";
    this.overlay.style.top = "0";
    this.overlay.style.right = "0";
    this.overlay.style.bottom = "0";
    this.overlay.style.left = "0";
    this.overlay.style.zIndex = "999997";
    this.overlay.style.background =
      "rgba(24, 31, 27, 0.16)";
    this.overlay.style.setProperty(
      "backdrop-filter",
      "blur(1px)"
    );

    this.overlay.addEventListener(
      "click",
      () => {
        this.closePanel();
      }
    );

    this.panel = document.createElement("div");
    this.panel.id = "pcl-gpt-sharepoint-panel";
    this.panel.setAttribute("role", "dialog");
    this.panel.setAttribute("aria-label", "OneDesk Assistant");

    this.panel.style.position = "fixed";
    this.panel.style.top = "92px";
    this.panel.style.right = "24px";
    this.panel.style.bottom = "24px";
    this.panel.style.width = "620px";
    this.panel.style.height = "calc(100vh - 116px)";
    this.panel.style.maxWidth = "calc(100vw - 48px)";
    this.panel.style.maxHeight = "calc(100vh - 116px)";
    this.panel.style.zIndex = "999998";
    this.panel.style.display = "block";
    this.panel.style.padding = "0";
    this.panel.style.margin = "0";
    this.panel.style.overflow = "hidden";
    this.panel.style.border =
      "1px solid rgba(0, 135, 68, 0.12)";
    this.panel.style.borderRadius = "26px";
    this.panel.style.background = "#ffffff";
    this.panel.style.boxShadow =
      "0 24px 70px rgba(20, 36, 27, 0.28)";
    this.panel.style.boxSizing = "border-box";

    const iframe = document.createElement("iframe");
    iframe.id = "pcl-gpt-frame";
    iframe.src = this.getChatbotUrl();
    iframe.title = "OneDesk Assistant";

    iframe.setAttribute(
      "allow",
      "clipboard-read; clipboard-write"
    );

    iframe.style.position = "absolute";
    iframe.style.top = "0";
    iframe.style.right = "0";
    iframe.style.bottom = "0";
    iframe.style.left = "0";
    iframe.style.width = "100%";
    iframe.style.height = "100%";
    iframe.style.minWidth = "0";
    iframe.style.minHeight = "0";
    iframe.style.maxWidth = "100%";
    iframe.style.maxHeight = "100%";
    iframe.style.display = "block";
    iframe.style.margin = "0";
    iframe.style.padding = "0";
    iframe.style.border = "0";
    iframe.style.background = "#ffffff";
    iframe.style.boxSizing = "border-box";

    this.panel.appendChild(iframe);

    document.body.appendChild(this.overlay);
    document.body.appendChild(this.panel);

    this.applyResponsivePanelSize();

    window.addEventListener(
      "resize",
      this.applyResponsivePanelSize
    );
  }

  private getChatbotUrl(): string {
    const rawChatbotUrl =
      this.properties.chatbotUrl ||
      DEFAULT_CHATBOT_URL;
    const apiBaseUrl =
      this.properties.apiBaseUrl ||
      DEFAULT_API_BASE_URL;

    this.warnIfInsecureApiBase(apiBaseUrl);

    try {
      const url = new URL(
        rawChatbotUrl,
        window.location.href
      );

      url.searchParams.set("v", WIDGET_VERSION);
      url.searchParams.set("embed", "1");
      url.searchParams.set("apiBase", apiBaseUrl);
      url.searchParams.set(
        "parentOrigin",
        window.location.origin
      );
      this.appendUserContext(url);

      this.logInfo("iframe_url_prepared", {
        iframePath: url.pathname,
        apiBaseUrl,
        widgetVersion: WIDGET_VERSION,
        iframeOrigin: url.origin,
      });

      return url.toString();
    } catch {
      const separator =
        rawChatbotUrl.indexOf("?") >= 0
          ? "&"
          : "?";

      return (
        `${rawChatbotUrl}${separator}embed=1`
        + `&apiBase=${encodeURIComponent(apiBaseUrl)}`
        + `&v=${encodeURIComponent(WIDGET_VERSION)}`
        + `&parentOrigin=${encodeURIComponent(window.location.origin)}`
        + this.getEncodedUserContext()
      );
    }
  }

  private appendUserContext(url: URL): void {
    const profile = this.getCurrentUserProfile();

    Object.keys(profile).forEach((key) => {
      const value = profile[key];

      if (value) {
        url.searchParams.set(key, value);
      }
    });
  }

  private getEncodedUserContext(): string {
    const profile = this.getCurrentUserProfile();

    return Object.keys(profile)
      .filter((key) => Boolean(profile[key]))
      .map((key) => `&${key}=${encodeURIComponent(profile[key])}`)
      .join("");
  }

  private getCurrentUserProfile(): { [key: string]: string } {
    const user = this.context.pageContext.user;

    return {
      displayName: user.displayName || "",
      preferredName: user.displayName || "",
      email: user.email || user.loginName || "",
      entraObjectId: "",
    };
  }

  private getLogoUrl(): string {
    const rawChatbotUrl =
      this.properties.chatbotUrl ||
      "http://127.0.0.1:5500/";

    try {
      return new URL(
        "/assets/pcl-logo.png",
        rawChatbotUrl
      ).toString();
    } catch {
      return "http://127.0.0.1:5500/assets/pcl-logo.png";
    }
  }

  private warnIfInsecureApiBase(apiBaseUrl: string): void {
    if (
      window.location.protocol === "https:" &&
      apiBaseUrl.indexOf("https://") !== 0
    ) {
      this.logWarn("insecure_api_base_url", { apiBaseUrl });
    }
  }

  private handleWidgetMessage = (
    event: MessageEvent
  ): void => {
    const messageType = event.data?.type;

    if (
      messageType !== "pcl-gpt:close" &&
      messageType !== "PCL_GPT_CLOSE" &&
      messageType !== API_TOKEN_REQUEST_MESSAGE_TYPE
    ) {
      return;
    }

    if (messageType === API_TOKEN_REQUEST_MESSAGE_TYPE) {
      this.sendApiToken(event).catch((error) => {
        this.logError("token_message_handling_failed", {
          errorType: error instanceof Error ? error.name : typeof error,
          message: error instanceof Error ? error.message : String(error),
        });
      });
      return;
    }

    this.closePanel();
  };

  private async sendApiToken(event: MessageEvent): Promise<void> {
    const frameWindow = this.getFrameWindow();

    if (!frameWindow || event.source !== frameWindow) {
      this.logWarn("token_request_rejected", {
        reason: "unexpected_message_source",
        eventOrigin: event.origin,
      });
      return;
    }

    let expectedOrigin: string;

    try {
      const iframe = document.getElementById(
        "pcl-gpt-frame"
      ) as HTMLIFrameElement | null;

      if (!iframe?.src) {
        throw new Error("OneDesk iframe URL is unavailable.");
      }

      expectedOrigin = new URL(iframe.src).origin;
    } catch (error) {
      this.logError("iframe_origin_resolution_failed", {
        errorType: error instanceof Error ? error.name : typeof error,
        message: error instanceof Error ? error.message : String(error),
      });
      return;
    }

    if (event.origin !== expectedOrigin) {
      this.logWarn("token_request_rejected", {
        reason: "unexpected_origin",
        eventOrigin: event.origin,
        expectedOrigin,
      });
      return;
    }

    try {
      const resource =
        this.properties.apiResource ||
        DEFAULT_API_RESOURCE;

      this.logInfo("token_acquisition_started", {
        resource,
      });

      const tokenFactory = (
        this.context as unknown as ITokenAwareContext
      ).aadTokenProviderFactory;

      if (!tokenFactory) {
        throw new Error(
          "AadTokenProviderFactory is not available."
        );
      }

      const provider = await tokenFactory.getTokenProvider();
      const token = await provider.getToken(resource);

      if (!token || this.jwtSegmentCount(token) !== 3) {
        throw new Error(
          "Microsoft returned an invalid API token."
        );
      }

      this.logInfo("token_acquisition_success", {
        tokenPresent: true,
        tokenLength: token.length,
        jwtSegmentCount: this.jwtSegmentCount(token),
        resource,
      });

      frameWindow.postMessage(
        {
          type: API_TOKEN_MESSAGE_TYPE,
          accessToken: token,
          expiresIn: 300,
          errorCode: "",
        },
        expectedOrigin
      );

      this.logInfo("post_message_sent", {
        type: API_TOKEN_MESSAGE_TYPE,
        targetOrigin: expectedOrigin,
        tokenPresent: true,
        tokenLength: token.length,
        jwtSegmentCount: this.jwtSegmentCount(token),
      });
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error);

      this.logError("token_acquisition_failed", {
        errorType:
          error instanceof Error
            ? error.name
            : typeof error,
        message: errorMessage,
        requestedResource:
          this.properties.apiResource ||
          DEFAULT_API_RESOURCE,
      });

      frameWindow.postMessage(
        {
          type: API_TOKEN_MESSAGE_TYPE,
          accessToken: "",
          expiresIn: 0,
          errorCode: "token_acquisition_failed",
        },
        expectedOrigin
      );

      this.logInfo("post_message_sent", {
        type: API_TOKEN_MESSAGE_TYPE,
        targetOrigin: expectedOrigin,
        tokenPresent: false,
        tokenLength: 0,
        jwtSegmentCount: 0,
        errorCode: "token_acquisition_failed",
      });
    }
  }

  private logInfo(eventName: string, fields: Record<string, unknown> = {}): void {
    if (!this.debugLogsEnabled) {
      return;
    }
    console.info("[OneAssist SPFx]", eventName, this.sanitizeLogFields(fields));
  }

  private logWarn(eventName: string, fields: Record<string, unknown> = {}): void {
    console.warn("[OneAssist SPFx]", eventName, this.sanitizeLogFields(fields));
  }

  private logError(eventName: string, fields: Record<string, unknown> = {}): void {
    console.error("[OneAssist SPFx]", eventName, this.sanitizeLogFields(fields));
  }

  private sanitizeLogFields(fields: Record<string, unknown>): Record<string, unknown> {
    const output: Record<string, unknown> = {};
    const safeTokenDiagnostics = new Set([
      "tokenPresent",
      "tokenLength",
      "jwtSegmentCount",
    ]);
    Object.keys(fields || {}).forEach((key) => {
      const lower = key.toLowerCase();
      if (safeTokenDiagnostics.has(key)) {
        output[key] = fields[key];
      } else if (
        lower.indexOf("token") >= 0 ||
        lower.indexOf("authorization") >= 0 ||
        lower.indexOf("secret") >= 0 ||
        lower.indexOf("password") >= 0 ||
        lower.indexOf("cookie") >= 0
      ) {
        output[key] = "[REDACTED]";
      } else {
        output[key] = fields[key];
      }
    });
    return output;
  }

  private jwtSegmentCount(token: string | undefined): number {
    const value = String(token || "").trim();
    return value ? value.split(".").length : 0;
  }

  private getFrameWindow(): Window | null {
    const iframe = document.getElementById(
      "pcl-gpt-frame"
    ) as HTMLIFrameElement | null;

    return iframe?.contentWindow || null;
  }

  private handleEscapeKey = (
    event: KeyboardEvent
  ): void => {
    if (
      event.key === "Escape" &&
      this.panel
    ) {
      this.closePanel();
    }
  };

  private closePanel(): void {
    window.removeEventListener(
      "resize",
      this.applyResponsivePanelSize
    );

    if (this.panel) {
      this.panel.style.display = "none";
    }

    if (this.overlay) {
      this.overlay.style.display = "none";
    }

    if (this.launcherButton) {
      this.launcherButton.style.display =
        "inline-flex";

      this.launcherButton.setAttribute(
        "aria-expanded",
        "false"
      );
    }
  }

  private applyResponsivePanelSize = (): void => {
    if (!this.panel || !this.root) {
      return;
    }

    const compactViewport =
      window.innerWidth <= 768;

    if (compactViewport) {
      this.panel.style.top = "10px";
      this.panel.style.right = "10px";
      this.panel.style.bottom = "10px";
      this.panel.style.width =
        "calc(100vw - 20px)";
      this.panel.style.height =
        "calc(100vh - 20px)";
      this.panel.style.maxWidth = "none";
      this.panel.style.maxHeight =
        "calc(100vh - 20px)";
      this.panel.style.borderRadius = "20px";

      this.root.style.right = "10px";
      this.root.style.bottom = "10px";
    } else {
      this.panel.style.top = "92px";
      this.panel.style.right = "24px";
      this.panel.style.bottom = "24px";
      this.panel.style.width = "620px";
      this.panel.style.height =
        "calc(100vh - 116px)";
      this.panel.style.maxWidth =
        "calc(100vw - 48px)";
      this.panel.style.maxHeight =
        "calc(100vh - 116px)";
      this.panel.style.borderRadius = "26px";

      this.root.style.right = "28px";
      this.root.style.bottom = "28px";
    }
  };

  protected onDispose(): void {
    window.removeEventListener(
      "message",
      this.handleWidgetMessage
    );

    window.removeEventListener(
      "keydown",
      this.handleEscapeKey
    );

    window.removeEventListener(
      "resize",
      this.applyResponsivePanelSize
    );

    this.closePanel();

    if (this.panel) {
      this.panel.remove();
      this.panel = undefined;
    }

    if (this.overlay) {
      this.overlay.remove();
      this.overlay = undefined;
    }

    if (this.root) {
      this.root.remove();
      this.root = undefined;
    }

    this.launcherButton = undefined;
    this.panel = undefined;
    this.overlay = undefined;
  }
}