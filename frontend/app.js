const DEFAULT_API_BASE_URL = "http://127.0.0.1:8085/api";
const LOCAL_PROFILE_STORAGE_KEY = "oneassist.localProfile";
const ACTIVE_SESSION_STORAGE_PREFIX = "oneassist.activeSessionId";
const API_TOKEN_MESSAGE_TYPE = "onedesk-api-token";
const LEGACY_API_TOKEN_MESSAGE_TYPE = "pcl-gpt:api-token";
const API_TOKEN_REQUEST_MESSAGE_TYPE = "pcl-gpt:api-token-request";

window.ONEASSIST_BUILD_VERSION = "2026-08-07-v1";

const runtimeConfig = getRuntimeConfig();
const API_BASE_URL = runtimeConfig.apiBaseUrl;
const EMBED_MODE = runtimeConfig.embedMode;
const HOSTED_MODE = runtimeConfig.hostedMode;
const DEFAULT_OPEN = runtimeConfig.defaultOpen;
const ENABLE_HISTORY_PANEL = runtimeConfig.enableHistoryPanel;
const ENABLE_CLIENT_DEBUG_LOGS = Boolean(runtimeConfig.enableClientDebugLogs);
const LOG_USER_MESSAGES = Boolean(runtimeConfig.logUserMessages);

const oneAssistLogger = {
  info(event, fields = {}) {
    if (ENABLE_CLIENT_DEBUG_LOGS) {
      console.info(
        "[OneAssist Frontend]",
        event,
        sanitizeClientLogFields(fields)
      );
    }
  },

  warn(event, fields = {}) {
    console.warn(
      "[OneAssist Frontend]",
      event,
      sanitizeClientLogFields(fields)
    );
  },

  error(event, fields = {}) {
    console.error(
      "[OneAssist Frontend]",
      event,
      sanitizeClientLogFields(fields)
    );
  },
};

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

let backendReadyPromise = null;

let apiAccessToken = "";
let apiAccessTokenExpiresAt = 0;
let apiAccessTokenPromise = null;
let apiAccessTokenError = "";

oneAssistLogger.info("OneDesk Assistant frontend version:", {
  version: window.ONEASSIST_BUILD_VERSION,
  apiBaseUrl: API_BASE_URL,
  origin: window.location.origin,
  embedMode: EMBED_MODE,
  hostedMode: HOSTED_MODE,
  enableClientDebugLogs: ENABLE_CLIENT_DEBUG_LOGS,
});

document.body.classList.toggle("embed-mode", EMBED_MODE);
document.body.classList.toggle("hosted-mode", HOSTED_MODE);

document.documentElement.classList.toggle(
  "embed-mode",
  EMBED_MODE
);

document.documentElement.classList.toggle(
  "hosted-mode",
  HOSTED_MODE
);

if (HOSTED_MODE) {
  window.addEventListener(
    "resize",
    scheduleHostLayoutUpdate
  );
}

setWidgetOpen(DEFAULT_OPEN);

updateFeedbackSubmitState();

ensureBackendReady()
  .then(() => prepareActiveSession())
  .catch((error) => {
    oneAssistLogger.error(
      "active_session_initialization_failed",
      {
        errorType: error?.name,
        message: error?.message,
      }
    );
  });

launcherButton?.addEventListener("click", () => {
  const willOpen =
    chatWidget?.classList.contains("hidden") ?? true;

  setWidgetOpen(willOpen);
});

collapseButton?.addEventListener("click", () => {
  setWidgetOpen(false);
  notifyHostClose();
});

endChatButton?.addEventListener("click", () => {
  openFeedback();
});

closeFeedbackButton?.addEventListener(
  "click",
  closeFeedback
);

skipFeedbackButton?.addEventListener(
  "click",
  endChatSession
);

feedbackBackdrop?.addEventListener(
  "click",
  closeFeedback
);

feedbackChoices.forEach((button) => {
  button.addEventListener("click", () => {
    selectedRating =
      button.dataset.rating ?? "";

    feedbackChoices.forEach((item) => {
      item.classList.remove("selected");
    });

    button.classList.add("selected");

    updateFeedbackSubmitState();
  });
});

submitFeedbackButton?.addEventListener(
  "click",
  () => {
    if (!selectedRating) {
      return;
    }

    endChatSession();
  }
);

chatForm?.addEventListener(
  "submit",
  async (event) => {
    event.preventDefault();

    const message =
      messageInput?.value.trim() ?? "";

    if (!message) {
      return;
    }

    appendMessage(
      "user",
      message
    );

    messageInput.value = "";

    autoResizeTextarea();
    setComposerState(true);
    showTypingIndicator();

    try {
      await ensureBackendReady();

      let user = null;

      let sessionId =
        currentSessionId || "";

      let historyEnabled = false;

      try {
        user =
          await initializeCurrentUser();

        sessionId =
          await ensureChatSession(user);

        historyEnabled =
          Boolean(
            user?.userId &&
            sessionId
          );
      } catch (historyError) {
        if (
          isAuthenticationError(
            historyError
          )
        ) {
          throw historyError;
        }

        oneAssistLogger.warn(
          "chat_history_session_unavailable",
          {
            errorType:
              historyError?.name,

            message:
              historyError?.message,
          }
        );
      }

      const chatEndpoint =
        `${API_BASE_URL}/chat`;

      oneAssistLogger.info(
        "chat_request_started",
        {
          apiUrl: API_BASE_URL,
          endpoint: "/chat",
          url: chatEndpoint,
          version:
            window.ONEASSIST_BUILD_VERSION,
          messageLength:
            message.length,

          ...(LOG_USER_MESSAGES
            ? {
                userMessage:
                  message,
              }
            : {}),
        }
      );

      const response =
        await apiRequest(
          "/chat",
          {
            method: "POST",

            headers: {
              "Content-Type":
                "application/json",

              ...(historyEnabled
                ? {
                    "X-OneAssist-User-Id":
                      String(
                        user.userId
                      ),
                  }
                : {}),
            },

            body: JSON.stringify({
              message,

              ...(historyEnabled
                ? {
                    sessionId,
                  }
                : {}),

              ...(currentSessionId
                ? {
                    sessionUuid:
                      currentSessionId,
                  }
                : {}),

              userEmail:
                runtimeConfig
                  .userProfile
                  .email,

              displayName:
                runtimeConfig
                  .userProfile
                  .displayName,

              preferredName:
                runtimeConfig
                  .userProfile
                  .preferredName,

              department:
                runtimeConfig
                  .userProfile
                  .department,
            }),
          }
        );

      if (!response.ok) {
        throw await buildApiResponseError(
          response,
          "/chat"
        );
      }

      oneAssistLogger.info(
        "chat_request_completed",
        {
          endpoint: "/chat",
          status:
            response.status,
        }
      );

      const payload =
        await response.json();

      persistResponseSession(
        payload
      );

      removeTypingIndicator();

      appendMessage(
        "bot",

        payload.answer ||
          "No response was received.",

        payload.sources ?? [],

        {
          notice:
            payload.notice,

          enableFeedback:
            Boolean(
              payload.assistantMessageId
            ),

          assistantMessageId:
            payload.assistantMessageId,

          messageId:
            payload.assistantMessageId,
        }
      );
    } catch (error) {
      oneAssistLogger.error(
        "chat_request_failed",
        {
          endpoint:
            error?.endpoint ||
            "/chat",

          statusCode:
            error?.statusCode,

          backendDetail:
            error?.backendDetail,
        }
      );

      removeTypingIndicator();

      appendMessage(
        "bot",
        formatApiErrorMessage(error)
      );
    } finally {
      removeTypingIndicator();

      setComposerState(false);

      messageInput?.focus();
    }
  }
);

