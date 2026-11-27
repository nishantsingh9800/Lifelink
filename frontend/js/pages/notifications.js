document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("notifications");
  const auth = await LifeLinkAuth.requireAuth();
  if (!auth) return;

  const listEl = document.getElementById("notif-list");

  async function loadNotifications() {
    listEl.innerHTML = `<div class="card">Loading notifications...</div>`;
    try {
      const items = await LifeLinkAPI.request("/api/notifications");
      if (!items.length) {
        listEl.innerHTML = `
          <div class="empty-state">
            <h3>No notifications yet</h3>
            <p>Request alerts, donor acceptances/declines, and escalation updates will appear here.</p>
          </div>
        `;
        return;
      }

      listEl.innerHTML = `<div style="display: grid; gap: 12px;">${items
        .map(
          (n) => `
        <div class="card" style="${n.read_at ? "" : "border-left: 4px solid var(--primary-red);"}">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap;">
            <div>
              <strong>${LifeLinkUI.escapeHtml(n.title)}</strong>
              ${n.read_at ? `<span class="badge badge-neutral" style="margin-left: 6px;">Read</span>` : `<span class="badge badge-red" style="margin-left: 6px;">Unread</span>`}
              <p style="margin: 6px 0; color: var(--text-secondary);">${LifeLinkUI.escapeHtml(n.message)}</p>
              <div class="form-hint">${new Date(n.created_at).toLocaleString()}</div>
            </div>
            <div style="display: flex; gap: 8px;">
              ${n.related_request_id ? `<a href="/pages/request-details.html?id=${encodeURIComponent(n.related_request_id)}" class="btn btn-secondary btn-sm">Open Request</a>` : ""}
              ${!n.read_at ? `<button type="button" class="btn btn-outline btn-sm mark-read-btn" data-id="${n.id}">Mark Read</button>` : ""}
            </div>
          </div>
        </div>
      `
        )
        .join("")}</div>`;

      document.querySelectorAll(".mark-read-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await LifeLinkAPI.request(`/api/notifications/${encodeURIComponent(btn.dataset.id)}/read`, {
            method: "POST",
          });
          await loadNotifications();
        });
      });
    } catch (err) {
      listEl.innerHTML = "";
      LifeLinkUI.showAlert("notif-alert", err.message, "error");
    }
  }

  document.getElementById("mark-all-read-btn").addEventListener("click", async () => {
    await LifeLinkAPI.request("/api/notifications/read-all", { method: "POST" });
    await loadNotifications();
  });

  await loadNotifications();
});
