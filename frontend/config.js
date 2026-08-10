window.PCL_GPT_CONFIG = {
  ...(window.PCL_GPT_CONFIG || {}),
  apiBaseUrl: "http://127.0.0.1:8085/api",
  enableClientDebugLogs: true,
  logUserMessages: false,
};

window.ONEASSIST_BUILD_TRANSPORT_HEADERS = function buildTransportHeaders(
  headers = {},
  apiBaseUrl = window.PCL_GPT_CONFIG?.apiBaseUrl || ""
) {
  const output = {
    ...(headers || {}),
  };

  try {
    const hostname = new URL(apiBaseUrl).hostname.toLowerCase();

    if (
      hostname.endsWith(".ngrok-free.dev") ||
      hostname.endsWith(".ngrok-free.app")
    ) {
      output["ngrok-skip-browser-warning"] = "true";
    }
  } catch {
    // Keep original headers.
  }

  return output;
};