window.addEventListener(
  "message",
  (event) => {
    if (
      runtimeConfig.parentOrigin &&
      event.origin !==
        runtimeConfig.parentOrigin
    ) {
      oneAssistLogger.warn(
        "token_message_origin_rejected",
        {
          origin:
            event.origin,

          expectedOrigin:
            runtimeConfig.parentOrigin,
        }
      );

      return;
    }

    const payload =
      event.data || {};

    if (
      !isApiTokenMessage(payload)
    ) {
      return;
    }

    apiAccessToken =
      normalizeApiToken(
        payload.accessToken
      );

    apiAccessTokenError =
      apiAccessToken
        ? ""
        : String(
            payload.errorCode ||
              "token_unavailable"
          );

    oneAssistLogger.info(
      "token_message_received",
      {
        origin:
          event.origin,

        tokenPresent:
          Boolean(
            apiAccessToken
          ),

        tokenLength:
          String(
            payload.accessToken ||
              ""
          ).length,

        jwtSegmentCount:
          jwtSegmentCount(
            payload.accessToken
          ),
      }
    );

    const expiresIn =
      Number(
        payload.expiresIn ||
        300
      );

    apiAccessTokenExpiresAt =
      Date.now() +
      Math.max(
        30,
        expiresIn - 30
      ) *
        1000;
  }
);

messageInput?.addEventListener(
  "input",
  autoResizeTextarea
);

messageInput?.addEventListener(
  "keydown",
  handleComposerKeydown
);

function ensureBackendReady() {
  if (backendReadyPromise) {
    return backendReadyPromise;
  }

  const healthEndpoint =
    buildApiUrl("/health");

  oneAssistLogger.info(
    "backend_health_check_started",
    {
      apiUrl:
        API_BASE_URL,

      endpoint:
        "/health",

      url:
        healthEndpoint,

      version:
        window.ONEASSIST_BUILD_VERSION,
    }
  );

  backendReadyPromise =
    apiRequest(
      "/health",
      {
        method: "GET",

        headers: {
          "Accept":
            "application/json",
        },
      }
    )
      .then(
        async (response) => {
          oneAssistLogger.info(
            "backend_health_check_completed",
            {
              apiUrl:
                API_BASE_URL,

              endpoint:
                "/health",

              status:
                response.status,

              version:
                window.ONEASSIST_BUILD_VERSION,
            }
          );

          if (!response.ok) {
            throw await buildApiResponseError(
              response,
              "/health"
            );
          }

          return true;
        }
      )
      .catch((error) => {
        backendReadyPromise = null;

        throw error;
      });

  return backendReadyPromise;
}

async function apiRequest(
  path,
  options = {},
  requestOptions = {}
) {
  return performApiRequest(
    buildApiUrl(path),
    options,
    requestOptions.requireAuth !== false &&
      isEmbeddedSharePointMode()
  );
}

async function performApiRequest(
  url,
  options = {},
  requiresAuth = false,
  retryOnUnauthorized = true
) {
  const headers =
    buildTransportHeaders({
      ...(options.headers ||
        {}),

      ...(requiresAuth
        ? await getApiAuthorizationHeader()
        : {}),
    });

  let response;

  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (error) {
    if (
      requiresAuth &&
      isEmbeddedSharePointMode() &&
      !isUsableJwt(apiAccessToken)
    ) {
      throw createApiTokenError(
        apiAccessTokenError ||
          "token_unavailable"
      );
    }

    throw error;
  }

  if (
    response.status !== 401 ||
    !retryOnUnauthorized
  ) {
    return response;
  }

  clearApiAccessToken();

  const retryHeaders =
    buildTransportHeaders({
      ...(options.headers ||
        {}),

      ...(requiresAuth
        ? await getApiAuthorizationHeader({
            forceRefresh: true,
          })
        : {}),
    });

  return fetch(
    url,
    {
      ...options,
      headers:
        retryHeaders,
    }
  );
}

function buildApiUrl(
  path
) {
  return `${API_BASE_URL}${path}`;
}

function buildTransportHeaders(
  headers = {}
) {
  return (
    window.ONEASSIST_BUILD_TRANSPORT_HEADERS?.(
      headers,
      API_BASE_URL
    ) || {
      ...(headers || {}),
    }
  );
}

