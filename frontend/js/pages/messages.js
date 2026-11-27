document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("messages");
  const auth = await LifeLinkAuth.requireAuth();
  if (!auth) return;

  const params = new URLSearchParams(window.location.search);
  let activeConvId = params.get("conversation_id") || "";
  let activeConv = null;
  let pollTimer = null;

  const convListEl = document.getElementById("conv-list");
  const emptySelectionEl = document.getElementById("chat-empty-selection");
  const activeViewEl = document.getElementById("chat-active-view");
  const messagesBoxEl = document.getElementById("chat-messages-box");

  async function loadConversations() {
    const convs = await LifeLinkAPI.request("/api/conversations");
    if (!convs.length) {
      convListEl.innerHTML = `<p style="color: var(--text-secondary); margin: 0;">No conversations yet. Chats open automatically when a donor accepts a request.</p>`;
      return [];
    }
    convListEl.innerHTML = convs
      .map(
        (c) => `
      <button type="button" class="btn btn-outline conv-item-btn" data-id="${c.id}" style="justify-content: space-between; text-align: left; width: 100%; ${c.id === activeConvId ? "border-color: var(--primary-red); background: var(--light-red);" : ""}">
        <span>
          <strong>${LifeLinkUI.escapeHtml(c.counterpart_display_name)}</strong>
          <span class="form-hint" style="display: block;">${LifeLinkUI.escapeHtml(c.blood_group)} &middot; ${LifeLinkUI.escapeHtml(c.hospital_name)}</span>
        </span>
        ${c.unread_count > 0 ? `<span class="badge badge-red">${c.unread_count}</span>` : `<span class="badge badge-neutral">${LifeLinkUI.formatLabel(c.status)}</span>`}
      </button>
    `
      )
      .join("");

    document.querySelectorAll(".conv-item-btn").forEach((btn) => {
      btn.addEventListener("click", () => selectConversation(btn.dataset.id));
    });
    return convs;
  }

  async function loadContactSharing(conv) {
    const donorUserId = conv.my_role === "requester" ? conv.counterpart_user_id : auth.user.id;
    const cs = await LifeLinkAPI.request(
      `/api/contact-sharing/${encodeURIComponent(conv.request_id)}?donor_user_id=${encodeURIComponent(donorUserId)}`
    );
    const textEl = document.getElementById("cs-status-text");
    if (cs.status === "both_consented" && cs.counterpart_phone_number) {
      textEl.textContent = `Both participants agreed. Verified phone: ${cs.counterpart_phone_number}. (${cs.privacy_notice})`;
    } else if (cs.status === "withdrawn") {
      textEl.textContent = `Contact sharing was withdrawn. Phone numbers are hidden for future requests.`;
    } else {
      textEl.textContent = `Requester consent: ${cs.requester_consent ? "Yes" : "No"} | Donor consent: ${cs.donor_consent ? "Yes" : "No"}. Both must agree to reveal phone numbers.`;
    }
  }

  async function loadMessagesOnly(convId) {
    const msgs = await LifeLinkAPI.request(`/api/messages/${encodeURIComponent(convId)}`);
    await LifeLinkAPI.request(`/api/messages/${encodeURIComponent(convId)}/read`, { method: "POST" });
    messagesBoxEl.innerHTML = msgs.length
      ? msgs
          .map(
            (m) => `
          <div style="justify-self: ${m.is_mine ? "end" : "start"}; max-width: 82%; background: ${m.is_mine ? "var(--primary-red)" : "var(--white)"}; color: ${m.is_mine ? "var(--white)" : "var(--text)"}; border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 14px;">
            <div style="font-size: 0.78rem; opacity: 0.85; margin-bottom: 4px;">${LifeLinkUI.escapeHtml(m.sender_display_name)} &middot; ${new Date(m.created_at).toLocaleTimeString()}</div>
            <div>${LifeLinkUI.escapeHtml(m.message_text)}</div>
          </div>
        `
          )
          .join("")
      : `<p style="color: var(--text-secondary); margin: 0;">No messages yet. Introduce yourself and coordinate hospital details safely.</p>`;
    messagesBoxEl.scrollTop = messagesBoxEl.scrollHeight;
  }

  async function selectConversation(convId) {
    LifeLinkUI.clearAlert("chat-alert");
    activeConvId = convId;
    try {
      activeConv = await LifeLinkAPI.request(`/api/conversations/${encodeURIComponent(convId)}`);
      emptySelectionEl.classList.add("hidden");
      activeViewEl.classList.remove("hidden");

      document.getElementById("chat-counterpart-name").textContent = activeConv.counterpart_display_name;
      const badge = document.getElementById("chat-conv-status");
      badge.textContent = LifeLinkUI.formatLabel(activeConv.status);
      badge.className = `badge ${LifeLinkUI.statusBadgeClass(activeConv.status)}`;
      document.getElementById("chat-request-context").textContent =
        `${activeConv.blood_group} · ${activeConv.hospital_name}, ${activeConv.city}`;

      const disabled = activeConv.status !== "active";
      document.getElementById("chat-message-input").disabled = disabled;
      document.getElementById("chat-send-btn").disabled = disabled;

      await Promise.all([loadMessagesOnly(convId), loadContactSharing(activeConv), loadConversations()]);

      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(async () => {
        if (activeConvId) {
          try {
            await loadMessagesOnly(activeConvId);
          } catch {
            // Silent poll retry
          }
        }
      }, 4500);
    } catch (err) {
      LifeLinkUI.showAlert("chat-alert", err.message, "error");
    }
  }

  document.getElementById("chat-send-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!activeConvId) return;
    const input = document.getElementById("chat-message-input");
    const text = input.value.trim();
    if (!text) return;
    try {
      await LifeLinkAPI.request(`/api/messages/${encodeURIComponent(activeConvId)}`, {
        method: "POST",
        body: JSON.stringify({ message_text: text }),
      });
      input.value = "";
      await loadMessagesOnly(activeConvId);
    } catch (err) {
      LifeLinkUI.showAlert("chat-alert", err.message, "error");
    }
  });

  async function toggleConsent(grant) {
    if (!activeConv) return;
    const donorUserId = activeConv.my_role === "requester" ? activeConv.counterpart_user_id : auth.user.id;
    const endpoint = grant ? "consent" : "withdraw";
    try {
      await LifeLinkAPI.request(
        `/api/contact-sharing/${encodeURIComponent(activeConv.request_id)}/${endpoint}?donor_user_id=${encodeURIComponent(donorUserId)}`,
        { method: "POST" }
      );
      await loadContactSharing(activeConv);
    } catch (err) {
      LifeLinkUI.showAlert("chat-alert", err.message, "error");
    }
  }

  document.getElementById("cs-consent-btn").addEventListener("click", () => toggleConsent(true));
  document.getElementById("cs-withdraw-btn").addEventListener("click", () => toggleConsent(false));

  document.getElementById("chat-block-btn").addEventListener("click", async () => {
    if (!activeConv) return;
    try {
      await LifeLinkAPI.request("/api/reports/block", {
        method: "POST",
        body: JSON.stringify({
          blocked_user_id: activeConv.counterpart_user_id,
          conversation_id: activeConv.id,
          reason: "Blocked from private chat",
        }),
      });
      LifeLinkUI.showAlert("chat-alert", "User blocked and conversation closed.", "info");
      await selectConversation(activeConv.id);
    } catch (err) {
      LifeLinkUI.showAlert("chat-alert", err.message, "error");
    }
  });

  document.getElementById("chat-report-btn").addEventListener("click", async () => {
    if (!activeConv) return;
    const reason = window.prompt("Please describe why you are reporting this user or request:");
    if (!reason || reason.trim().length < 3) return;
    try {
      await LifeLinkAPI.request("/api/reports", {
        method: "POST",
        body: JSON.stringify({
          reported_user_id: activeConv.counterpart_user_id,
          request_id: activeConv.request_id,
          reason: reason.trim(),
        }),
      });
      LifeLinkUI.showAlert("chat-alert", "Report submitted to administrators for review.", "success");
    } catch (err) {
      LifeLinkUI.showAlert("chat-alert", err.message, "error");
    }
  });

  const convs = await loadConversations();
  if (activeConvId) {
    await selectConversation(activeConvId);
  } else if (convs.length > 0) {
    await selectConversation(convs[0].id);
  }
});
