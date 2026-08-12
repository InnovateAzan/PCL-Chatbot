const DEFAULT_API_BASE_URL = "http://127.0.0.1:8085/api";
const LOCAL_PROFILE_STORAGE_KEY = "oneassist.localProfile";
const ACTIVE_SESSION_STORAGE_PREFIX = "oneassist.activeSessionId";
const ACTIVE_MODULE_STORAGE_PREFIX = "oneassist.activeModule";
const API_TOKEN_MESSAGE_TYPE = "onedesk-api-token";
const LEGACY_API_TOKEN_MESSAGE_TYPE = "pcl-gpt:api-token";
const API_TOKEN_REQUEST_MESSAGE_TYPE = "pcl-gpt:api-token-request";

window.ONEASSIST_BUILD_VERSION = "2026-08-11-v4";

const runtimeConfig = getRuntimeConfig();
const API_BASE_URL = runtimeConfig.apiBaseUrl;
const EMBED_MODE = runtimeConfig.embedMode;
const HOSTED_MODE = runtimeConfig.hostedMode;
const DEFAULT_OPEN = runtimeConfig.defaultOpen;
const ENABLE_HISTORY_PANEL = runtimeConfig.enableHistoryPanel;
const ENABLE_CLIENT_DEBUG_LOGS = Boolean(
  runtimeConfig.enableClientDebugLogs
);
const LOG_USER_MESSAGES = Boolean(
  runtimeConfig.logUserMessages
);

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

const feedbackChoices = document.querySelectorAll(
  ".feedback-choice"
);

let selectedRating = "";
let currentUser = null;
let currentSessionId = "";

let initializingUserPromise = null;
let ensuringSessionPromise = null;
let typingIndicatorElement = null;
let quickActionsElement = null;
let awaitingSpecificTicketNumber = false;
let selectedSpecificTicketNumber = "";
let selectedPolicyName = "";
let activeModule = readActiveModule() || "main";

const renderedMessageKeys = new Set();

let backendReadyPromise = null;

let apiAccessToken = "";
let apiAccessTokenExpiresAt = 0;
let apiAccessTokenPromise = null;
let apiAccessTokenError = "";

oneAssistLogger.info(
  "OneDesk Assistant frontend version:",
  {
    version: window.ONEASSIST_BUILD_VERSION,
    apiBaseUrl: API_BASE_URL,
    origin: window.location.origin,
    embedMode: EMBED_MODE,
    hostedMode: HOSTED_MODE,
    enableClientDebugLogs: ENABLE_CLIENT_DEBUG_LOGS,
  }
);

document.body.classList.toggle(
  "embed-mode",
  EMBED_MODE
);

document.body.classList.toggle(
  "hosted-mode",
  HOSTED_MODE
);

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

/*
 * IMPORTANT FIX:
 * Previous code called showGuidedOptions("root"),
 * but that function does not exist.
 *
 * The real function in this file is:
 * showQuickActions("root")
 */
ensureBackendReady()
  .then(async () => {
    await prepareActiveSession();
    showQuickActions("root");
  })
  .catch((error) => {
    oneAssistLogger.error(
      "active_session_initialization_failed",
      {
        errorType: error?.name,
        message: error?.message,
      }
    );
  });

launcherButton?.addEventListener(
  "click",
  () => {
    const willOpen =
      chatWidget?.classList.contains("hidden") ?? true;

    setWidgetOpen(willOpen);
  }
);

collapseButton?.addEventListener(
  "click",
  () => {
    setWidgetOpen(false);
    notifyHostClose();
  }
);

