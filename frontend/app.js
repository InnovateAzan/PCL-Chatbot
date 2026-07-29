const DEFAULT_API_BASE_URL = "http://127.0.0.1:8085/api";

const runtimeConfig = getRuntimeConfig();
const API_BASE_URL = runtimeConfig.apiBaseUrl;
const EMBED_MODE = runtimeConfig.embedMode;
const HOSTED_MODE = runtimeConfig.hostedMode;
const DEFAULT_OPEN = runtimeConfig.defaultOpen;

const chatForm = document.getElementById("chatForm");
const sendButton = document.getElementById("sendButton");
const messageInput = document.getElementById("messageInput");
const messages = document.getElementById("messages");
const launcherButton = document.getElementById("launcherButton");
const chatWidget = document.getElementById("chatWidget");
const collapseButton = document.getElementById("collapseButton");
const endChatButton = document.getElementById("endChatButton");
const statusNote = document.getElementById("statusNote");

const feedbackModal = document.getElementById("feedbackModal");
const feedbackBackdrop = document.getElementById("feedbackBackdrop");
const closeFeedbackButton = document.getElementById(
  "closeFeedbackButton"
);
const skipFeedbackButton = document.getElementById(
  "skipFeedbackButton"
);
const submitFeedbackButton = document.getElementById(
  "submitFeedbackButton"
);
const feedbackInput = document.getElementById("feedbackInput");
const feedbackChoices = document.querySelectorAll(".feedback-choice");

let selectedRating = "";

document.body.classList.toggle("embed-mode", EMBED_MODE);
document.body.classList.toggle("hosted-mode", HOSTED_MODE);
document.documentElement.classList.toggle("embed-mode", EMBED_MODE);
document.documentElement.classList.toggle("hosted-mode", HOSTED_MODE);

if (HOSTED_MODE) {
  window.addEventListener("resize", scheduleHostLayoutUpdate);
}

setWidgetOpen(DEFAULT_OPEN);
updateFeedbackSubmitState();
checkHealth();

launcherButton?.addEventListener("click", () => {
  const willOpen = chatWidget?.classList.contains("hidden") ?? true;
  setWidgetOpen(willOpen);
});

collapseButton?.addEventListener("click", () => {
  setWidgetOpen(false);
  notifyHostClose();
});

endChatButton?.addEventListener("click", () => {
  openFeedback();
});

closeFeedbackButton?.addEventListener("click", closeFeedback);
skipFeedbackButton?.addEventListener("click", endChatSession);
feedbackBackdrop?.addEventListener("click", closeFeedback);

feedbackChoices.forEach((button) => {
  button.addEventListener("click", () => {
    selectedRating = button.dataset.rating ?? "";

    feedbackChoices.forEach((item) => {
      item.classList.remove("selected");
    });

    button.classList.add("selected");
    updateFeedbackSubmitState();
  });
});

submitFeedbackButton?.addEventListener("click", () => {
  if (!selectedRating) {
    return;
  }

  endChatSession();
});

chatForm?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = messageInput?.value.trim() ?? "";

  if (!message) {
    return;
  }

  appendMessage("user", message);

  messageInput.value = "";
  autoResizeTextarea();
  setComposerState(true);

  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
      }),
    });

    if (!response.ok) {
      let errorMessage = "Chat request failed.";

      try {
        const errorPayload = await response.json();

        if (errorPayload?.detail) {
          errorMessage = String(errorPayload.detail);
        }
      } catch {
        // Use the default error message.
      }

      throw new Error(errorMessage);
    }

    const payload = await response.json();

    appendMessage(
      "bot",
      payload.answer || "No response was received.",
      payload.sources ?? [],
      {
        notice: payload.notice,
        enableFeedback: true,
      }
    );
  } catch (error) {
    console.error("Chat request error:", error);

    appendMessage(
      "bot",
      "The assistant could not reach the backend. Please make sure the API server is running."
    );
  } finally {
    setComposerState(false);
    messageInput?.focus();
  }
});

messageInput?.addEventListener("input", autoResizeTextarea);
messageInput?.addEventListener("keydown", handleComposerKeydown);

