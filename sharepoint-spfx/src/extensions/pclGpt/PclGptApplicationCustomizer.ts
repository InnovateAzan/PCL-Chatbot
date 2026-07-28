import { BaseApplicationCustomizer } from "@microsoft/sp-application-base";

export interface IPclGptApplicationCustomizerProperties {
  chatbotUrl?: string;
  oneDeskPath?: string;
}

export default class PclGptApplicationCustomizer
  extends BaseApplicationCustomizer<IPclGptApplicationCustomizerProperties> {

  private launcherRoot: HTMLDivElement | undefined;
  private panelRoot: HTMLDivElement | undefined;
  private overlayRoot: HTMLDivElement | undefined;
  private launcherButton: HTMLButtonElement | undefined;

  public onInit(): Promise<void> {
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

    console.log("PCL GPT extension loaded");
    console.log("Current path:", currentPath);
    console.log("Expected path:", expectedPath);

    if (!isOneDeskPage) {
      console.log("PCL GPT hidden because this is not One Desk.");
      return Promise.resolve();
    }

    this.renderLauncher();

    return Promise.resolve();
  }

  private renderLauncher(): void {
    if (document.getElementById("pcl-gpt-launcher-root")) {
      return;
    }

    this.launcherRoot = document.createElement("div");
    this.launcherRoot.id = "pcl-gpt-launcher-root";

    this.launcherButton = document.createElement("button");
    this.launcherButton.id = "pcl-gpt-launcher-button";
    this.launcherButton.type = "button";
    this.launcherButton.setAttribute("aria-label", "Open PCL GPT");
    this.launcherButton.setAttribute("aria-expanded", "false");

    Object.assign(this.launcherButton.style, {
      position: "fixed",
      right: "28px",
      bottom: "28px",
      zIndex: "999999",
      display: "flex",
      alignItems: "center",
      gap: "14px",
      padding: "0",
      border: "none",
      background: "transparent",
      cursor: "pointer",
      fontFamily: "Segoe UI, Arial, sans-serif"
    });

    const label = document.createElement("span");
    label.textContent = "PCL GPT";

    Object.assign(label.style, {
      minWidth: "165px",
      padding: "17px 28px",
      borderRadius: "999px",
      background: "#ffffff",
      color: "#008744",
      boxShadow: "0 14px 35px rgba(25, 45, 32, 0.18)",
      fontSize: "19px",
      fontWeight: "700",
      textAlign: "center",
      transition: "transform 160ms ease, box-shadow 160ms ease"
    });

    const logoCircle = document.createElement("span");

    Object.assign(logoCircle.style, {
      width: "62px",
      height: "62px",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: "50%",
      background: "#ffffff",
      boxShadow: "0 14px 35px rgba(25, 45, 32, 0.18)",
      transition: "transform 160ms ease, box-shadow 160ms ease"
    });

    const logoText = document.createElement("span");
    logoText.textContent = "PCL";

    Object.assign(logoText.style, {
      width: "43px",
      height: "43px",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      border: "2px solid #008744",
      borderRadius: "50%",
      color: "#008744",
      fontSize: "11px",
      fontWeight: "800"
    });

    logoCircle.appendChild(logoText);

    this.launcherButton.appendChild(label);
    this.launcherButton.appendChild(logoCircle);

    this.launcherButton.addEventListener("mouseenter", () => {
      label.style.transform = "translateY(-2px)";
      logoCircle.style.transform = "translateY(-2px)";
    });

    this.launcherButton.addEventListener("mouseleave", () => {
      label.style.transform = "translateY(0)";
      logoCircle.style.transform = "translateY(0)";
    });

    this.launcherButton.addEventListener("click", () => {
      if (this.panelRoot) {
        this.closePanel();
      } else {
        this.openPanel();
      }
    });

    this.launcherRoot.appendChild(this.launcherButton);
    document.body.appendChild(this.launcherRoot);
  }

  private openPanel(): void {
    const chatbotUrl =
      this.properties.chatbotUrl ||
      "http://127.0.0.1:5500/?embed=1";

    this.overlayRoot = document.createElement("div");
    this.overlayRoot.id = "pcl-gpt-overlay";

    Object.assign(this.overlayRoot.style, {
      position: "fixed",
      inset: "0",
      zIndex: "999997",
      background: "rgba(24, 31, 27, 0.18)",
      backdropFilter: "blur(1px)"
    });

    this.overlayRoot.addEventListener("click", () => {
      this.closePanel();
    });

    this.panelRoot = document.createElement("div");
    this.panelRoot.id = "pcl-gpt-panel";
    this.panelRoot.setAttribute("role", "dialog");
    this.panelRoot.setAttribute("aria-label", "PCL GPT");

    Object.assign(this.panelRoot.style, {
      position: "fixed",
      top: "92px",
      right: "24px",
      bottom: "24px",
      width: "620px",
      maxWidth: "calc(100vw - 48px)",
      zIndex: "999998",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      border: "1px solid rgba(0, 135, 68, 0.12)",
      borderRadius: "26px",
      background: "#ffffff",
      boxShadow: "0 24px 70px rgba(20, 36, 27, 0.28)"
    });

    const header = document.createElement("div");

    Object.assign(header.style, {
      minHeight: "74px",
      padding: "12px 18px",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "12px",
      borderBottom: "1px solid #eee8ef",
      background: "#ffffff"
    });

    const identity = document.createElement("div");

    Object.assign(identity.style, {
      display: "flex",
      alignItems: "center",
      gap: "12px"
    });

    const headerLogo = document.createElement("div");
    headerLogo.textContent = "PCL";

    Object.assign(headerLogo.style, {
      width: "42px",
      height: "42px",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      border: "2px solid #008744",
      borderRadius: "50%",
      color: "#008744",
      fontSize: "11px",
      fontWeight: "800"
    });

    const titleWrapper = document.createElement("div");

    Object.assign(titleWrapper.style, {
      display: "flex",
      flexDirection: "column",
      gap: "2px"
    });

    const title = document.createElement("strong");
    title.textContent = "PCL GPT";

    Object.assign(title.style, {
      fontSize: "18px",
      color: "#202124"
    });

    const subtitle = document.createElement("span");
    subtitle.textContent = "Pakistan Cables IT Policy Assistant";

    Object.assign(subtitle.style, {
      fontSize: "13px",
      color: "#7b747f"
    });

    titleWrapper.appendChild(title);
    titleWrapper.appendChild(subtitle);

    identity.appendChild(headerLogo);
    identity.appendChild(titleWrapper);

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.textContent = "×";
    closeButton.setAttribute("aria-label", "Close PCL GPT");

    Object.assign(closeButton.style, {
      width: "42px",
      height: "42px",
      border: "1px solid #dcd6df",
      borderRadius: "50%",
      background: "#ffffff",
      color: "#37313a",
      cursor: "pointer",
      fontSize: "27px",
      lineHeight: "1"
    });

    closeButton.addEventListener("click", () => {
      this.closePanel();
    });

    const iframe = document.createElement("iframe");
    iframe.src = chatbotUrl;
    iframe.title = "PCL GPT";
    iframe.setAttribute(
      "allow",
      "clipboard-read; clipboard-write"
    );

    Object.assign(iframe.style, {
      width: "100%",
      height: "100%",
      flex: "1 1 auto",
      border: "0",
      background: "#ffffff"
    });

    header.appendChild(identity);
    header.appendChild(closeButton);

    this.panelRoot.appendChild(header);
    this.panelRoot.appendChild(iframe);

    document.body.appendChild(this.overlayRoot);
    document.body.appendChild(this.panelRoot);

    this.launcherButton?.setAttribute("aria-expanded", "true");

    this.applyResponsivePanelSize();
    window.addEventListener("resize", this.applyResponsivePanelSize);
  }

  private applyResponsivePanelSize = (): void => {
    if (!this.panelRoot) {
      return;
    }

    if (window.innerWidth <= 768) {
      Object.assign(this.panelRoot.style, {
        top: "10px",
        right: "10px",
        bottom: "10px",
        width: "calc(100vw - 20px)",
        maxWidth: "none",
        borderRadius: "20px"
      });
    } else {
      Object.assign(this.panelRoot.style, {
        top: "92px",
        right: "24px",
        bottom: "24px",
        width: "620px",
        maxWidth: "calc(100vw - 48px)",
        borderRadius: "26px"
      });
    }
  };

  private closePanel(): void {
    window.removeEventListener(
      "resize",
      this.applyResponsivePanelSize
    );

    this.panelRoot?.remove();
    this.overlayRoot?.remove();

    this.panelRoot = undefined;
    this.overlayRoot = undefined;

    this.launcherButton?.setAttribute("aria-expanded", "false");
  }

  protected onDispose(): void {
    window.removeEventListener(
      "resize",
      this.applyResponsivePanelSize
    );

    this.closePanel();

    this.launcherRoot?.remove();
    this.launcherRoot = undefined;
    this.launcherButton = undefined;
  }
}