function isEmbeddedSharePointMode() {
  return (
    Boolean(
      runtimeConfig.parentOrigin
    ) &&
    window.parent !== window
  );
}

async function getApiAuthorizationHeader(
  options = {}
) {
  const token =
    await getApiAccessToken(
      options
    );

  if (!isUsableJwt(token)) {
    oneAssistLogger.warn(
      "authorization_header_skipped",
      {
        tokenPresent:
          Boolean(token),

        tokenLength:
          String(
            token || ""
          ).length,

        jwtSegmentCount:
          jwtSegmentCount(
            token
          ),

        tokenError:
          apiAccessTokenError ||
          "",
      }
    );

    if (
      runtimeConfig.parentOrigin &&
      window.parent !== window
    ) {
      throw createApiTokenError(
        apiAccessTokenError ||
          "token_unavailable"
      );
    }

    return {};
  }

  return {
    "Authorization":
      `Bearer ${token}`,
  };
}

async function getApiAccessToken(
  options = {}
) {
  if (options.forceRefresh) {
    oneAssistLogger.info(
      "token_refresh_requested"
    );

    clearApiAccessToken();
  }

  if (
    isUsableJwt(
      apiAccessToken
    ) &&
    Date.now() <
      apiAccessTokenExpiresAt
  ) {
    return apiAccessToken;
  }

  if (
    !runtimeConfig.parentOrigin ||
    window.parent === window
  ) {
    return "";
  }

  if (apiAccessTokenPromise) {
    return apiAccessTokenPromise;
  }

  apiAccessTokenPromise =
    new Promise(
      (resolve) => {
        const timeout =
          window.setTimeout(
            () => {
              window.removeEventListener(
                "message",
                handler
              );

              apiAccessTokenError =
                "token_request_timeout";

              resolve("");
            },
            5000
          );

        function handler(
          event
        ) {
          if (
            event.origin !==
            runtimeConfig.parentOrigin
          ) {
            return;
          }

          const payload =
            event.data || {};

          if (
            !isApiTokenMessage(
              payload
            )
          ) {
            return;
          }

          window.clearTimeout(
            timeout
          );

          window.removeEventListener(
            "message",
            handler
          );

          apiAccessToken =
            normalizeApiToken(
              payload.accessToken
            );

          apiAccessTokenError =
            apiAccessToken
              ? ""
              : String(
                  payload.errorCode ||
                    "token_unavailable"
                );

          oneAssistLogger.info(
            "token_reacquired",
            {
              tokenPresent:
                Boolean(
                  apiAccessToken
                ),

              tokenLength:
                String(
                  payload.accessToken ||
                    ""
                ).length,

              jwtSegmentCount:
                jwtSegmentCount(
                  payload.accessToken
                ),
            }
          );

          const expiresIn =
            Number(
              payload.expiresIn ||
              300
            );

          apiAccessTokenExpiresAt =
            Date.now() +
            Math.max(
              30,
              expiresIn - 30
            ) *
              1000;

          resolve(
            apiAccessToken
          );
        }

        window.addEventListener(
          "message",
          handler
        );

        window.parent.postMessage(
          {
            type:
              API_TOKEN_REQUEST_MESSAGE_TYPE,
          },
          runtimeConfig.parentOrigin
        );
      }
    ).finally(() => {
      apiAccessTokenPromise =
        null;
    });

  return apiAccessTokenPromise;
}

function clearApiAccessToken() {
  apiAccessToken = "";
  apiAccessTokenExpiresAt = 0;
  apiAccessTokenError = "";
}

function createApiTokenError(
  code
) {
  const error =
    new Error(
      code ===
        "token_request_timeout"
        ? "Microsoft sign-in did not respond. Refresh the OneDesk page and try again."
        : "Microsoft sign-in could not obtain access to the OneDesk Chat Assistant API. Verify the access_as_user permission is approved, then refresh the OneDesk page."
    );

  error.code = code;

  error.endpoint =
    "Microsoft sign-in";

  return error;
}

function sanitizeClientLogFields(
  fields
) {
  const blocked = [
    "accessToken",
    "refreshToken",
    "authorization",
    "password",
    "secret",
    "apiKey",
    "cookie",
  ];

  const safeTokenDiagnostics =
    new Set([
      "tokenPresent",
      "tokenLength",
      "jwtSegmentCount",
    ]);

  const output = {};

  Object.keys(
    fields || {}
  ).forEach(
    (key) => {
      if (
        safeTokenDiagnostics.has(
          key
        )
      ) {
        output[key] =
          fields[key];
      } else if (
        blocked.some(
          (item) =>
            key
              .toLowerCase()
              .includes(
                item.toLowerCase()
              )
        )
      ) {
        output[key] =
          "[REDACTED]";
      } else {
        output[key] =
          fields[key];
      }
    }
  );

  return output;
}

function isApiTokenMessage(
  payload
) {
  return (
    payload?.type ===
      API_TOKEN_MESSAGE_TYPE ||
    payload?.type ===
      LEGACY_API_TOKEN_MESSAGE_TYPE
  );
}

function normalizeApiToken(
  value
) {
  const token =
    String(
      value || ""
    ).trim();

  if (
    !isUsableJwt(token)
  ) {
    return "";
  }

  return token;
}

function isUsableJwt(
  token
) {
  const value =
    String(
      token || ""
    ).trim();

  return (
    value.length >
      100 &&
    jwtSegmentCount(
      value
    ) === 3
  );
}

function jwtSegmentCount(
  token
) {
  const value =
    String(
      token || ""
    ).trim();

  return value
    ? value.split(".").length
    : 0;
}

async function buildApiResponseError(
  response,
  endpoint
) {
  let backendDetail = "";
  let backendBody = "";

  try {
    const payload =
      await response
        .clone()
        .json();

    if (payload?.detail) {
      backendDetail =
        String(
          payload.detail
        );
    }
  } catch {
    try {
      backendBody =
        await response.text();
    } catch {
      backendBody = "";
    }
  }

  const error =
    new Error(
      backendDetail ||
        backendBody ||
        `Backend request failed with HTTP ${response.status}.`
    );

  error.apiUrl =
    API_BASE_URL;

  error.endpoint =
    endpoint;

  error.statusCode =
    response.status;

  error.backendDetail =
    backendDetail ||
    backendBody;

  return error;
}