function appendMessage(
  role,
  text,
  sources = [],
  meta = {}
) {
  if (!messages) {
    return;
  }

  const article = document.createElement("article");
  article.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  const body = document.createElement("div");
  body.className = "message-body";

  if (role === "bot") {
    body.appendChild(formatAssistantAnswer(text));
  } else {
    body.textContent = String(text || "");
  }

  bubble.appendChild(body);

  if (role === "bot" && meta.notice) {
    const note = document.createElement("p");
    note.className = "message-note";
    note.textContent = String(meta.notice);

    bubble.appendChild(note);
  }

  article.appendChild(bubble);

  if (role === "bot" && meta.enableFeedback) {
    article.appendChild(createFeedbackBar());
  }

  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function formatAssistantAnswer(answer) {
  const container = document.createElement("div");
  container.className = "formatted-answer";

  const normalizedAnswer = normalizeAssistantAnswer(answer);

  const lines = normalizedAnswer
    .split(/\r?\n/)
    .map((line) => line.trim());

  let bulletList = null;

  function closeBulletList() {
    bulletList = null;
  }

  function getBulletList() {
    if (bulletList) {
      return bulletList;
    }

    bulletList = document.createElement("ul");
    bulletList.className = "answer-bullet-list";

    container.appendChild(bulletList);

    return bulletList;
  }

  for (const rawLine of lines) {
    if (!rawLine) {
      closeBulletList();
      continue;
    }

    const sectionMatch = rawLine.match(
      /^\[\s*SECTION\s*\](.*?)\[\s*\/\s*SECTION\s*\]$/i
    );

    if (sectionMatch) {
      closeBulletList();

      const heading = document.createElement("h4");
      heading.className = "answer-section-heading";
      heading.textContent = sectionMatch[1].trim();

      container.appendChild(heading);
      continue;
    }

    const bulletMatch = rawLine.match(
      /^\[\s*BULLET\s*\](.*?)\[\s*\/\s*BULLET\s*\]$/i
    );

    if (bulletMatch) {
      const list = getBulletList();

      const item = document.createElement("li");
      item.textContent = bulletMatch[1].trim();

      list.appendChild(item);
      continue;
    }

    if (
      rawLine.startsWith("• ") ||
      rawLine.startsWith("- ") ||
      rawLine.startsWith("* ")
    ) {
      const list = getBulletList();

      const item = document.createElement("li");
      item.textContent = rawLine.slice(2).trim();

      list.appendChild(item);
      continue;
    }

    closeBulletList();

    const paragraph = document.createElement("p");
    paragraph.className = "answer-paragraph";
    paragraph.textContent = rawLine;

    container.appendChild(paragraph);
  }

  if (!container.hasChildNodes()) {
    const paragraph = document.createElement("p");
    paragraph.className = "answer-paragraph";
    paragraph.textContent = String(answer || "");

    container.appendChild(paragraph);
  }

  return container;
}

function normalizeAssistantAnswer(answer) {
  let text = String(answer || "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");

  // Remove Markdown headings.
  text = text.replace(
    /^\s*#{1,6}\s*/gm,
    ""
  );

  // Remove Markdown bold and underline formatting.
  text = text
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1");

  // Normalize SECTION tags, including different casing and spacing.
  text = text
    .replace(
      /\[\s*section\s*\]/gi,
      "[SECTION]"
    )
    .replace(
      /\[\s*\/\s*section\s*\]/gi,
      "[/SECTION]"
    );

  // Normalize BULLET tags, including malformed casing.
  text = text
    .replace(
      /\[\s*bullet\s*\]/gi,
      "[BULLET]"
    )
    .replace(
      /\[\s*\/\s*bullet\s*\]/gi,
      "[/BULLET]"
    );

  // Ensure each SECTION tag is on a separate line.
  text = text
    .replace(
      /\s*(\[SECTION\])/gi,
      "\n$1"
    )
    .replace(
      /(\[\/SECTION\])\s*/gi,
      "$1\n"
    );

  // Ensure each BULLET tag is on a separate line.
  text = text
    .replace(
      /\s*(\[BULLET\])/gi,
      "\n$1"
    )
    .replace(
      /(\[\/BULLET\])\s*/gi,
      "$1\n"
    );

  // Convert inline bullet symbols into separate lines.
  text = text.replace(
    /\s+•\s+/g,
    "\n• "
  );

  // Convert Markdown bullets to structured BULLET tags.
  text = text.replace(
    /^\s*[-*]\s+(.+)$/gm,
    "[BULLET]$1[/BULLET]"
  );

  text = text.replace(
    /^\s*•\s+(.+)$/gm,
    "[BULLET]$1[/BULLET]"
  );

  // Repair an opening BULLET tag with a missing closing tag.
  text = text.replace(
    /\[BULLET\]([^\n]*?)(?=\n|$)/gi,
    (fullMatch, content) => {
      if (fullMatch.includes("[/BULLET]")) {
        return fullMatch;
      }

      return `[BULLET]${content.trim()}[/BULLET]`;
    }
  );

  // Repair an opening SECTION tag with a missing closing tag.
  text = text.replace(
    /\[SECTION\]([^\n]*?)(?=\n|$)/gi,
    (fullMatch, content) => {
      if (fullMatch.includes("[/SECTION]")) {
        return fullMatch;
      }

      return `[SECTION]${content.trim()}[/SECTION]`;
    }
  );

  // Remove excessive blank lines.
  text = text.replace(
    /\n{3,}/g,
    "\n\n"
  );

  return text.trim();
}

function createSourcesBlock(sources) {
  const sourceBlock = document.createElement("div");
  sourceBlock.className = "sources";

  const title = document.createElement("strong");
  title.className = "sources-title";
  title.textContent = "Reference";

  sourceBlock.appendChild(title);

  sources.forEach((source) => {
    const wrapper = document.createElement("div");
    wrapper.className = "source-item";

    const line = document.createElement("p");

    const section = source.section
      ? `, ${source.section}`
      : "";

    const page = source.page_number
      ? `, page ${source.page_number}`
      : "";

    line.textContent =
      `${source.document_name || "Unknown document"}${section}${page}`;

    wrapper.appendChild(line);

    if (source.snippet) {
      const snippet = document.createElement("p");
      snippet.className = "source-snippet";
      snippet.textContent = source.snippet;

      wrapper.appendChild(snippet);
    }

    sourceBlock.appendChild(wrapper);
  });

  return sourceBlock;
}

function createFeedbackBar() {
  const wrapper = document.createElement("div");
  wrapper.className = "feedback-bar";

  const up = document.createElement("button");
  up.type = "button";
  up.className = "feedback-toggle";
  up.setAttribute("aria-label", "Helpful response");
  up.innerHTML = "&#128077;";

  const down = document.createElement("button");
  down.type = "button";
  down.className = "feedback-toggle";
  down.setAttribute("aria-label", "Unhelpful response");
  down.innerHTML = "&#128078;";

  up.addEventListener("click", () => {
    up.classList.toggle("selected");
    down.classList.remove("selected");
  });

  down.addEventListener("click", () => {
    down.classList.toggle("selected");
    up.classList.remove("selected");
  });

  wrapper.appendChild(up);
  wrapper.appendChild(down);

  return wrapper;
}

function scheduleHostLayoutUpdate() {
  if (!HOSTED_MODE) {
    return;
  }

  window.requestAnimationFrame(() => {
    notifyHostLayout();
  });
}

function notifyHostLayout() {
  if (!HOSTED_MODE || window.parent === window) {
    return;
  }

  const isOpen = !(chatWidget?.classList.contains("hidden") ?? true);
  const activeElement = isOpen ? chatWidget : launcherButton;
  const bounds = activeElement?.getBoundingClientRect();

  if (!bounds) {
    return;
  }

  window.parent.postMessage(
    {
      type: "pcl-gpt:layout",
      isOpen,
      width: Math.ceil(bounds.width),
      height: Math.ceil(bounds.height),
    },
    runtimeConfig.parentOrigin || "*"
  );
}

function notifyHostClose() {
  if (window.parent === window) {
    return;
  }

  window.parent.postMessage(
    {
      type: "pcl-gpt:close",
    },
    runtimeConfig.parentOrigin || "*"
  );
}

function getRuntimeConfig() {
  const params = new URLSearchParams(
    window.location.search
  );

  const surface =
    params.get("surface") ||
    document.body.dataset.surface ||
    "";

  const hostedMode =
    surface.toLowerCase() === "sharepoint";

  const embedMode =
    params.get("embed") === "1" ||
    (
      !hostedMode &&
      document.body.dataset.embed === "true"
    );

  const explicitOpen = parseBooleanFlag(
    params.get("open") ||
      document.body.dataset.open
  );

  const apiBaseCandidate =
    params.get("apiBase") ||
    document.body.dataset.apiBase ||
    window.PCL_GPT_CONFIG?.apiBaseUrl ||
    DEFAULT_API_BASE_URL;

  return {
    apiBaseUrl: normalizeApiBase(apiBaseCandidate),
    embedMode,
    hostedMode,
    parentOrigin:
      String(
        params.get("parentOrigin") ||
          document.body.dataset.parentOrigin ||
          ""
      ).trim(),
    defaultOpen: resolveDefaultOpen(
      explicitOpen,
      embedMode,
      hostedMode
    ),
  };
}

function normalizeApiBase(value) {
  const normalized = String(
    value || DEFAULT_API_BASE_URL
  ).trim();

  return normalized.replace(/\/+$/, "");
}

function parseBooleanFlag(value) {
  if (value == null) {
    return undefined;
  }

  const normalized = String(value).trim().toLowerCase();

  if (!normalized) {
    return undefined;
  }

  if (
    normalized === "1" ||
    normalized === "true" ||
    normalized === "yes"
  ) {
    return true;
  }

  if (
    normalized === "0" ||
    normalized === "false" ||
    normalized === "no"
  ) {
    return false;
  }

  return undefined;
}

function resolveDefaultOpen(
  explicitOpen,
  embedMode,
  hostedMode
) {
  if (typeof explicitOpen === "boolean") {
    return explicitOpen;
  }

  if (embedMode) {
    return true;
  }

  if (hostedMode) {
    return false;
  }

  return true;
}

function handleComposerKeydown(event) {
  if (event.key !== "Enter") {
    return;
  }

  if (event.ctrlKey) {
    const start = messageInput.selectionStart;
    const end = messageInput.selectionEnd;
    const value = messageInput.value;

    messageInput.value =
      `${value.slice(0, start)}\n${value.slice(end)}`;

    messageInput.selectionStart =
      messageInput.selectionEnd =
        start + 1;

    autoResizeTextarea();
    return;
  }

  event.preventDefault();
  chatForm?.requestSubmit();
}

async function checkHealth() {
  if (!statusNote) {
    return;
  }

  if (window.location.protocol === "file:") {
    statusNote.textContent =
      "Open the frontend through http://127.0.0.1:5500 so it can connect to the backend.";

    return;
  }

  try {
    const response = await fetch(
      `${API_BASE_URL}/health`
    );

    if (!response.ok) {
      throw new Error("Health check failed");
    }

    const payload = await response.json();

    statusNote.textContent =
      payload.gemini_configured
        ? "Live Gemini is configured for richer responses."
        : "Policy fallback mode is active until a Gemini API key is added.";
  } catch (error) {
    console.error(
      "Health check error:",
      error
    );

    statusNote.textContent =
      "Backend is offline. Start the local API to activate the assistant.";
  }
}

function setComposerState(isLoading) {
  if (messageInput) {
    messageInput.disabled = isLoading;
  }

  if (sendButton) {
    sendButton.disabled = isLoading;
  }
}

function setWidgetOpen(isOpen) {
  if (!chatWidget || !launcherButton) {
    return;
  }

  chatWidget.classList.toggle(
    "hidden",
    !isOpen
  );

  launcherButton.classList.toggle(
    "hidden",
    isOpen
  );

  launcherButton.setAttribute(
    "aria-expanded",
    String(isOpen)
  );

  if (isOpen) {
    messageInput?.focus();
  }

  scheduleHostLayoutUpdate();
}

function openFeedback() {
  feedbackModal?.classList.remove("hidden");
  feedbackBackdrop?.classList.remove("hidden");
  updateFeedbackSubmitState();
}

function closeFeedback() {
  feedbackModal?.classList.add("hidden");
  feedbackBackdrop?.classList.add("hidden");

  if (feedbackInput) {
    feedbackInput.value = "";
  }

  selectedRating = "";

  feedbackChoices.forEach((item) => {
    item.classList.remove("selected");
  });

  updateFeedbackSubmitState();
}

function endChatSession() {
  closeFeedback();
  resetChatSession();
  setWidgetOpen(false);
  notifyHostClose();
}

function resetChatSession() {
  if (messages) {
    messages.replaceChildren();
  }

  if (messageInput) {
    messageInput.value = "";
    autoResizeTextarea();
  }

  setComposerState(false);
}

function updateFeedbackSubmitState() {
  if (!submitFeedbackButton) {
    return;
  }

  const hasRating = Boolean(selectedRating);

  submitFeedbackButton.disabled = !hasRating;
  submitFeedbackButton.classList.toggle("ready", hasRating);
}

function autoResizeTextarea() {
  if (!messageInput) {
    return;
  }

  messageInput.style.height = "auto";

  messageInput.style.height =
    `${Math.min(
      messageInput.scrollHeight,
      118
    )}px`;
}