endChatButton?.addEventListener(
  "click",
  () => {
    openFeedback();
  }
);

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
  button.addEventListener(
    "click",
    () => {
      selectedRating =
        button.dataset.rating ?? "";

      feedbackChoices.forEach((item) => {
        item.classList.remove("selected");
      });

      button.classList.add("selected");

      updateFeedbackSubmitState();
    }
  );
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

    /*
     * Specific ticket number flow.
     *
     * If the user clicked "Check Specific Ticket"
     * and then enters a number like 113, do not
     * immediately send it to backend.
     *
     * Instead show:
     * Status
     * Assigned To
     * Request Type
     * Created Date
     * Last Updated
     * Full Details
     */
    if (
      awaitingSpecificTicketNumber &&
      /^\d{1,8}$/.test(message)
    ) {
      appendMessage(
        "user",
        message
      );

      messageInput.value = "";

      autoResizeTextarea();

      showTicketSpecificActions(
        message
      );

      return;
    }

    if (
      activeModule === "policies" &&
      isTicketIntent(message)
    ) {
      appendMessage("user", message);
      messageInput.value = "";
      autoResizeTextarea();
      appendMessage(
        "bot",
        "You're currently in IT Policies. I can help with policy-related questions here. For ticket status, assignment, or Service Desk details, please switch to IT Service Desk Tickets."
      );
      showQuickActions("root");
      return;
    }

    if (
      activeModule === "serviceDesk" &&
      isPolicyIntent(message)
    ) {
      appendMessage("user", message);
      messageInput.value = "";
      autoResizeTextarea();
      appendMessage(
        "bot",
        "You're currently in IT Service Desk Tickets. For policy-related questions, please switch to IT Policies."
      );
      showQuickActions("root");
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
          apiUrl:
            API_BASE_URL,

          endpoint:
            "/chat",

          url:
            chatEndpoint,

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

            body:
              JSON.stringify({
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
          endpoint:
            "/chat",

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
        formatApiErrorMessage(
          error
        )
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
      !isApiTokenMessage(
        payload
      )
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


/* =========================================================
   BACKEND
   ========================================================= */

function ensureBackendReady() {
  if (backendReadyPromise) {
    return backendReadyPromise;
  }

  const healthEndpoint =
    buildApiUrl(
      "/health"
    );

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
        method:
          "GET",

        headers: {
          Accept:
            "application/json",
        },
      }
    )
      .then(
        async (
          response
        ) => {
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
      .catch(
        (error) => {
          backendReadyPromise =
            null;

          throw error;
        }
      );

  return backendReadyPromise;
}

async function apiRequest(
  path,
  options = {},
  requestOptions = {}
) {
  return performApiRequest(
    buildApiUrl(
      path
    ),

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
      ...(options.headers || {}),

      ...(requiresAuth
        ? await getApiAuthorizationHeader()
        : {}),
    });

  let response;

  try {
    response =
      await fetch(
        url,
        {
          ...options,
          headers,
        }
      );
  } catch (error) {
    if (
      requiresAuth &&
      isEmbeddedSharePointMode() &&
      !isUsableJwt(
        apiAccessToken
      )
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
      ...(options.headers || {}),

      ...(requiresAuth
        ? await getApiAuthorizationHeader(
            {
              forceRefresh:
                true,
            }
          )
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


/* =========================================================
   AUTH
   ========================================================= */

async function getApiAuthorizationHeader(
  options = {}
) {
  const token =
    await getApiAccessToken(
      options
    );

  if (
    !isUsableJwt(
      token
    )
  ) {
    oneAssistLogger.warn(
      "authorization_header_skipped",
      {
        tokenPresent:
          Boolean(
            token
          ),

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
    Authorization:
      `Bearer ${token}`,
  };
}

async function getApiAccessToken(
  options = {}
) {
  if (
    options.forceRefresh
  ) {
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

  if (
    apiAccessTokenPromise
  ) {
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
    ).finally(
      () => {
        apiAccessTokenPromise =
          null;
      }
    );

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
        ? (
            "Microsoft sign-in did not respond. " +
            "Refresh the OneDesk page and try again."
          )
        : (
            "Microsoft sign-in could not obtain access to the " +
            "OneDesk Chat Assistant API. Verify the access_as_user " +
            "permission is approved, then refresh the OneDesk page."
          )
    );

  error.code =
    code;

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
    !isUsableJwt(
      token
    )
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
    value.length > 100 &&
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


/* =========================================================
   API ERRORS
   ========================================================= */

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

    if (
      payload?.detail
    ) {
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
      (
        "Backend request failed with HTTP " +
        `${response.status}.`
      )
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
      error?.code ||
      ""
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

  if (
    statusCode
  ) {
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
      error?.code ||
      ""
    ).startsWith(
      "token_"
    ) ||
    Number(
      error?.statusCode ||
      0
    ) === 401
  );
}


/* =========================================================
   QUICK ACTIONS
   ========================================================= */

function showQuickActions(
  kind = "root"
) {
  if (!messages) {
    return;
  }

  clearQuickActions();

  const wrapper =
    document.createElement(
      "div"
    );

  wrapper.className =
    "quick-actions";
  wrapper.dataset.kind =
    kind;

  const title =
    document.createElement(
      "div"
    );

  title.className =
    "quick-actions-title";

  title.textContent =
    kind === "tickets"
      ? "Choose a ticket action"
      : kind === "policies" || kind === "browse-policies" || kind === "policy-actions"
        ? "What would you like help with?"
        : `Hi ${getFirstName()}, how can I help you today?`;

  const actions =
    kind === "tickets"
      ? [
          {
            label: "View My Tickets",
            message: "show my tickets",
          },
          {
            label: "My Assigned Tickets",
            message: "show my assigned tickets",
          },
          {
            label: "Open Tickets",
            message: "show my open tickets",
          },
          {
            label: "Resolved Tickets",
            message: "show my resolved tickets",
          },
          {
            label: "Ticket Summary",
            message: "ticket summary",
          },
          {
            label: "Check Specific Ticket",
            message: "__ask_ticket_number__",
          },
          {
            label: "Back to Main Menu",
            message: "__main_menu__",
          },
        ]
      : kind === "policies"
        ? [
            { label: "Ask a Policy Question", message: "__policy_question__" },
            { label: "Browse Policies", message: "__browse_policies__" },
            { label: "Back to Main Menu", message: "__main_menu__" },
          ]
        : kind === "browse-policies"
          ? [
              { label: "Acceptable Use", message: "__policy_select:Acceptable Use__" },
              { label: "AI Governance", message: "__policy_select:AI Governance__" },
              { label: "Information Security", message: "__policy_select:Information Security__" },
              { label: "Access Control", message: "__policy_select:Access Control__" },
              { label: "Backup & Disaster Recovery", message: "__policy_select:Backup & Disaster Recovery__" },
              { label: "Incident Response", message: "__policy_select:Incident Response__" },
              { label: "Hardware Procurement", message: "__policy_select:Hardware Procurement__" },
              { label: "Software Procurement", message: "__policy_select:Software Procurement__" },
              { label: "Vendor & Third-Party Risk", message: "__policy_select:Vendor & Third-Party Risk__" },
              { label: "Back", message: "__back_policies__" },
              { label: "Main Menu", message: "__main_menu__" },
            ]
          : kind === "policy-actions"
            ? [
                { label: "Ask a Question", message: "__policy_question__" },
                { label: "Policy Summary", message: "policy summary" },
                { label: "Key Responsibilities", message: "policy key responsibilities" },
                { label: "Compliance Requirements", message: "policy compliance requirements" },
                { label: "← Policies", message: "__policy_menu__" },
                { label: "Main Menu", message: "__main_menu__" },
              ]
            : [
                {
                  label: "IT Policies",
                  message: "__policy_menu__",
                },
                {
                  label: "IT Service Desk Tickets",
                  message: "__ticket_menu__",
                },
              ];

  const chips =
    document.createElement(
      "div"
    );

  chips.className =
    "quick-actions-chips";

  actions.forEach(
    (action) => {
      const button =
        document.createElement(
          "button"
        );

      button.type =
        "button";

      button.className =
        "quick-action-chip";

      button.textContent =
        action.label;

      button.addEventListener(
        "click",
        () =>
          handleQuickAction(
            action.message
          )
      );

      chips.appendChild(
        button
      );
    }
  );

  wrapper.appendChild(
    title
  );

  wrapper.appendChild(
    chips
  );

  /*
   * Append rather than prepend so the guided
   * menu behaves naturally inside the chat.
   */
  messages.appendChild(
    wrapper
  );

  quickActionsElement =
    wrapper;

  messages.scrollTop =
    messages.scrollHeight;
}

function clearQuickActions() {
  quickActionsElement?.remove();

  quickActionsElement =
    null;
}

function getFirstName() {
  const preferred =
    String(
      runtimeConfig.userProfile.preferredName || ""
    ).trim();

  if (preferred) {
    return preferred.split(/\s+/)[0];
  }

  const display =
    String(
      runtimeConfig.userProfile.displayName || ""
    ).trim();

  if (display) {
    return display.split(/\s+/)[0];
  }

  return "there";
}

function isPolicyIntent(message) {
  return /(?:\bpolicy\b|policies|acceptable use|ai governance|information security|access control|backup|disaster recovery|incident response|hardware procurement|software procurement|vendor|third[- ]party risk)/i.test(
    String(message || "")
  );
}

function isTicketIntent(message) {
  return /(?:\bticket\b|\bassigned\b|\bassign\b|\bopen\b|\bresolved\b|\bstatus\b|\bcreated\b|\bupdated\b|\blast updated\b|\bsummary\b|\bservice desk\b)/i.test(
    String(message || "")
  );
}

function handleQuickAction(
  message
) {
  if (
    !messageInput ||
    !chatForm
  ) {
    return;
  }

  /*
   * Root menu:
   * IT Policies
   * Frontend navigation only.
   * Do NOT send "it policies" to backend.
   */
  if (
    message === "it policies"
  ) {
    activeModule = "policies";
    writeActiveModule(activeModule);
    showQuickActions(
      "policies"
    );
    return;
  }

  /*
   * Root menu:
   * IT Service Desk Tickets
   * Frontend navigation only.
   */
  if (
    message ===
    "it service desk tickets"
  ) {
    activeModule = "serviceDesk";
    writeActiveModule(activeModule);
    showQuickActions(
      "tickets"
    );
    return;
  }

  /*
   * Main menu
   */
  if (
    message === "__main_menu__"
  ) {
    activeModule = "main";
    writeActiveModule(activeModule);
    selectedPolicyName = "";

    awaitingSpecificTicketNumber =
      false;

    selectedSpecificTicketNumber =
      "";

    showQuickActions(
      "root"
    );

    return;
  }

  /*
   * Back to policy menu
   */
  if (
    message === "__policy_menu__"
  ) {
    activeModule = "policies";
    writeActiveModule(activeModule);
    showQuickActions(
      "policies"
    );

    return;
  }

  /*
   * Back to ticket menu
   */
  if (
    message === "__ticket_menu__"
  ) {
    activeModule = "serviceDesk";
    writeActiveModule(activeModule);
    awaitingSpecificTicketNumber =
      false;

    selectedSpecificTicketNumber =
      "";

    showQuickActions(
      "tickets"
    );

    return;
  }

  /*
   * Browse policy list
   */
  if (
    message ===
    "__browse_policies__"
  ) {
    activeModule = "policies";
    writeActiveModule(activeModule);
    showQuickActions(
      "browse-policies"
    );

    return;
  }

  /*
   * User selected a specific policy.
   *
   * Example internal value:
   * __policy_select:AI Governance__
   */
  if (
    message.startsWith(
      "__policy_select:"
    )
  ) {
    selectedPolicyName =
      message
        .slice(
          "__policy_select:".length
        )
        .replace(
          /__$/,
          ""
        )
        .trim();

    showQuickActions(
      "policy-actions"
    );

    return;
  }

  /*
   * Ask a policy question.
   * Do NOT call backend yet.
   * Wait for user's actual typed question.
   */
  if (
    message ===
    "__policy_question__"
  ) {
    activeModule = "policies";
    writeActiveModule(activeModule);
    clearQuickActions();

    appendMessage(
      "bot",
      selectedPolicyName
        ? `Please type your question about ${selectedPolicyName}.`
        : "Please type your IT policy question below."
    );

    messageInput.focus();

    return;
  }

  /*
   * Back to policy menu
   */
  if (
    message ===
    "__back_policies__"
  ) {
    activeModule = "policies";
    writeActiveModule(activeModule);
    showQuickActions(
      "policies"
    );

    return;
  }

  /*
   * Specific ticket flow.
   * Ask user for ticket number.
   */
  if (
    message ===
    "__ask_ticket_number__"
  ) {
    clearQuickActions();

    awaitingSpecificTicketNumber =
      true;

    selectedSpecificTicketNumber =
      "";

    appendMessage(
      "bot",
      "Please enter the ticket number."
    );

    messageInput.focus();

    return;
  }

  /*
   * From here onward, this is a REAL action/query
   * which may be sent to the backend.
   */
  clearQuickActions();

  /*
   * Policy actions need the selected policy name.
   *
   * Example:
   * selectedPolicyName = "AI Governance"
   * message = "policy summary"
   *
   * Backend receives:
   * "AI Governance policy summary"
   */
  if (
    message ===
      "policy summary" ||
    message ===
      "policy key responsibilities" ||
    message ===
      "policy compliance requirements"
  ) {
    messageInput.value =
      `${selectedPolicyName || "policy"} ${message}`;
  } else {
    messageInput.value =
      message;
  }

  chatForm.requestSubmit();
}

function showTicketSpecificActions(
  ticketNumber
) {
  selectedSpecificTicketNumber =
    String(
      ticketNumber || ""
    ).trim();

  awaitingSpecificTicketNumber =
    false;

  clearQuickActions();

  if (
    !messages
  ) {
    return;
  }

  const wrapper =
    document.createElement(
      "div"
    );

  wrapper.className =
    "quick-actions";

  const title =
    document.createElement(
      "div"
    );

  title.className =
    "quick-actions-title";

  title.textContent =
    `What would you like to know about Ticket #${selectedSpecificTicketNumber}?`;

  const chips =
    document.createElement(
      "div"
    );

  chips.className =
    "quick-actions-chips";

  const mapping = [
    [
      "Status",
      "status",
    ],
    [
      "Assigned To",
      "assigned to",
    ],
    [
      "Request Type",
      "request type",
    ],
    [
      "Created Date",
      "created",
    ],
    [
      "Last Updated",
      "last updated",
    ],
    [
      "Full Details",
      "details",
    ],
  ];

  mapping.forEach(
    ([label, suffix]) => {
      const button =
        document.createElement(
          "button"
        );

      button.type =
        "button";

      button.className =
        "quick-action-chip";

      button.textContent =
        label;

      button.addEventListener(
        "click",
        () => {
          clearQuickActions();

          messageInput.value =
            `ticket ${selectedSpecificTicketNumber} ${suffix}`;

          chatForm.requestSubmit();
        }
      );

      chips.appendChild(
        button
      );
    }
  );

  wrapper.appendChild(
    title
  );

  wrapper.appendChild(
    chips
  );

  messages.appendChild(
    wrapper
  );

  quickActionsElement =
    wrapper;

  messages.scrollTop =
    messages.scrollHeight;
}


/* =========================================================
   MESSAGES
   ========================================================= */

function appendMessage(
  role,
  text,
  sources = [],
  meta = {}
) {
  if (
    !messages
  ) {
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

  if (
    messageKey
  ) {
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

  if (
    role === "bot"
  ) {
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

  bubble.appendChild(
    body
  );

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

    dots.appendChild(
      dot
    );
  }

  bubble.appendChild(
    dots
  );

  article.appendChild(
    bubble
  );

  messages.appendChild(
    article
  );

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

  if (
    !id
  ) {
    return "";
  }

  return `${role}:${id}`;
}


/* =========================================================
   ASSISTANT RESPONSE FORMATTER
   ========================================================= */

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
    if (
      bulletList
    ) {
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
    if (
      !rawLine
    ) {
      closeBulletList();
      continue;
    }

    const sectionMatch =
      rawLine.match(
        /^\[\s*SECTION\s*\](.*?)\[\s*\/\s*SECTION\s*\]$/i
      );

    if (
      sectionMatch
    ) {
      closeBulletList();

      const heading =
        document.createElement(
          "h4"
        );

      heading.className =
        "answer-section-heading";

      appendSafeInlineContent(
        heading,
        sectionMatch[1].trim()
      );

      container.appendChild(
        heading
      );

      continue;
    }

    const bulletMatch =
      rawLine.match(
        /^\[\s*BULLET\s*\](.*?)\[\s*\/\s*BULLET\s*\]$/i
      );

    if (
      bulletMatch
    ) {
      const list =
        getBulletList();

      const item =
        document.createElement(
          "li"
        );

      appendSafeInlineContent(
        item,
        bulletMatch[1].trim()
      );

      list.appendChild(
        item
      );

      continue;
    }

    if (
      rawLine.startsWith("• ") ||
      rawLine.startsWith("- ") ||
      rawLine.startsWith("* ")
    ) {
      const list =
        getBulletList();

      const item =
        document.createElement(
          "li"
        );

      appendSafeInlineContent(
        item,
        rawLine
          .slice(2)
          .trim()
      );

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

    appendSafeInlineContent(
      paragraph,
      rawLine
    );

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

    appendSafeInlineContent(
      paragraph,
      String(
        answer || ""
      )
    );

    container.appendChild(
      paragraph
    );
  }

  return container;
}

function appendSafeInlineContent(
  element,
  text
) {
  const value =
    String(
      text || ""
    );

  const fullMarkdownLink =
    value.match(
      /^\s*\[([^\]]+)\]\s*\(\s*(https?:\/\/.+)\s*\)\s*$/i
    );

  if (
    fullMarkdownLink
  ) {
    createSafeExternalLink(
      element,
      fullMarkdownLink[1],
      fullMarkdownLink[2]
    );

    return;
  }

  const inlineMarkdownPattern =
    /\[([^\]]+)\]\s*\(\s*(https?:\/\/[^<>\s]+)\s*\)/gi;

  let lastIndex = 0;
  let match;

  while (
    (
      match =
        inlineMarkdownPattern.exec(
          value
        )
    ) !== null
  ) {
    if (
      match.index >
      lastIndex
    ) {
      element.appendChild(
        document.createTextNode(
          value.slice(
            lastIndex,
            match.index
          )
        )
      );
    }

    createSafeExternalLink(
      element,
      match[1],
      match[2]
    );

    lastIndex =
      inlineMarkdownPattern.lastIndex;
  }

  if (
    lastIndex > 0
  ) {
    if (
      lastIndex <
      value.length
    ) {
      element.appendChild(
        document.createTextNode(
          value.slice(
            lastIndex
          )
        )
      );
    }

    return;
  }

  element.textContent =
    value;
}

function createSafeExternalLink(
  element,
  label,
  url
) {
  const cleanLabel =
    String(
      label || "Open Ticket"
    ).trim();

  const cleanUrl =
    String(
      url || ""
    ).trim();

  if (
    !/^https?:\/\//i.test(
      cleanUrl
    )
  ) {
    element.appendChild(
      document.createTextNode(
        cleanLabel
      )
    );

    return;
  }

  const link =
    document.createElement(
      "a"
    );

  link.href =
    cleanUrl;

  link.textContent =
    cleanLabel;

  link.target =
    "_blank";

  link.rel =
    "noopener noreferrer";

  link.className =
    "answer-link";

  link.setAttribute(
    "aria-label",
    `${cleanLabel} - opens in a new tab`
  );

  element.appendChild(
    link
  );
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
      /\[([^\]\n]+)\]\s*\n+\s*\((https?:\/\/[^\n]+)\)/gi,
      "[$1]($2)"
    );

  text =
    text.replace(
      /\[([^\]\n]+)\]\s+\((https?:\/\/[^\n]+)\)/gi,
      "[$1]($2)"
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


/* =========================================================
   SOURCES
   ========================================================= */

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
              Number(
                page
              )
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
    uniquePages.length > 1
      ? `Pages ${uniquePages.join(", ")}`
      : uniquePages.length === 1
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
  const buildMainMenuButton = () => {
    const button =
      document.createElement("button");

    button.type = "button";
    button.className = "message-note-action";
    button.textContent = "← Main Menu";

    button.addEventListener("click", () => {
      activeModule = "main";
      writeActiveModule(activeModule);
      awaitingSpecificTicketNumber = false;
      selectedSpecificTicketNumber = "";
      selectedPolicyName = "";
      showQuickActions("root");
    });

    return button;
  };

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
          !seen.has(
            key
          )
        ) {
          seen.add(
            key
          );

          uniqueSources.push(
            label
          );
        }
      }
    );

    if (
      uniqueSources.length > 0
    ) {
      const wrapper =
        document.createElement(
          "div"
        );

      wrapper.className =
        "sources";

      const footerRow =
        document.createElement("div");

      footerRow.className = "message-footer-row";

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

      footerRow.appendChild(wrapper);
      footerRow.appendChild(buildMainMenuButton());

      return footerRow;
    }
  }

  if (
    fallbackNotice
  ) {
    const footerRow =
      document.createElement("div");

    footerRow.className = "message-footer-row";

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

    footerRow.appendChild(note);
    footerRow.appendChild(buildMainMenuButton());

    return footerRow;
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


/* =========================================================
   FEEDBACK
   ========================================================= */

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

  up.type =
    "button";

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

  down.type =
    "button";

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

  wrapper.appendChild(
    up
  );

  wrapper.appendChild(
    down
  );

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
          method:
            "POST",

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

    if (
      !response.ok
    ) {
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


/* =========================================================
   SHAREPOINT HOST
   ========================================================= */

function scheduleHostLayoutUpdate() {
  if (
    !HOSTED_MODE
  ) {
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

  if (
    !bounds
  ) {
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


/* =========================================================
   RUNTIME CONFIG
   ========================================================= */

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
    window.PCL_GPT_CONFIG?.apiBaseUrl ||
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
        document.body.dataset.enableHistory ||
        window.PCL_GPT_CONFIG?.enableHistory
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
        document.body.dataset.parentOrigin ||
        ""
      ).trim(),

    enableClientDebugLogs:
      parseBooleanFlag(
        params.get(
          "enableClientDebugLogs"
        ) ||
        document.body.dataset.enableClientDebugLogs ||
        window.PCL_GPT_CONFIG?.enableClientDebugLogs
      ) === true,

    logUserMessages:
      parseBooleanFlag(
        params.get(
          "logUserMessages"
        ) ||
        document.body.dataset.logUserMessages ||
        window.PCL_GPT_CONFIG?.logUserMessages
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
    window.PCL_GPT_CONFIG?.userProfile ||
    {};

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
      ) ||
      "{}"
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
  if (
    value == null
  ) {
    return undefined;
  }

  const normalized =
    String(
      value
    )
      .trim()
      .toLowerCase();

  if (
    !normalized
  ) {
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

  if (
    embedMode
  ) {
    return true;
  }

  if (
    hostedMode
  ) {
    return false;
  }

  return true;
}


/* =========================================================
   COMPOSER
   ========================================================= */

function handleComposerKeydown(
  event
) {
  if (
    event.key !== "Enter"
  ) {
    return;
  }

  if (
    event.ctrlKey
  ) {
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


/* =========================================================
   USER
   ========================================================= */

async function initializeCurrentUser() {
  if (
    currentUser
  ) {
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
        method:
          "POST",

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
        async (
          response
        ) => {
          if (
            !response.ok
          ) {
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


/* =========================================================
   CHAT SESSION PERSISTENCE
   ========================================================= */

async function prepareActiveSession() {
  const storedSessionId =
    readActiveSessionId();

  if (
    !storedSessionId
  ) {
    return "";
  }

  currentSessionId =
    storedSessionId;

  const restored =
    await restoreActiveSession(
      {
        userId:
          "",

        email:
          runtimeConfig
            .userProfile
            .email,
      },

      storedSessionId
    );

  if (
    !restored
  ) {
    clearActiveSessionId();

    currentSessionId =
      "";
  }

  return currentSessionId;
}

async function ensureChatSession(
  user
) {
  if (
    currentSessionId
  ) {
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

  if (
    storedSessionId
  ) {
    currentSessionId =
      storedSessionId;

    const restored =
      await restoreActiveSession(
        user,
        storedSessionId
      );

    if (
      restored
    ) {
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
        method:
          "POST",

        headers: {
          "Content-Type":
            "application/json",

          "X-OneAssist-User-Id":
            String(
              user.userId
            ),
        },

        body:
          JSON.stringify(
            {}
          ),
      }
    );

  if (
    !response.ok
  ) {
    throw new Error(
      "Chat session could not be created."
    );
  }

  const payload =
    await response.json();

  currentSessionId =
    payload.sessionId ||
    "";

  if (
    !currentSessionId
  ) {
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

  if (
    !userEmail
  ) {
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

    if (
      !response.ok
    ) {
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
          leftDate !== rightDate
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
        rawRole ===
          "bot"
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
            role ===
              "bot" &&
            Boolean(
              messageId
            ),

          assistantMessageId:
            role ===
              "bot"
              ? messageId
              : undefined,

          userMessageId:
            role ===
              "user"
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

  if (
    responseSessionId
  ) {
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

function getActiveModuleStorageKey() {
  const profileEmail =
    (
      runtimeConfig.userProfile.email ||
      "anonymous"
    ).toLowerCase();

  return (
    `${ACTIVE_MODULE_STORAGE_PREFIX}:` +
    `${API_BASE_URL}:` +
    `${profileEmail}`
  );
}

function readActiveModule() {
  try {
    return String(
      window.localStorage.getItem(
        getActiveModuleStorageKey()
      ) || ""
    ).trim();
  } catch {
    return "";
  }
}

function writeActiveModule(moduleName) {
  try {
    window.localStorage.setItem(
      getActiveModuleStorageKey(),
      String(moduleName || "")
    );
  } catch {
    // Local storage can be disabled.
  }
}


/* =========================================================
   WIDGET
   ========================================================= */

function setComposerState(
  isLoading
) {
  if (
    messageInput
  ) {
    messageInput.disabled =
      isLoading;
  }

  if (
    sendButton
  ) {
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
    String(
      isOpen
    )
  );

  if (
    isOpen
  ) {
    messageInput?.focus();
    showQuickActions("root");
  }

  scheduleHostLayoutUpdate();
}


/* =========================================================
   END CHAT / FEEDBACK MODAL
   ========================================================= */

function openFeedback() {
  feedbackModal
    ?.classList
    .remove(
      "hidden"
    );

  feedbackBackdrop
    ?.classList
    .remove(
      "hidden"
    );

  updateFeedbackSubmitState();
}

function closeFeedback() {
  feedbackModal
    ?.classList
    .add(
      "hidden"
    );

  feedbackBackdrop
    ?.classList
    .add(
      "hidden"
    );

  if (
    feedbackInput
  ) {
    feedbackInput.value =
      "";
  }

  selectedRating =
    "";

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

  setWidgetOpen(
    false
  );

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
        method:
          "POST",

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
  if (
    messages
  ) {
    messages.replaceChildren();
  }

  renderedMessageKeys.clear();

  awaitingSpecificTicketNumber =
    false;

  selectedSpecificTicketNumber =
    "";

  clearQuickActions();

  if (
    messageInput
  ) {
    messageInput.value =
      "";

    autoResizeTextarea();
  }

  setComposerState(
    false
  );

  if (
    ENABLE_HISTORY_PANEL
  ) {
    // Reserved for history panel.
  }

  /*
   * Prepare the next fresh chat.
   */
  if (
    messages?.childElementCount === 0
  ) {
    showQuickActions(
      "root"
    );
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

  submitFeedbackButton.classList.toggle(
    "ready",
    hasRating
  );
}


/* =========================================================
   TEXTAREA
   ========================================================= */

function autoResizeTextarea() {
  if (
    !messageInput
  ) {
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