function formatApiErrorMessage(
  error
) {
  if (
    String(
      error?.code || ""
    ).startsWith(
      "token_"
    )
  ) {
    return error.message;
  }

  const statusCode =
    error?.statusCode;

  const endpoint =
    error?.endpoint ||
    "/chat";

  const backendDetail =
    String(
      error?.backendDetail ||
        error?.message ||
        ""
    ).trim();

  if (statusCode) {
    return (
      "The assistant could not complete the backend request.\n\n" +
      `API URL: ${API_BASE_URL}\n` +
      `Endpoint: ${endpoint}\n` +
      `Status: ${statusCode}\n` +
      `Backend detail: ${
        backendDetail ||
        "No detail returned."
      }`
    );
  }

  return (
    "The assistant could not reach the backend.\n\n" +
    `API URL: ${API_BASE_URL}\n` +
    `Endpoint: ${endpoint}\n` +
    "Status: network error\n" +
    `Backend detail: ${
      backendDetail ||
      "No response received."
    }`
  );
}

function isAuthenticationError(
  error
) {
  return (
    String(
      error?.code || ""
    ).startsWith(
      "token_"
    ) ||
    Number(
      error?.statusCode || 0
    ) === 401
  );
}

function appendMessage(
  role,
  text,
  sources = [],
  meta = {}
) {
  if (!messages) {
    return;
  }

  const messageKey =
    buildRenderedMessageKey(
      role,
      meta
    );

  if (
    messageKey &&
    renderedMessageKeys.has(
      messageKey
    )
  ) {
    return;
  }

  const article =
    document.createElement(
      "article"
    );

  article.className =
    `message ${role}`;

  if (messageKey) {
    article.dataset.messageKey =
      messageKey;

    renderedMessageKeys.add(
      messageKey
    );
  }

  const bubble =
    document.createElement(
      "div"
    );

  bubble.className =
    "message-bubble";

  const body =
    document.createElement(
      "div"
    );

  body.className =
    "message-body";

  if (role === "bot") {
    body.appendChild(
      formatAssistantAnswer(
        text
      )
    );
  } else {
    body.textContent =
      String(
        text || ""
      );
  }

  bubble.appendChild(body);

  const noticeElement =
    buildNoticeElement(
      sources,
      meta.notice
    );

  if (
    role === "bot" &&
    noticeElement
  ) {
    bubble.appendChild(
      noticeElement
    );
  }

  article.appendChild(
    bubble
  );

  if (
    role === "bot" &&
    meta.enableFeedback
  ) {
    article.appendChild(
      createFeedbackBar(
        meta.assistantMessageId
      )
    );
  }

  messages.appendChild(
    article
  );

  messages.scrollTop =
    messages.scrollHeight;
}

function showTypingIndicator() {
  if (
    !messages ||
    typingIndicatorElement
  ) {
    return;
  }

  const article =
    document.createElement(
      "article"
    );

  article.className =
    "message bot typing-indicator-message";

  article.setAttribute(
    "aria-live",
    "polite"
  );

  const bubble =
    document.createElement(
      "div"
    );

  bubble.className =
    "message-bubble typing-indicator-bubble";

  const dots =
    document.createElement(
      "div"
    );

  dots.className =
    "typing-dots";

  dots.setAttribute(
    "aria-label",
    "Assistant is typing"
  );

  for (
    let index = 0;
    index < 3;
    index += 1
  ) {
    const dot =
      document.createElement(
        "span"
      );

    dot.className =
      "typing-dot";

    dots.appendChild(dot);
  }

  bubble.appendChild(dots);
  article.appendChild(bubble);
  messages.appendChild(article);

  typingIndicatorElement =
    article;

  messages.scrollTop =
    messages.scrollHeight;
}

function removeTypingIndicator() {
  if (
    !typingIndicatorElement
  ) {
    return;
  }

  typingIndicatorElement.remove();

  typingIndicatorElement =
    null;
}

