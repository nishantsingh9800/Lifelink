document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("assistant");
  const auth = await LifeLinkAuth.requireAuth();
  if (!auth) return;

  let sessionId = null;
  const logEl = document.getElementById("assistant-log");
  const inputEl = document.getElementById("assistant-input");

  function appendBubble(senderType, text, actions = []) {
    const isUser = senderType === "user";
    const wrapper = document.createElement("div");
    wrapper.style.justifySelf = isUser ? "end" : "start";
    wrapper.style.maxWidth = "85%";
    wrapper.style.background = isUser ? "var(--primary-red)" : "var(--white)";
    wrapper.style.color = isUser ? "var(--white)" : "var(--text)";
    wrapper.style.border = "1px solid var(--border)";
    wrapper.style.borderRadius = "var(--radius-md)";
    wrapper.style.padding = "10px 14px";

    const actionHtml = actions.length
      ? `<div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px;">
          ${actions
            .map(
              (a) =>
                `<a href="${LifeLinkUI.escapeHtml(a.url)}" class="btn btn-secondary btn-sm">${LifeLinkUI.escapeHtml(a.label)}</a>`
            )
            .join("")}
         </div>`
      : "";

    wrapper.innerHTML = `
      <div style="font-size: 0.76rem; opacity: 0.8; margin-bottom: 4px;">${isUser ? "You" : "LifeLink Assistant"}</div>
      <div>${LifeLinkUI.escapeHtml(text)}</div>
      ${actionHtml}
    `;
    logEl.appendChild(wrapper);
    logEl.scrollTop = logEl.scrollHeight;
  }

  try {
    const history = await LifeLinkAPI.request("/api/chatbot/history");
    sessionId = history.session_id;
    if (history.messages && history.messages.length) {
      history.messages.forEach((m) => appendBubble(m.sender_type, m.message_text));
    } else {
      appendBubble(
        "assistant",
        "Hello! I am LifeLink Assistant (rule-based platform guide). Ask me to prepare a blood request, track your request status, or explain privacy and blood-bank resources."
      );
    }
  } catch (err) {
    LifeLinkUI.showAlert("assistant-alert", err.message, "error");
  }

  async function sendPrompt(text) {
    LifeLinkUI.clearAlert("assistant-alert");
    appendBubble("user", text);
    try {
      const res = await LifeLinkAPI.request("/api/chatbot/message", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });
      sessionId = res.session_id;
      appendBubble("assistant", res.reply, res.suggested_actions || []);
    } catch (err) {
      LifeLinkUI.showAlert("assistant-alert", err.message, "error");
    }
  }

  document.getElementById("assistant-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = "";
    await sendPrompt(text);
  });

  document.querySelectorAll(".quick-prompt-btn").forEach((btn) => {
    btn.addEventListener("click", () => sendPrompt(btn.dataset.prompt));
  });
});
