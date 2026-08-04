const DEFAULT_API_BASE_URL = "http://127.0.0.1:8085/api";
const LOCAL_PROFILE_STORAGE_KEY = "oneassist.localProfile";
const ACTIVE_SESSION_STORAGE_PREFIX = "oneassist.activeSessionId";

const runtimeConfig = getRuntimeConfig();
const API_BASE_URL = runtimeConfig.apiBaseUrl;
const EMBED_MODE = runtimeConfig.embedMode;
const HOSTED_MODE = runtimeConfig.hostedMode;
const DEFAULT_OPEN = runtimeConfig.defaultOpen;
const ENABLE_HISTORY_PANEL = runtimeConfig.enableHistoryPanel;

const chatForm = document.getElementById("chatForm");
const sendButton = document.getElementById("sendButton");
const messageInput = document.getElementById("messageInput");
const messages = document.getElementById("messages");
const launcherButton = document.getElementById("launcherButton");
const chatWidget = document.getElementById("chatWidget");
const collapseButton = document.getElementById("collapseButton");
const endChatButton = document.getElementById("endChatButton");

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
let currentUser = null;
let currentSessionId = "";
let initializingUserPromise = null;
let ensuringSessionPromise = null;
let typingIndicatorElement = null;
const renderedMessageKeys = new Set();

document.body.classList.toggle("embed-mode", EMBED_MODE);
document.body.classList.toggle("hosted-mode", HOSTED_MODE);
document.documentElement.classList.toggle("embed-mode", EMBED_MODE);
document.documentElement.classList.toggle("hosted-mode", HOSTED_MODE);

if (HOSTED_MODE) {
  window.addEventListener("resize", scheduleHostLayoutUpdate);
}