function buildRenderedMessageKey(
  role,
  meta = {}
) {
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

function formatAssistantAnswer(
  answer
) {
  const container =
    document.createElement(
      "div"
    );

  container.className =
    "formatted-answer";

  const normalizedAnswer =
    normalizeAssistantAnswer(
      answer
    );

  const lines =
    normalizedAnswer
      .split(/\r?\n/)
      .map(
        (line) =>
          line.trim()
      );

  let bulletList = null;

  function closeBulletList() {
    bulletList = null;
  }

  function getBulletList() {
    if (bulletList) {
      return bulletList;
    }

    bulletList =
      document.createElement(
        "ul"
      );

    bulletList.className =
      "answer-bullet-list";

    container.appendChild(
      bulletList
    );

    return bulletList;
  }

  for (
    const rawLine
    of lines
  ) {
    if (!rawLine) {
      closeBulletList();
      continue;
    }

    const sectionMatch =
      rawLine.match(
        /^\[\s*SECTION\s*\](.*?)\[\s*\/\s*SECTION\s*\]$/i
      );

    if (sectionMatch) {
      closeBulletList();

      const heading =
        document.createElement(
          "h4"
        );

      heading.className =
        "answer-section-heading";

      heading.textContent =
        sectionMatch[1].trim();

      container.appendChild(
        heading
      );

      continue;
    }

    const bulletMatch =
      rawLine.match(
        /^\[\s*BULLET\s*\](.*?)\[\s*\/\s*BULLET\s*\]$/i
      );

    if (bulletMatch) {
      const list =
        getBulletList();

      const item =
        document.createElement(
          "li"
        );

      item.textContent =
        bulletMatch[1].trim();

      list.appendChild(
        item
      );

      continue;
    }

    if (
      rawLine.startsWith(
        "• "
      ) ||
      rawLine.startsWith(
        "- "
      ) ||
      rawLine.startsWith(
        "* "
      )
    ) {
      const list =
        getBulletList();

      const item =
        document.createElement(
          "li"
        );

      item.textContent =
        rawLine
          .slice(2)
          .trim();

      list.appendChild(
        item
      );

      continue;
    }

    closeBulletList();

    const paragraph =
      document.createElement(
        "p"
      );

    paragraph.className =
      "answer-paragraph";

    paragraph.textContent =
      rawLine;

    container.appendChild(
      paragraph
    );
  }

  if (
    !container.hasChildNodes()
  ) {
    const paragraph =
      document.createElement(
        "p"
      );

    paragraph.className =
      "answer-paragraph";

    paragraph.textContent =
      String(
        answer || ""
      );

    container.appendChild(
      paragraph
    );
  }

  return container;
}

function normalizeAssistantAnswer(
  answer
) {
  let text =
    String(
      answer || ""
    )
      .replace(
        /\r\n/g,
        "\n"
      )
      .replace(
        /\r/g,
        "\n"
      );

  text =
    text.replace(
      /^\s*#{1,6}\s*/gm,
      ""
    );

  text =
    text
      .replace(
        /\*\*(.*?)\*\*/g,
        "$1"
      )
      .replace(
        /__(.*?)__/g,
        "$1"
      );

  text =
    text
      .replace(
        /\[\s*section\s*\]/gi,
        "[SECTION]"
      )
      .replace(
        /\[\s*\/\s*section\s*\]/gi,
        "[/SECTION]"
      );

  text =
    text
      .replace(
        /\[\s*bullet\s*\]/gi,
        "[BULLET]"
      )
      .replace(
        /\[\s*\/\s*bullet\s*\]/gi,
        "[/BULLET]"
      );

  text =
    text
      .replace(
        /\s*(\[SECTION\])/gi,
        "\n$1"
      )
      .replace(
        /(\[\/SECTION\])\s*/gi,
        "$1\n"
      );

  text =
    text
      .replace(
        /\s*(\[BULLET\])/gi,
        "\n$1"
      )
      .replace(
        /(\[\/BULLET\])\s*/gi,
        "$1\n"
      );

  text =
    text.replace(
      /\s+•\s+/g,
      "\n• "
    );

  text =
    text.replace(
      /^\s*[-*]\s+(.+)$/gm,
      "[BULLET]$1[/BULLET]"
    );

  text =
    text.replace(
      /^\s*•\s+(.+)$/gm,
      "[BULLET]$1[/BULLET]"
    );

  text =
    text.replace(
      /\[BULLET\]([^\n]*?)(?=\n|$)/gi,
      (
        fullMatch,
        content
      ) => {
        if (
          fullMatch.includes(
            "[/BULLET]"
          )
        ) {
          return fullMatch;
        }

        return (
          `[BULLET]${
            content.trim()
          }[/BULLET]`
        );
      }
    );

  text =
    text.replace(
      /\[SECTION\]([^\n]*?)(?=\n|$)/gi,
      (
        fullMatch,
        content
      ) => {
        if (
          fullMatch.includes(
            "[/SECTION]"
          )
        ) {
          return fullMatch;
        }

        return (
          `[SECTION]${
            content.trim()
          }[/SECTION]`
        );
      }
    );

  text =
    text.replace(
      /\n{3,}/g,
      "\n\n"
    );

  return text.trim();
}

function formatSourceLabel(
  source
) {
  const rawName =
    String(
      source?.display_title ||
      source?.displayTitle ||
      source?.title ||
      source?.document_name ||
      source?.documentName ||
      "Unknown policy"
    );

  const policyName =
    rawName
      .replace(
        /\.[^.]+$/i,
        ""
      )
      .replace(
        /\s+/g,
        " "
      )
      .trim();

  const pages =
    Array.isArray(
      source?.pages
    )
      ? source.pages
          .map(
            (page) =>
              Number(page)
          )
          .filter(
            (page) =>
              Number.isInteger(
                page
              ) &&
              page > 0
          )
      : [];

  const uniquePages =
    [
      ...new Set(
        pages
      ),
    ].sort(
      (a, b) =>
        a - b
    );

  const pageNumber =
    source?.page ??
    source?.page_number ??
    source?.pageNumber;

  const pageLabel =
    uniquePages.length >
    1
      ? `Pages ${uniquePages.join(
          ", "
        )}`
      : uniquePages.length ===
          1
        ? `Page ${uniquePages[0]}`
        : pageNumber
          ? `Page ${pageNumber}`
          : "Page unavailable";

  return (
    `${policyName} — ${pageLabel}`
  );
}

function buildNoticeElement(
  sources,
  fallbackNotice
) {
  if (
    Array.isArray(
      sources
    ) &&
    sources.length > 0
  ) {
    const uniqueSources =
      [];

    const seen =
      new Set();

    sources.forEach(
      (source) => {
        const label =
          formatSourceLabel(
            source
          );

        const rawName =
          String(
            source?.document_number ||
            source?.documentNumber ||
            source?.display_title ||
            source?.displayTitle ||
            source?.title ||
            source?.document_name ||
            source?.documentName ||
            "Unknown policy"
          ).toLowerCase();

        const key =
          rawName;

        if (
          label &&
          !seen.has(key)
        ) {
          seen.add(key);
          uniqueSources.push(
            label
          );
        }
      }
    );

    if (
      uniqueSources.length >
      0
    ) {
      const wrapper =
        document.createElement(
          "div"
        );

      wrapper.className =
        "sources";

      const title =
        document.createElement(
          "div"
        );

      title.className =
        "sources-title";

      title.textContent =
        "Sources:";

      wrapper.appendChild(
        title
      );

      const list =
        document.createElement(
          "ul"
        );

      list.className =
        "sources-list";

      uniqueSources.forEach(
        (label) => {
          const item =
            document.createElement(
              "li"
            );

          item.className =
            "source-item";

          item.textContent =
            label;

          list.appendChild(
            item
          );
        }
      );

      wrapper.appendChild(
        list
      );

      return wrapper;
    }
  }

  if (fallbackNotice) {
    const note =
      document.createElement(
        "p"
      );

    note.className =
      "message-note";

    note.textContent =
      sanitizeDisplayedNotice(
        fallbackNotice
      );

    return note;
  }

  return null;
}

function sanitizeDisplayedNotice(
  notice
) {
  const nonPolicyPhrase =
    new RegExp(
      String.raw`\s*;?\s*${
        [
          "not from PCL",
          "policy",
        ].join(" ")
      }\.?`,
      "gi"
    );

  return String(
    notice || ""
  )
    .replace(
      nonPolicyPhrase,
      ""
    )
    .replace(
      /\s{2,}/g,
      " "
    )
    .trim();
}

function createFeedbackBar(
  assistantMessageId
) {
  const wrapper =
    document.createElement(
      "div"
    );

  wrapper.className =
    "feedback-bar";

  const up =
    document.createElement(
      "button"
    );

  up.type = "button";

  up.className =
    "feedback-toggle";

  up.setAttribute(
    "aria-label",
    "Helpful response"
  );

  up.innerHTML =
    "&#128077;";

  const down =
    document.createElement(
      "button"
    );

  down.type = "button";

  down.className =
    "feedback-toggle";

  down.setAttribute(
    "aria-label",
    "Unhelpful response"
  );

  down.innerHTML =
    "&#128078;";

  up.addEventListener(
    "click",
    async () => {
      up.classList.add(
        "selected"
      );

      down.classList.remove(
        "selected"
      );

      await submitMessageFeedback(
        assistantMessageId,
        5,
        "HELPFUL",
        wrapper
      );
    }
  );

  down.addEventListener(
    "click",
    async () => {
      down.classList.add(
        "selected"
      );

      up.classList.remove(
        "selected"
      );

      await submitMessageFeedback(
        assistantMessageId,
        1,
        "NOT_HELPFUL",
        wrapper
      );
    }
  );

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
  if (
    !assistantMessageId ||
    !currentUser
  ) {
    return;
  }

  wrapper.classList.remove(
    "error"
  );

  wrapper.classList.add(
    "saving"
  );

  try {
    const response =
      await apiRequest(
        `/messages/${assistantMessageId}/feedback`,
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",

            "X-OneAssist-User-Id":
              String(
                currentUser.userId
              ),
          },

          body:
            JSON.stringify({
              rating,
              feedbackType,
            }),
        }
      );

    if (!response.ok) {
      throw new Error(
        "Feedback could not be saved."
      );
    }

    wrapper.classList.add(
      "saved"
    );
  } catch (error) {
    oneAssistLogger.error(
      "feedback_save_failed",
      {
        errorType:
          error?.name,

        message:
          error?.message,
      }
    );

    wrapper.classList.add(
      "error"
    );
  } finally {
    wrapper.classList.remove(
      "saving"
    );
  }
}

