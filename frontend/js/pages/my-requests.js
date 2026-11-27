document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("my-requests");
  const auth = await LifeLinkAuth.requireAuth();
  if (!auth) return;

  const listEl = document.getElementById("my-requests-list");
  listEl.innerHTML = `<div class="card">Loading your blood requests...</div>`;

  try {
    const requests = await LifeLinkAPI.request("/api/requests");
    if (!requests.length) {
      listEl.innerHTML = `
        <div class="empty-state">
          <h3>No blood requests created yet</h3>
          <p>Create a structured emergency blood request to start donor coordination.</p>
          <a href="/pages/create-request.html" class="btn btn-primary">Create Blood Request</a>
        </div>
      `;
      return;
    }

    listEl.innerHTML = `<div class="grid-2">${requests
      .map(
        (r) => `
      <div class="card">
        <div style="display: flex; justify-content: space-between; gap: 8px; align-items: center;">
          <strong>${LifeLinkUI.escapeHtml(r.patient_reference_name)}</strong>
          <span class="badge badge-red">${LifeLinkUI.escapeHtml(r.blood_group)} &middot; ${LifeLinkUI.escapeHtml(r.units_requested)} unit(s)</span>
        </div>
        <p style="margin: 8px 0; color: var(--text-secondary); font-size: 0.92rem;">
          ${LifeLinkUI.escapeHtml(r.hospital_name)}, ${LifeLinkUI.escapeHtml(r.city)}
        </p>
        <div style="display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0 14px;">
          <span class="badge ${LifeLinkUI.statusBadgeClass(r.status)}">${LifeLinkUI.formatLabel(r.status)}</span>
          <span class="badge ${LifeLinkUI.statusBadgeClass(r.urgency)}">${LifeLinkUI.formatLabel(r.urgency)}</span>
          <span class="badge badge-neutral">Stage ${LifeLinkUI.escapeHtml(r.escalation_stage)}</span>
        </div>
        <a href="/pages/request-details.html?id=${encodeURIComponent(r.id)}" class="btn btn-secondary btn-sm">View Details &amp; Timeline</a>
      </div>
    `
      )
      .join("")}</div>`;
  } catch (err) {
    listEl.innerHTML = "";
    LifeLinkUI.showAlert("my-requests-alert", err.message, "error");
  }
});
