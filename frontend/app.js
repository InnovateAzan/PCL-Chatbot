const DEFAULT_API_BASE_URL = "http://127.0.0.1:8085/api";
const runtimeConfig = getRuntimeConfig();
const API_BASE_URL = runtimeConfig.apiBaseUrl;
const EMBED_MODE = runtimeConfig.embedMode;

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
const closeFeedbackButton = document.getElementById("closeFeedbackButton");
const skipFeedbackButton = document.getElementById("skipFeedbackButton");
const submitFeedbackButton = document.getElementById("submitFeedbackButton");
const feedbackInput = document.getElementById("feedbackInput");
const feedbackChoices = document.querySelectorAll(".feedback-choice");

let selectedRating = "";

document.body.classList.toggle("embed-mode", EMBED_MODE);

appendMessage(
  "bot",
  "Assalam o Alaikum! Welcome to Pakistan Cables. How can I help you today?"
);
setWidgetOpen(true);
checkHealth();

launcherButton.addEventListener("click", () => {
  const willOpen = chatWidget.classList.contains("hidden");
  setWidgetOpen(willOpen);
});

collapseButton.addEventListener("click", () => {
  setWidgetOpen(false);
});

endChatButton.addEventListener("click", () => {
  openFeedback();
});

closeFeedbackButton.addEventListener("click", closeFeedback);
skipFeedbackButton.addEventListener("click", closeFeedback);
feedbackBackdrop.addEventListener("click", closeFeedback);

feedbackChoices.forEach((button) => {
  button.addEventListener("click", () => {
    selectedRating = button.dataset.rating ?? "";
    feedbackChoices.forEach((item) => item.classList.remove("selected"));
    button.classList.add("selected");
  });
});

submitFeedbackButton.addEventListener("click", () => {
  const summary = selectedRating
    ? `Thanks for the ${selectedRating} feedback.`
    : "Thanks for your feedback.";

  const detail = feedbackInput.value.trim();
  appendMessage(
    "bot",
    detail ? `${summary} Your comment has been noted.` : summary
  );
  closeFeedback();
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = messageInput.value.trim();
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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      throw new Error("Chat request failed");
    }

    const payload = await response.json();
    appendMessage("bot", payload.answer, payload.sources ?? [], {
      notice: payload.notice,
      enableFeedback: true,
    });
  } catch (error) {
    appendMessage(
      "bot",
      "The assistant could not reach the backend. Please make sure the API server is running."
    );
  } finally {
    setComposerState(false);
  }
});

messageInput.addEventListener("input", autoResizeTextarea);
messageInput.addEventListener("keydown", handleComposerKeydown);

function getRuntimeConfig() {
  const params = new URLSearchParams(window.location.search);
  const apiBaseCandidate =
    params.get("apiBase") ||
    document.body.dataset.apiBase ||
    window.PCL_GPT_CONFIG?.apiBaseUrl ||
    DEFAULT_API_BASE_URL;

  return {
    apiBaseUrl: normalizeApiBase(apiBaseCandidate),
    embedMode:
      params.get("embed") === "1" || document.body.dataset.embed === "true",
  };
}

function normalizeApiBase(value) {
  const normalized = (value || DEFAULT_API_BASE_URL).trim();
  return normalized.replace(/\/+$/, "");
}

function handleComposerKeydown(event) {
  if (event.key !== "Enter") {
    return;
  }

  if (event.ctrlKey) {
    const start = messageInput.selectionStart;
    const end = messageInput.selectionEnd;
    const value = messageInput.value;

    messageInput.value = `${value.slice(0, start)}\n${value.slice(end)}`;
    messageInput.selectionStart = messageInput.selectionEnd = start + 1;
    autoResizeTextarea();
    return;
  }

  event.preventDefault();
  chatForm.requestSubmit();
}

async function checkHealth() {
  if (window.location.protocol === "file:") {
    statusNote.textContent =
      "This page was opened from a local file. Open http://127.0.0.1:5500 instead so the chat can reach the backend.";
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    if (!response.ok) {
      throw new Error("Health check failed");
    }

    const payload = await response.json();
    statusNote.textContent = payload.gemini_configured
      ? "Live Gemini is configured for richer responses."
      : "Policy fallback mode is active until a Gemini API key is added.";
  } catch (error) {
    statusNote.textContent =
      "Backend is offline. Start the local API to activate the assistant.";
  }
}

function appendMessage(role, text, sources = [], meta = {}) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  const body = document.createElement("p");
  body.className = "message-body";
  body.textContent = text;
  bubble.appendChild(body);

  if (role === "bot" && meta.notice) {
    const note = document.createElement("p");
    note.className = "message-note";
    note.textContent = meta.notice;
    bubble.appendChild(note);
  }

  if (role === "bot" && sources.length > 0) {
    const sourceBlock = document.createElement("div");
    sourceBlock.className = "sources";

    const title = document.createElement("strong");
    title.textContent = "Sources";
    sourceBlock.appendChild(title);

    sources.forEach((source) => {
      const wrapper = document.createElement("div");
      wrapper.className = "source-item";

      const line = document.createElement("p");
      const section = source.section ? `, ${source.section}` : "";
      const page = source.page_number ? `, page ${source.page_number}` : "";
      line.textContent = `${source.document_name}${section}${page}`;
      wrapper.appendChild(line);

      if (source.snippet) {
        const snippet = document.createElement("p");
        snippet.className = "source-snippet";
        snippet.textContent = source.snippet;
        wrapper.appendChild(snippet);
      }

      sourceBlock.appendChild(wrapper);
    });

    bubble.appendChild(sourceBlock);
  }

  article.appendChild(bubble);

  if (role === "bot" && meta.enableFeedback) {
    article.appendChild(createFeedbackBar());
  }

  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function createFeedbackBar() {
  const wrapper = document.createElement("div");
  wrapper.className = "feedback-bar";

  const up = document.createElement("button");
  up.type = "button";
  up.className = "feedback-toggle";
  up.innerHTML = "&#128077;";

  const down = document.createElement("button");
  down.type = "button";
  down.className = "feedback-toggle";
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

function setComposerState(isLoading) {
  messageInput.disabled = isLoading;
  sendButton.disabled = isLoading;
}

function setWidgetOpen(isOpen) {
  chatWidget.classList.toggle("hidden", !isOpen);
  launcherButton.classList.toggle("hidden", isOpen);
  launcherButton.setAttribute("aria-expanded", String(isOpen));

  if (isOpen) {
    messageInput.focus();
  }
}

function openFeedback() {
  feedbackModal.classList.remove("hidden");
  feedbackBackdrop.classList.remove("hidden");
}

function closeFeedback() {
  feedbackModal.classList.add("hidden");
  feedbackBackdrop.classList.add("hidden");
  feedbackInput.value = "";
  selectedRating = "";
  feedbackChoices.forEach((item) => item.classList.remove("selected"));
}

function autoResizeTextarea() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 118)}px`;
}