function scheduleHostLayoutUpdate() {
  if (!HOSTED_MODE) {
    return;
  }

  window.requestAnimationFrame(
    () => {
      notifyHostLayout();
    }
  );
}

function notifyHostLayout() {
  if (
    !HOSTED_MODE ||
    window.parent === window
  ) {
    return;
  }

  const isOpen =
    !(
      chatWidget
        ?.classList
        .contains(
          "hidden"
        ) ??
      true
    );

  const activeElement =
    isOpen
      ? chatWidget
      : launcherButton;

  const bounds =
    activeElement
      ?.getBoundingClientRect();

  if (!bounds) {
    return;
  }

  window.parent.postMessage(
    {
      type:
        "pcl-gpt:layout",

      isOpen,

      width:
        Math.ceil(
          bounds.width
        ),

      height:
        Math.ceil(
          bounds.height
        ),
    },

    runtimeConfig.parentOrigin ||
      "*"
  );
}

function notifyHostClose() {
  if (
    window.parent === window
  ) {
    return;
  }

  window.parent.postMessage(
    {
      type:
        "pcl-gpt:close",
    },

    runtimeConfig.parentOrigin ||
      "*"
  );
}

function getRuntimeConfig() {
  const params =
    new URLSearchParams(
      window.location.search
    );

  const surface =
    params.get(
      "surface"
    ) ||
    document.body.dataset.surface ||
    "";

  const hostedMode =
    surface
      .toLowerCase() ===
    "sharepoint";

  const embedMode =
    params.get(
      "embed"
    ) === "1" ||
    (
      !hostedMode &&
      document.body.dataset.embed ===
        "true"
    );

  const explicitOpen =
    parseBooleanFlag(
      params.get(
        "open"
      ) ||
      document.body.dataset.open
    );

  const apiBaseCandidate =
    params.get(
      "apiBase"
    ) ||
    document.body.dataset.apiBase ||
    window.PCL_GPT_CONFIG
      ?.apiBaseUrl ||
    DEFAULT_API_BASE_URL;

  return {
    apiBaseUrl:
      normalizeApiBase(
        apiBaseCandidate
      ),

    embedMode,

    hostedMode,

    enableHistoryPanel:
      parseBooleanFlag(
        params.get(
          "enableHistory"
        ) ||
        document.body.dataset
          .enableHistory ||
        window.PCL_GPT_CONFIG
          ?.enableHistory
      ) === true,

    userProfile:
      buildUserProfile(
        params
      ),

    parentOrigin:
      String(
        params.get(
          "parentOrigin"
        ) ||
        document.body.dataset
          .parentOrigin ||
        ""
      ).trim(),

    enableClientDebugLogs:
      parseBooleanFlag(
        params.get(
          "enableClientDebugLogs"
        ) ||
        document.body.dataset
          .enableClientDebugLogs ||
        window.PCL_GPT_CONFIG
          ?.enableClientDebugLogs
      ) === true,

    logUserMessages:
      parseBooleanFlag(
        params.get(
          "logUserMessages"
        ) ||
        document.body.dataset
          .logUserMessages ||
        window.PCL_GPT_CONFIG
          ?.logUserMessages
      ) === true,

    defaultOpen:
      resolveDefaultOpen(
        explicitOpen,
        embedMode,
        hostedMode
      ),
  };
}