setWidgetOpen(DEFAULT_OPEN);
updateFeedbackSubmitState();
prepareActiveSession().catch((error) => {
  console.error("Active chat session initialization error:", error);
});

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
  showTypingIndicator();

  try {
    let user = null;
    let sessionId = currentSessionId || "";
    let historyEnabled = false;

    try {
      user = await initializeCurrentUser();
      sessionId = await ensureChatSession(user);
      historyEnabled = Boolean(user?.userId && sessionId);
    } catch (historyError) {
      console.warn(
        "Legacy chat history session unavailable; using existing PostgreSQL chat save flow.",
        historyError
      );
    }

    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(historyEnabled
          ? { "X-OneAssist-User-Id": String(user.userId) }
          : {}),
      },
      body: JSON.stringify({
        message,
        ...(historyEnabled ? { sessionId } : {}),
        ...(currentSessionId ? { sessionUuid: currentSessionId } : {}),
        userEmail: runtimeConfig.userProfile.email,
        displayName: runtimeConfig.userProfile.displayName,
        preferredName: runtimeConfig.userProfile.preferredName,
        department: runtimeConfig.userProfile.department,
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
    persistResponseSession(payload);
    removeTypingIndicator();

    appendMessage(
      "bot",
      payload.answer || "No response was received.",
      payload.sources ?? [],
      {
        notice: payload.notice,
        enableFeedback: Boolean(payload.assistantMessageId),
        assistantMessageId: payload.assistantMessageId,
        messageId: payload.assistantMessageId,
      }
    );
  } catch (error) {
    console.error("Chat request error:", error);
    removeTypingIndicator();
    const errorText = String(
      error?.message || ""
    ).trim();
    const fallbackMessage = HOSTED_MODE
      ? (
        `The assistant could not complete the request. `
        + `Backend: ${API_BASE_URL}. `
        + `Reason: ${errorText || "Unknown error."}`
      )
      : (
        "The assistant could not reach the backend. "
        + "Please make sure the API server is running."
      );

    appendMessage(
      "bot",
      fallbackMessage
    );
  } finally {
    removeTypingIndicator();
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

  const messageKey = buildRenderedMessageKey(role, meta);
  if (messageKey && renderedMessageKeys.has(messageKey)) {
    return;
  }

  const article = document.createElement("article");
  article.className = `message ${role}`;
  if (messageKey) {
    article.dataset.messageKey = messageKey;
    renderedMessageKeys.add(messageKey);
  }

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

  const noticeElement = buildNoticeElement(
    sources,
    meta.notice,
  );

  if (role === "bot" && noticeElement) {
    bubble.appendChild(noticeElement);
  }

  article.appendChild(bubble);

  if (role === "bot" && meta.enableFeedback) {
    article.appendChild(createFeedbackBar(meta.assistantMessageId));
  }

  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function showTypingIndicator() {
  if (!messages || typingIndicatorElement) {
    return;
  }

  const article = document.createElement("article");
  article.className = "message bot typing-indicator-message";
  article.setAttribute("aria-live", "polite");

  const bubble = document.createElement("div");
  bubble.className = "message-bubble typing-indicator-bubble";

  const dots = document.createElement("div");
  dots.className = "typing-dots";
  dots.setAttribute("aria-label", "Assistant is typing");

  for (let index = 0; index < 3; index += 1) {
    const dot = document.createElement("span");
    dot.className = "typing-dot";
    dots.appendChild(dot);
  }

  bubble.appendChild(dots);
  article.appendChild(bubble);
  messages.appendChild(article);
  typingIndicatorElement = article;
  messages.scrollTop = messages.scrollHeight;
}

function removeTypingIndicator() {
  if (!typingIndicatorElement) {
    return;
  }

  typingIndicatorElement.remove();
  typingIndicatorElement = null;
}

function buildRenderedMessageKey(role, meta = {}) {
  const id =
    meta.messageId ||
    meta.assistantMessageId ||
    meta.userMessageId ||
    "";

  if (!id) {
    return "";
  }

  return `${role}:${id}`;
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

function formatSourceLabel(source) {
  const rawName = String(
    source?.display_title ||
    source?.displayTitle ||
    source?.title ||
    source?.document_name ||
    source?.documentName ||
    "Unknown policy"
  );
  const policyName = rawName
    .replace(/\.[^.]+$/i, "")
    .replace(/\s+/g, " ")
    .trim();

  const pages = Array.isArray(source?.pages)
    ? source.pages
        .map((page) => Number(page))
        .filter((page) => Number.isInteger(page) && page > 0)
    : [];
  const uniquePages = [...new Set(pages)].sort((a, b) => a - b);
  const pageNumber = source?.page ?? source?.page_number ?? source?.pageNumber;
  const pageLabel = uniquePages.length > 1
    ? `Pages ${uniquePages.join(", ")}`
    : uniquePages.length === 1
      ? `Page ${uniquePages[0]}`
      : pageNumber
        ? `Page ${pageNumber}`
        : "Page unavailable";

  return `${policyName} — ${pageLabel}`;
}

function buildNoticeElement(sources, fallbackNotice) {
  if (Array.isArray(sources) && sources.length > 0) {
    const uniqueSources = [];
    const seen = new Set();

    sources.forEach((source) => {
      const label = formatSourceLabel(source);
      const rawName = String(
        source?.document_number ||
        source?.documentNumber ||
        source?.display_title ||
        source?.displayTitle ||
        source?.title ||
        source?.document_name ||
        source?.documentName ||
        "Unknown policy"
      ).toLowerCase();
      const key = rawName;

      if (label && !seen.has(key)) {
        seen.add(key);
        uniqueSources.push(label);
      }
    });

    if (uniqueSources.length > 0) {
      const wrapper = document.createElement("div");
      wrapper.className = "sources";

      const title = document.createElement("div");
      title.className = "sources-title";
      title.textContent = "Sources:";
      wrapper.appendChild(title);

      const list = document.createElement("ul");
      list.className = "sources-list";

      uniqueSources.forEach((label) => {
        const item = document.createElement("li");
        item.className = "source-item";
        item.textContent = label;
        list.appendChild(item);
      });

      wrapper.appendChild(list);
      return wrapper;
    }
  }

  if (fallbackNotice) {
    const note = document.createElement("p");
    note.className = "message-note";
    note.textContent = String(fallbackNotice);
    return note;
  }

  return null;
}

function createFeedbackBar(assistantMessageId) {
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

  up.addEventListener("click", async () => {
    up.classList.add("selected");
    down.classList.remove("selected");
    await submitMessageFeedback(
      assistantMessageId,
      5,
      "HELPFUL",
      wrapper
    );
  });

  down.addEventListener("click", async () => {
    down.classList.add("selected");
    up.classList.remove("selected");
    await submitMessageFeedback(
      assistantMessageId,
      1,
      "NOT_HELPFUL",
      wrapper
    );
  });

  wrapper.appendChild(up);
  wrapper.appendChild(down);

  return wrapper;
}

async function submitMessageFeedback(
  assistantMessageId,
  rating,
  feedbackType,
  wrapper
) {
  if (!assistantMessageId || !currentUser) {
    return;
  }

  wrapper.classList.remove("error");
  wrapper.classList.add("saving");

  try {
    const response = await fetch(
      `${API_BASE_URL}/messages/${assistantMessageId}/feedback`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-OneAssist-User-Id": String(currentUser.userId),
        },
        body: JSON.stringify({
          rating,
          feedbackType,
        }),
      }
    );

    if (!response.ok) {
      throw new Error("Feedback could not be saved.");
    }

    wrapper.classList.add("saved");
  } catch (error) {
    console.error("Feedback error:", error);
    wrapper.classList.add("error");
  } finally {
    wrapper.classList.remove("saving");
  }
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
    enableHistoryPanel: parseBooleanFlag(
      params.get("enableHistory") ||
        document.body.dataset.enableHistory ||
        window.PCL_GPT_CONFIG?.enableHistory
    ) === true,
    userProfile: buildUserProfile(params),
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

function buildUserProfile(params) {
  const configProfile = window.PCL_GPT_CONFIG?.userProfile || {};
  const savedProfile = readLocalProfile();

  const profile = {
    displayName:
      params.get("displayName") ||
      configProfile.displayName ||
      savedProfile.displayName ||
      "Local OneAssist User",
    preferredName:
      params.get("preferredName") ||
      configProfile.preferredName ||
      savedProfile.preferredName ||
      "",
    email:
      params.get("email") ||
      configProfile.email ||
      savedProfile.email ||
      "local.oneassist.user@example.com",
    employeeId:
      params.get("employeeId") ||
      configProfile.employeeId ||
      savedProfile.employeeId ||
      "",
    department:
      params.get("department") ||
      configProfile.department ||
      savedProfile.department ||
      "",
    jobTitle:
      params.get("jobTitle") ||
      configProfile.jobTitle ||
      savedProfile.jobTitle ||
      "",
    entraObjectId:
      params.get("entraObjectId") ||
      configProfile.entraObjectId ||
      savedProfile.entraObjectId ||
      "",
  };

  writeLocalProfile(profile);
  return profile;
}

function readLocalProfile() {
  try {
    return JSON.parse(
      window.localStorage.getItem(LOCAL_PROFILE_STORAGE_KEY) || "{}"
    );
  } catch {
    return {};
  }
}

function writeLocalProfile(profile) {
  try {
    window.localStorage.setItem(
      LOCAL_PROFILE_STORAGE_KEY,
      JSON.stringify(profile)
    );
  } catch {
    // Local storage can be disabled in embedded browser contexts.
  }
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

async function initializeCurrentUser() {
  if (currentUser) {
    return currentUser;
  }

  if (initializingUserPromise) {
    return initializingUserPromise;
  }

  initializingUserPromise = fetch(`${API_BASE_URL}/users/initialize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(runtimeConfig.userProfile),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error("User initialization failed.");
      }

      currentUser = await response.json();
      return currentUser;
    })
    .catch((error) => {
      initializingUserPromise = null;
      throw error;
    });

  return initializingUserPromise;
}

async function prepareActiveSession() {
  const storedSessionId = readActiveSessionId();
  if (!storedSessionId) {
    return "";
  }

  currentSessionId = storedSessionId;
  const restored = await restoreActiveSession(
    { userId: "", email: runtimeConfig.userProfile.email },
    storedSessionId
  );

  if (!restored) {
    clearActiveSessionId();
    currentSessionId = "";
  }

  return currentSessionId;
}

async function ensureChatSession(user) {
  if (currentSessionId) {
    return currentSessionId;
  }

  if (ensuringSessionPromise) {
    return ensuringSessionPromise;
  }

  ensuringSessionPromise = resolveActiveChatSession(user).finally(() => {
    ensuringSessionPromise = null;
  });

  return ensuringSessionPromise;
}

async function resolveActiveChatSession(user) {
  const storedSessionId = readActiveSessionId();

  if (storedSessionId) {
    currentSessionId = storedSessionId;

    const restored = await restoreActiveSession(user, storedSessionId);
    if (restored) {
      return currentSessionId;
    }

    clearActiveSessionId();
    currentSessionId = "";
  }

  return createChatSession(user);
}

async function createChatSession(user) {
  const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-OneAssist-User-Id": String(user.userId),
    },
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    throw new Error("Chat session could not be created.");
  }

  const payload = await response.json();
  currentSessionId = payload.sessionId || "";

  if (!currentSessionId) {
    throw new Error("Chat session response did not include a session ID.");
  }

  writeActiveSessionId(currentSessionId);
  return currentSessionId;
}

async function restoreActiveSession(user, sessionId) {
  const userEmail = runtimeConfig.userProfile.email || user?.email || "";
  if (!userEmail) {
    return false;
  }

  try {
    const response = await fetch(
      `${API_BASE_URL}/chat/sessions/${encodeURIComponent(sessionId)}`
        + `?user_email=${encodeURIComponent(userEmail)}`,
      {
        headers: user?.userId
          ? { "X-OneAssist-User-Id": String(user.userId) }
          : {},
      }
    );

    if (!response.ok) {
      return false;
    }

    const payload = await response.json();
    const session = payload.session || {};
    const status = String(session.status || "").toUpperCase();
    if (status === "ENDED") {
      return false;
    }

    currentSessionId =
      session.session_uuid ||
      session.uuid ||
      sessionId;
    writeActiveSessionId(currentSessionId);
    restoreMessages(payload.messages || []);
    return true;
  } catch (error) {
    console.warn("Active chat session restore failed:", error);
    return false;
  }
}

function restoreMessages(historyMessages) {
  if (!messages || !Array.isArray(historyMessages)) {
    return;
  }

  const orderedMessages = [...historyMessages].sort((left, right) => {
    const leftDate = Date.parse(left.created_at || left.createdAt || "");
    const rightDate = Date.parse(right.created_at || right.createdAt || "");

    if (!Number.isNaN(leftDate) && !Number.isNaN(rightDate) && leftDate !== rightDate) {
      return leftDate - rightDate;
    }

    return Number(left.id || 0) - Number(right.id || 0);
  });

  orderedMessages.forEach((message) => {
    const rawRole = String(message.role || "").toLowerCase();
    const role = rawRole === "assistant" || rawRole === "bot"
      ? "bot"
      : "user";
    const text =
      message.message_text ||
      message.messageText ||
      message.content ||
      message.message ||
      message.response_text ||
      "";
    const messageId = message.id || message.message_id || message.messageId;

    appendMessage(
      role,
      text,
      message.sources || [],
      {
        enableFeedback: role === "bot" && Boolean(messageId),
        assistantMessageId: role === "bot" ? messageId : undefined,
        userMessageId: role === "user" ? messageId : undefined,
        messageId,
      }
    );
  });
}

function persistResponseSession(payload) {
  const responseSessionId =
    payload.sessionUuid ||
    (
      typeof payload.sessionId === "string"
        ? payload.sessionId
        : ""
    );

  if (responseSessionId) {
    currentSessionId = responseSessionId;
    writeActiveSessionId(responseSessionId);
  } else if (currentSessionId) {
    writeActiveSessionId(currentSessionId);
  }
}

function getActiveSessionStorageKey() {
  const profileEmail = (
    runtimeConfig.userProfile.email ||
    "anonymous"
  ).toLowerCase();

  return `${ACTIVE_SESSION_STORAGE_PREFIX}:${API_BASE_URL}:${profileEmail}`;
}

function readActiveSessionId() {
  try {
    return String(
      window.localStorage.getItem(getActiveSessionStorageKey()) || ""
    ).trim();
  } catch {
    return "";
  }
}

function writeActiveSessionId(sessionId) {
  try {
    window.localStorage.setItem(
      getActiveSessionStorageKey(),
      String(sessionId || "")
    );
  } catch {
    // Local storage can be disabled in embedded browser contexts.
  }
}

function clearActiveSessionId() {
  try {
    window.localStorage.removeItem(getActiveSessionStorageKey());
  } catch {
    // Local storage can be disabled in embedded browser contexts.
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

async function endChatSession() {
  await endCurrentBackendSession();
  closeFeedback();
  resetChatSession();
  setWidgetOpen(false);
  notifyHostClose();
}

async function endCurrentBackendSession() {
  if (!currentUser || !currentSessionId) {
    currentSessionId = "";
    clearActiveSessionId();
    return;
  }

  try {
    await fetch(`${API_BASE_URL}/chat/sessions/${currentSessionId}/end`, {
      method: "POST",
      headers: {
        "X-OneAssist-User-Id": String(currentUser.userId),
      },
    });
  } catch (error) {
    console.error("End chat session error:", error);
  } finally {
    currentSessionId = "";
    clearActiveSessionId();
  }
}

function resetChatSession() {
  if (messages) {
    messages.replaceChildren();
  }

  renderedMessageKeys.clear();

  if (messageInput) {
    messageInput.value = "";
    autoResizeTextarea();
  }

  setComposerState(false);

  if (ENABLE_HISTORY_PANEL) {
    // Reserved for the Phase 1 history panel flag; UI stays disabled by default.
  }
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
