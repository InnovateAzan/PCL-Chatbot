const DEFAULT_ADMIN_API_BASE_URL = "http://127.0.0.1:8085/api";
const params = new URLSearchParams(window.location.search);
const API_BASE_URL = (
  params.get("apiBase") ||
  window.PCL_GPT_CONFIG?.apiBaseUrl ||
  DEFAULT_ADMIN_API_BASE_URL
).replace(/\/+$/, "");
const ADMIN_USER_ID = params.get("userId") || window.PCL_GPT_CONFIG?.adminUserId || "";

const adminHeaders = {
  "X-OneAssist-Admin": "true",
};

if (ADMIN_USER_ID) {
  adminHeaders["X-OneAssist-User-Id"] = String(ADMIN_USER_ID);
}

loadDashboard().catch((error) => {
  console.error("Admin dashboard error:", error);
});

async function loadDashboard() {
  const [summary, usage, questions, policies, topics, unanswered] =
    await Promise.all([
      getJson("/admin/analytics/summary"),
      getJson("/admin/analytics/usage"),
      getJson("/admin/analytics/top-questions"),
      getJson("/admin/analytics/top-policies"),
      getJson("/admin/analytics/unanswered-topics"),
      getJson("/admin/unanswered-questions"),
    ]);

  renderKpis(summary);
  renderList("usageList", usage.items, "label", "value");
  renderList("topQuestionsList", questions.items, "question", "count");
  renderList("topPoliciesList", policies.items, "documentName", "count");
  renderList("topicsList", topics.items, "topic", "count");
  renderUnanswered(unanswered.items);
}

async function getJson(path) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: adminHeaders,
  });

  if (!response.ok) {
    throw new Error(`${path} failed`);
  }

  return response.json();
}

function renderKpis(summary) {
  const grid = document.getElementById("kpiGrid");
  const items = [
    ["Users", summary.totalUsers],
    ["Sessions", summary.totalChatSessions],
    ["Questions", summary.totalUserQuestions],
    ["Policy Answers", summary.policyBasedResponses],
    ["Fallbacks", summary.fallbackResponses],
    ["Feedback", summary.feedbackCount],
    ["Unanswered", summary.unansweredQuestions],
    ["Avg Response ms", Math.round(summary.averageResponseTimeMs || 0)],
  ];

  grid.replaceChildren(
    ...items.map(([label, value]) => {
      const card = document.createElement("article");
      card.className = "admin-kpi";
      card.innerHTML = `<span>${label}</span><strong>${value ?? 0}</strong>`;
      return card;
    })
  );
}

function renderList(elementId, items, labelKey, valueKey) {
  const target = document.getElementById(elementId);

  if (!items?.length) {
    target.textContent = "No data yet.";
    return;
  }

  target.replaceChildren(
    ...items.map((item) => {
      const row = document.createElement("p");
      row.innerHTML = `<span>${escapeHtml(item[labelKey] || "Unknown")}</span><strong>${item[valueKey] ?? 0}</strong>`;
      return row;
    })
  );
}

function renderUnanswered(items) {
  const target = document.getElementById("unansweredTable");

  if (!items?.length) {
    target.textContent = "No unanswered questions yet.";
    return;
  }

  const table = document.createElement("table");
  table.className = "admin-table";
  table.innerHTML = `
    <thead>
      <tr>
        <th>Question</th>
        <th>Topic</th>
        <th>Count</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      ${items.map((item) => `
        <tr>
          <td>${escapeHtml(item.normalizedQuestion)}</td>
          <td>${escapeHtml(item.detectedTopic || "")}</td>
          <td>${item.occurrenceCount}</td>
          <td>${escapeHtml(item.reviewStatus)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  target.replaceChildren(table);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