function buildUserProfile(
  params
) {
  const configProfile =
    window.PCL_GPT_CONFIG
      ?.userProfile || {};

  const savedProfile =
    readLocalProfile();

  const profile = {
    displayName:
      params.get(
        "displayName"
      ) ||
      configProfile.displayName ||
      savedProfile.displayName ||
      "Local OneAssist User",

    preferredName:
      params.get(
        "preferredName"
      ) ||
      configProfile.preferredName ||
      savedProfile.preferredName ||
      "",

    email:
      params.get(
        "email"
      ) ||
      configProfile.email ||
      savedProfile.email ||
      "local.oneassist.user@example.com",

    employeeId:
      params.get(
        "employeeId"
      ) ||
      configProfile.employeeId ||
      savedProfile.employeeId ||
      "",

    department:
      params.get(
        "department"
      ) ||
      configProfile.department ||
      savedProfile.department ||
      "",

    jobTitle:
      params.get(
        "jobTitle"
      ) ||
      configProfile.jobTitle ||
      savedProfile.jobTitle ||
      "",

    entraObjectId:
      params.get(
        "entraObjectId"
      ) ||
      configProfile.entraObjectId ||
      savedProfile.entraObjectId ||
      "",
  };

  writeLocalProfile(
    profile
  );

  return profile;
}

function readLocalProfile() {
  try {
    return JSON.parse(
      window.localStorage.getItem(
        LOCAL_PROFILE_STORAGE_KEY
      ) || "{}"
    );
  } catch {
    return {};
  }
}

function writeLocalProfile(
  profile
) {
  try {
    window.localStorage.setItem(
      LOCAL_PROFILE_STORAGE_KEY,

      JSON.stringify(
        profile
      )
    );
  } catch {
    // Local storage can be disabled.
  }
}

function normalizeApiBase(
  value
) {
  const normalized =
    String(
      value ||
      DEFAULT_API_BASE_URL
    ).trim();

  return normalized.replace(
    /\/+$/,
    ""
  );
}

function parseBooleanFlag(
  value
) {
  if (value == null) {
    return undefined;
  }

  const normalized =
    String(value)
      .trim()
      .toLowerCase();

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
  if (
    typeof explicitOpen ===
    "boolean"
  ) {
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

function handleComposerKeydown(
  event
) {
  if (
    event.key !== "Enter"
  ) {
    return;
  }

  if (event.ctrlKey) {
    const start =
      messageInput.selectionStart;

    const end =
      messageInput.selectionEnd;

    const value =
      messageInput.value;

    messageInput.value =
      `${value.slice(
        0,
        start
      )}\n${value.slice(
        end
      )}`;

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

  if (
    initializingUserPromise
  ) {
    return initializingUserPromise;
  }

  initializingUserPromise =
    apiRequest(
      "/users/initialize",
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json",
        },

        body:
          JSON.stringify(
            runtimeConfig.userProfile
          ),
      }
    )
      .then(
        async (response) => {
          if (!response.ok) {
            throw new Error(
              "User initialization failed."
            );
          }

          currentUser =
            await response.json();

          return currentUser;
        }
      )
      .catch(
        (error) => {
          initializingUserPromise =
            null;

          throw error;
        }
      );

  return initializingUserPromise;
}

async function prepareActiveSession() {
  const storedSessionId =
    readActiveSessionId();

  if (!storedSessionId) {
    return "";
  }

  currentSessionId =
    storedSessionId;

  const restored =
    await restoreActiveSession(
      {
        userId: "",
        email:
          runtimeConfig
            .userProfile
            .email,
      },

      storedSessionId
    );

  if (!restored) {
    clearActiveSessionId();

    currentSessionId =
      "";
  }

  return currentSessionId;
}

async function ensureChatSession(
  user
) {
  if (currentSessionId) {
    return currentSessionId;
  }

  if (
    ensuringSessionPromise
  ) {
    return ensuringSessionPromise;
  }

  ensuringSessionPromise =
    resolveActiveChatSession(
      user
    ).finally(
      () => {
        ensuringSessionPromise =
          null;
      }
    );

  return ensuringSessionPromise;
}

async function resolveActiveChatSession(
  user
) {
  const storedSessionId =
    readActiveSessionId();

  if (storedSessionId) {
    currentSessionId =
      storedSessionId;

    const restored =
      await restoreActiveSession(
        user,
        storedSessionId
      );

    if (restored) {
      return currentSessionId;
    }

    clearActiveSessionId();

    currentSessionId =
      "";
  }

  return createChatSession(
    user
  );
}

async function createChatSession(
  user
) {
  const response =
    await apiRequest(
      "/chat/sessions",
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json",

          "X-OneAssist-User-Id":
            String(
              user.userId
            ),
        },

        body:
          JSON.stringify({}),
      }
    );

  if (!response.ok) {
    throw new Error(
      "Chat session could not be created."
    );
  }

  const payload =
    await response.json();

  currentSessionId =
    payload.sessionId ||
    "";

  if (!currentSessionId) {
    throw new Error(
      "Chat session response did not include a session ID."
    );
  }

  writeActiveSessionId(
    currentSessionId
  );

  return currentSessionId;
}

async function restoreActiveSession(
  user,
  sessionId
) {
  const userEmail =
    runtimeConfig
      .userProfile
      .email ||
    user?.email ||
    "";

  if (!userEmail) {
    return false;
  }

  try {
    const response =
      await apiRequest(
        `/chat/sessions/${encodeURIComponent(
          sessionId
        )}?user_email=${encodeURIComponent(
          userEmail
        )}`,

        {
          headers:
            user?.userId
              ? {
                  "X-OneAssist-User-Id":
                    String(
                      user.userId
                    ),
                }
              : {},
        }
      );

    if (!response.ok) {
      return false;
    }

    const payload =
      await response.json();

    const session =
      payload.session ||
      {};

    const status =
      String(
        session.status ||
          ""
      ).toUpperCase();

    if (
      status === "ENDED"
    ) {
      return false;
    }

    currentSessionId =
      session.session_uuid ||
      session.uuid ||
      sessionId;

    writeActiveSessionId(
      currentSessionId
    );

    restoreMessages(
      payload.messages ||
        []
    );

    return true;
  } catch (error) {
    oneAssistLogger.warn(
      "active_session_restore_failed",
      {
        errorType:
          error?.name,

        message:
          error?.message,
      }
    );

    return false;
  }
}

function restoreMessages(
  historyMessages
) {
  if (
    !messages ||
    !Array.isArray(
      historyMessages
    )
  ) {
    return;
  }

  const orderedMessages =
    [
      ...historyMessages,
    ].sort(
      (
        left,
        right
      ) => {
        const leftDate =
          Date.parse(
            left.created_at ||
            left.createdAt ||
            ""
          );

        const rightDate =
          Date.parse(
            right.created_at ||
            right.createdAt ||
            ""
          );

        if (
          !Number.isNaN(
            leftDate
          ) &&
          !Number.isNaN(
            rightDate
          ) &&
          leftDate !==
            rightDate
        ) {
          return (
            leftDate -
            rightDate
          );
        }

        return (
          Number(
            left.id ||
              0
          ) -
          Number(
            right.id ||
              0
          )
        );
      }
    );

  orderedMessages.forEach(
    (message) => {
      const rawRole =
        String(
          message.role ||
            ""
        ).toLowerCase();

      const role =
        rawRole ===
          "assistant" ||
        rawRole === "bot"
          ? "bot"
          : "user";

      const text =
        message.message_text ||
        message.messageText ||
        message.content ||
        message.message ||
        message.response_text ||
        "";

      const messageId =
        message.id ||
        message.message_id ||
        message.messageId;

      appendMessage(
        role,
        text,
        message.sources ||
          [],
        {
          enableFeedback:
            role === "bot" &&
            Boolean(
              messageId
            ),

          assistantMessageId:
            role === "bot"
              ? messageId
              : undefined,

          userMessageId:
            role === "user"
              ? messageId
              : undefined,

          messageId,
        }
      );
    }
  );
}

function persistResponseSession(
  payload
) {
  const responseSessionId =
    payload.sessionUuid ||
    (
      typeof payload.sessionId ===
      "string"
        ? payload.sessionId
        : ""
    );

  if (responseSessionId) {
    currentSessionId =
      responseSessionId;

    writeActiveSessionId(
      responseSessionId
    );
  } else if (
    currentSessionId
  ) {
    writeActiveSessionId(
      currentSessionId
    );
  }
}

function getActiveSessionStorageKey() {
  const profileEmail =
    (
      runtimeConfig
        .userProfile
        .email ||
      "anonymous"
    ).toLowerCase();

  return (
    `${ACTIVE_SESSION_STORAGE_PREFIX}:` +
    `${API_BASE_URL}:` +
    `${profileEmail}`
  );
}

function readActiveSessionId() {
  try {
    return String(
      window.localStorage.getItem(
        getActiveSessionStorageKey()
      ) ||
        ""
    ).trim();
  } catch {
    return "";
  }
}

function writeActiveSessionId(
  sessionId
) {
  try {
    window.localStorage.setItem(
      getActiveSessionStorageKey(),

      String(
        sessionId ||
          ""
      )
    );
  } catch {
    // Local storage can be disabled.
  }
}

function clearActiveSessionId() {
  try {
    window.localStorage.removeItem(
      getActiveSessionStorageKey()
    );
  } catch {
    // Local storage can be disabled.
  }
}

function setComposerState(
  isLoading
) {
  if (messageInput) {
    messageInput.disabled =
      isLoading;
  }

  if (sendButton) {
    sendButton.disabled =
      isLoading;
  }
}

function setWidgetOpen(
  isOpen
) {
  if (
    !chatWidget ||
    !launcherButton
  ) {
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
  feedbackModal
    ?.classList
    .remove("hidden");

  feedbackBackdrop
    ?.classList
    .remove("hidden");

  updateFeedbackSubmitState();
}

function closeFeedback() {
  feedbackModal
    ?.classList
    .add("hidden");

  feedbackBackdrop
    ?.classList
    .add("hidden");

  if (feedbackInput) {
    feedbackInput.value =
      "";
  }

  selectedRating = "";

  feedbackChoices.forEach(
    (item) => {
      item.classList.remove(
        "selected"
      );
    }
  );

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
  if (
    !currentUser ||
    !currentSessionId
  ) {
    currentSessionId =
      "";

    clearActiveSessionId();

    return;
  }

  try {
    await apiRequest(
      `/chat/sessions/${currentSessionId}/end`,
      {
        method: "POST",

        headers: {
          "X-OneAssist-User-Id":
            String(
              currentUser.userId
            ),
        },
      }
    );
  } catch (error) {
    oneAssistLogger.error(
      "chat_session_end_failed",
      {
        errorType:
          error?.name,

        message:
          error?.message,
      }
    );
  } finally {
    currentSessionId =
      "";

    clearActiveSessionId();
  }
}

function resetChatSession() {
  if (messages) {
    messages.replaceChildren();
  }

  renderedMessageKeys.clear();

  if (messageInput) {
    messageInput.value =
      "";

    autoResizeTextarea();
  }

  setComposerState(false);

  if (ENABLE_HISTORY_PANEL) {
    // Reserved for history panel.
  }
}

function updateFeedbackSubmitState() {
  if (
    !submitFeedbackButton
  ) {
    return;
  }

  const hasRating =
    Boolean(
      selectedRating
    );

  submitFeedbackButton.disabled =
    !hasRating;

  submitFeedbackButton
    .classList
    .toggle(
      "ready",
      hasRating
    );
}

function autoResizeTextarea() {
  if (!messageInput) {
    return;
  }

  messageInput.style.height =
    "auto";

  messageInput.style.height =
    `${Math.min(
      messageInput.scrollHeight,
      118
    )}px`;
}
