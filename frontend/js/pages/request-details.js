document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("my-requests");
  const auth = await LifeLinkAuth.requireAuth();
  if (!auth) return;

  const params = new URLSearchParams(window.location.search);
  const requestId = params.get("id");
  const loadingEl = document.getElementById("req-detail-loading");

  if (!requestId) {
    loadingEl.classList.add("hidden");
    LifeLinkUI.showAlert("req-detail-alert", "Missing blood request ID.", "error");
    return;
  }

  let arrivalMap = null;
  let arrivalLayers = [];
  let pollTimer = null;

  function renderLiveTracking(summary) {
    if (!summary) return;
    const hvBadge = document.getElementById("rd-hosp-ver-badge");
    hvBadge.textContent = `Hospital: ${LifeLinkUI.formatLabel(summary.hospital_verification_status)}`;
    hvBadge.className = `badge ${summary.hospital_verification_status === "confirmed_genuine" ? "badge-success" : "badge-neutral"}`;

    document.getElementById("rd-live-counters").innerHTML = `
      <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;"><div class="stat-label">Donors Notified</div><div class="stat-value" style="font-size:1.3rem;">${summary.donors_notified}</div></div>
      <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;"><div class="stat-label">Responses Received</div><div class="stat-value" style="font-size:1.3rem;">${summary.responses_received}</div></div>
      <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;"><div class="stat-label">Donors Interested</div><div class="stat-value" style="font-size:1.3rem;">${summary.donors_interested}</div></div>
      <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;"><div class="stat-label">Last Status Update</div><div style="font-size:0.88rem; font-weight:600; margin-top:4px;">${new Date(summary.last_status_update).toLocaleTimeString()}</div></div>
    `;

    document.getElementById("rd-timeline-list").innerHTML = (summary.timeline || [])
      .map((step) => {
        const icon = step.state === "completed" ? "&#10003;" : step.state === "current" ? "&#9679;" : step.state === "terminal" ? "&#9888;" : "&#9675;";
        const cls = step.state === "completed" ? "badge-success" : step.state === "current" ? "badge-warning" : step.state === "terminal" ? "badge-red" : "badge-neutral";
        return `
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px; border:1px solid var(--border); border-radius:var(--radius-sm); padding:10px;">
            <div>
              <strong>${icon} ${step.step}. ${LifeLinkUI.escapeHtml(step.label)}</strong>
              <div class="form-hint">${LifeLinkUI.escapeHtml(step.detail)}</div>
            </div>
            <span class="badge ${cls}">${LifeLinkUI.formatLabel(step.state)}</span>
          </div>
        `;
      })
      .join("");

    document.getElementById("rd-next-steps").innerHTML =
      `<strong>Next Steps:</strong> ${(summary.next_steps || []).map((s) => LifeLinkUI.escapeHtml(s)).join(" ")}`;
  }

  function renderArrivalMap(zones) {
    const badgeEl = document.getElementById("rd-tracking-badge");
    const listEl = document.getElementById("rd-tracking-status-list");
    const mapEl = document.getElementById("rd-arrival-map");

    const activeZones = (zones || []).filter((z) => z.is_active);
    if (!activeZones.length) {
      badgeEl.textContent = "No active radius shared";
      badgeEl.className = "badge badge-neutral";
      listEl.innerHTML = `<p class="form-hint" style="margin: 0;">When an accepted donor enables location sharing, their approximate ~1 km arrival zone appears here.</p>`;
      mapEl.classList.add("hidden");
      return;
    }

    const latest = activeZones[0];
    badgeEl.textContent = LifeLinkUI.formatLabel(latest.tracking_status);
    badgeEl.className = `badge ${LifeLinkUI.statusBadgeClass(latest.tracking_status === "arrived_at_hospital" ? "accepted" : "urgent")}`;

    listEl.innerHTML = activeZones
      .map(
        (z) => `
      <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px; display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
        <div>
          <strong>${LifeLinkUI.escapeHtml(z.donor_display_name)}</strong> &middot; ${LifeLinkUI.escapeHtml(z.distance_band)}
          <div class="form-hint">~${z.radius_meters}m safety radius &middot; Updated ${new Date(z.updated_at).toLocaleTimeString()}</div>
        </div>
        <span class="badge badge-red">${LifeLinkUI.formatLabel(z.tracking_status)}</span>
      </div>
    `
      )
      .join("");

    if (typeof window.L !== "undefined") {
      mapEl.classList.remove("hidden");
      if (!arrivalMap) {
        arrivalMap = window.L.map("rd-arrival-map").setView([latest.zone_lat, latest.zone_lon], 13);
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "&copy; OpenStreetMap contributors",
        }).addTo(arrivalMap);
      } else {
        arrivalMap.setView([latest.zone_lat, latest.zone_lon], 13);
      }
      arrivalLayers.forEach((layer) => arrivalMap.removeLayer(layer));
      arrivalLayers = activeZones.map((z) =>
        window.L.circle([z.zone_lat, z.zone_lon], {
          radius: z.radius_meters,
          color: "#C62828",
          fillColor: "#E53935",
          fillOpacity: 0.22,
          weight: 2,
        })
          .bindPopup(`${LifeLinkUI.escapeHtml(z.donor_display_name)}: ${LifeLinkUI.escapeHtml(z.distance_band)}`)
          .addTo(arrivalMap)
      );
    } else {
      mapEl.classList.add("hidden");
    }
  }

  let isRefreshing = false;

  async function loadAll(manual = false) {
    if (isRefreshing) return;
    isRefreshing = true;
    const refreshBtn = document.getElementById("rd-refresh-live-btn");
    const pollMetaEl = document.getElementById("rd-live-poll-meta");
    if (refreshBtn && !refreshBtn.dataset.origText) {
      refreshBtn.dataset.origText = refreshBtn.textContent.trim();
    }
    if (manual && refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.textContent = "Refreshing...";
    }
    LifeLinkUI.clearAlert("rd-live-conn-alert");
    try {
      const [req, summary, history, candidates, responses, trackingZones] = await Promise.all([
        LifeLinkAPI.request(`/api/requests/${encodeURIComponent(requestId)}`),
        LifeLinkAPI.request(`/api/requests/${encodeURIComponent(requestId)}/tracking-summary`).catch(() => null),
        LifeLinkAPI.request(`/api/requests/${encodeURIComponent(requestId)}/history`),
        LifeLinkAPI.request(`/api/matching/${encodeURIComponent(requestId)}/candidates`),
        LifeLinkAPI.request(`/api/responses/${encodeURIComponent(requestId)}`),
        LifeLinkAPI.request(`/api/tracking/${encodeURIComponent(requestId)}`).catch(() => []),
      ]);
      renderLiveTracking(summary);
      renderArrivalMap(trackingZones);

      loadingEl.classList.add("hidden");
      document.getElementById("req-detail-body").classList.remove("hidden");

      document.getElementById("rd-blood-badge").textContent = `${req.blood_group} · ${req.units_requested} unit(s)`;
      const statusBadge = document.getElementById("rd-status-badge");
      statusBadge.textContent = LifeLinkUI.formatLabel(req.status);
      statusBadge.className = `badge ${LifeLinkUI.statusBadgeClass(req.status)}`;

      document.getElementById("rd-title").textContent = req.patient_reference_name;
      document.getElementById("rd-subtitle").textContent = `Request ID: ${req.id}`;
      document.getElementById("rd-safety-notice").textContent = req.safety_notice;
      document.getElementById("rd-hospital").textContent = `${req.hospital_name} (${req.hospital_location})`;
      document.getElementById("rd-location").textContent = `${req.city} · ${req.approximate_location}`;
      document.getElementById("rd-units").textContent = req.units_requested;
      document.getElementById("rd-urgency").textContent = LifeLinkUI.formatLabel(req.urgency);
      document.getElementById("rd-stage").textContent = req.escalation_stage;
      document.getElementById("rd-expires").textContent = new Date(req.expires_at).toLocaleString();
      document.getElementById("rd-notes").textContent = req.additional_information || "None provided";

      const fallbackEl = document.getElementById("rd-fallback-banner");
      if (req.escalation_stage >= 4 || req.status === "blood_bank_assistance") {
        fallbackEl.classList.remove("hidden");
        fallbackEl.innerHTML =
          `<strong>Stage ${req.escalation_stage} Emergency Fallback:</strong> Availability has not been confirmed through donor matching alone. ` +
          `Contact the treating hospital's blood bank immediately and search verified listings in the <a href="/pages/blood-banks.html">Blood-Bank Directory</a>.`;
      } else {
        fallbackEl.classList.add("hidden");
      }

      const isClosed = ["fulfilled", "cancelled", "expired"].includes(req.status);
      const isOwner = req.requester_id === auth.user.id;
      document.getElementById("rd-owner-actions").classList.toggle("hidden", !isOwner || isClosed);
      document.getElementById("rd-bb-fallback-link").href = `/pages/blood-banks.html?request_id=${encodeURIComponent(req.id)}`;
      document.getElementById("rd-coord-invite-form")?.classList.toggle("hidden", !isOwner || isClosed);

      const coords = await LifeLinkAPI.request(`/api/coordinators/${encodeURIComponent(requestId)}`).catch(() => []);
      const isMyActiveCoord = coords.some((c) => c.coordinator_user_id === auth.user.id && c.status === "active");
      document.getElementById("rd-coord-progress-form")?.classList.toggle("hidden", !(isMyActiveCoord || isOwner) || isClosed);
      const coordListEl = document.getElementById("rd-coordinators-list");
      if (coordListEl) {
        coordListEl.innerHTML = coords.length
          ? coords
            .map(
              (c) => `
              <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px; display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                <div>
                  <strong>${LifeLinkUI.escapeHtml(c.coordinator_display_name)}</strong>
                  <span class="badge ${LifeLinkUI.statusBadgeClass(c.status)}" style="margin-left:6px;">${LifeLinkUI.formatLabel(c.status)}</span>
                  <div class="form-hint">Chat: ${c.can_chat ? "Yes" : "No"} &middot; Blood Banks: ${c.can_contact_blood_banks ? "Yes" : "No"}</div>
                </div>
                ${isOwner && (c.status === "invited" || c.status === "active")
                  ? `<button type="button" class="btn btn-outline btn-sm rd-revoke-coord-btn" data-id="${c.id}">Revoke Access</button>`
                  : ""
                }
              </div>
            `
            )
            .join("")
          : `<p class="form-hint" style="margin:0;">No external emergency coordinator assigned.</p>`;

        document.querySelectorAll(".rd-revoke-coord-btn").forEach((btn) => {
          btn.addEventListener("click", async () => {
            LifeLinkUI.clearAlert("rd-coord-alert");
            try {
              await LifeLinkAPI.request(`/api/coordinators/${encodeURIComponent(btn.dataset.id)}/revoke`, { method: "POST" });
              LifeLinkUI.showAlert("rd-coord-alert", "Coordinator access revoked.", "info");
              await loadAll();
            } catch (err) {
              LifeLinkUI.showAlert("rd-coord-alert", err.message, "error");
            }
          });
        });
      }

      const attempts = await LifeLinkAPI.request(`/api/blood-banks/attempts/${encodeURIComponent(requestId)}`).catch(() => []);
      document.getElementById("rd-bb-attempts-list").innerHTML = attempts.length
        ? attempts
          .map(
            (a) => `
            <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;">
              <strong>${LifeLinkUI.escapeHtml(a.facility_name || a.blood_bank_id)}</strong>
              <span class="badge badge-neutral" style="margin-left: 6px;">${LifeLinkUI.formatLabel(a.outcome)}</span>
              <div class="form-hint">${new Date(a.attempted_at).toLocaleString()}</div>
            </div>
          `
          )
          .join("")
        : `<p style="color: var(--text-secondary); margin: 0;">No blood-bank contact attempts logged yet.</p>`;

      document.getElementById("rd-history-list").innerHTML = history
        .map(
          (item) => `
          <div style="border-left: 3px solid var(--primary-red); padding-left: 12px;">
            <strong>${LifeLinkUI.formatLabel(item.new_status)}</strong>
            <div class="form-hint">${new Date(item.created_at).toLocaleString()}</div>
            <div style="font-size: 0.9rem; color: var(--text-secondary);">${LifeLinkUI.escapeHtml(item.notes || "")}</div>
          </div>
        `
        )
        .join("");

      const candEl = document.getElementById("rd-candidates-list");
      candEl.innerHTML = candidates.length
        ? candidates
          .map(
            (c) => `
            <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <strong>${LifeLinkUI.escapeHtml(c.donor_display_name)} (${LifeLinkUI.escapeHtml(c.blood_group)})</strong>
                <span class="badge ${LifeLinkUI.statusBadgeClass(c.match_status)}">${LifeLinkUI.formatLabel(c.match_status)}</span>
              </div>
              <div class="form-hint">${LifeLinkUI.escapeHtml(c.city)} &middot; ${LifeLinkUI.escapeHtml(c.approximate_location)} &middot; Score ${c.priority_score}</div>
              <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px;">${LifeLinkUI.escapeHtml(c.match_reason)}</div>
            </div>
          `
          )
          .join("")
        : `<p style="color: var(--text-secondary); margin: 0;">No candidate donors notified yet. Click "Find &amp; Notify Donors" to run rule-based matching.</p>`;

      const respEl = document.getElementById("rd-responses-list");
      const donorSelect = document.getElementById("rd-fulfill-donor-select");
      if (donorSelect) {
        const accepted = responses.filter((r) => r.response === "accepted");
        donorSelect.innerHTML =
          `<option value="">Fulfilled via Blood Bank / Other</option>` +
          accepted
            .map(
              (r) =>
                `<option value="${LifeLinkUI.escapeHtml(r.donor_id)}">Donated by ${LifeLinkUI.escapeHtml(r.donor_display_name)} (${LifeLinkUI.escapeHtml(r.blood_group)})</option>`
            )
            .join("");
      }
      respEl.innerHTML = responses.length
        ? responses
          .map(
            (r) => `
            <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px;">
              <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <strong>${LifeLinkUI.escapeHtml(r.donor_display_name)} (${LifeLinkUI.escapeHtml(r.blood_group)})</strong>
                <span class="badge ${LifeLinkUI.statusBadgeClass(r.response)}">${LifeLinkUI.formatLabel(r.response)}</span>
              </div>
              <div class="form-hint">${new Date(r.responded_at).toLocaleString()}</div>
              ${r.conversation_id ? `<div style="margin-top: 8px;"><a href="/pages/messages.html?conversation_id=${encodeURIComponent(r.conversation_id)}" class="btn btn-secondary btn-sm">Open Private Chat</a></div>` : ""}
            </div>
          `
          )
          .join("")
        : `<p style="color: var(--text-secondary); margin: 0;">No donor responses recorded yet.</p>`;
      if (pollMetaEl) {
        pollMetaEl.textContent = `Auto-refreshes every 15 seconds · Last checked ${new Date().toLocaleTimeString()} · Private donor phone numbers hidden`;
      }
    } catch (err) {
      loadingEl.classList.add("hidden");
      if (!document.getElementById("req-detail-body").classList.contains("hidden")) {
        LifeLinkUI.showAlert("rd-live-conn-alert", `Live update delayed (${err.message}). Retrying automatically...`, "warning");
      } else {
        LifeLinkUI.showAlert("req-detail-alert", err.message, "error");
      }
    } finally {
      isRefreshing = false;
      if (refreshBtn) {
        refreshBtn.disabled = false;
        if (manual) {
          refreshBtn.textContent = refreshBtn.dataset.origText || "Refresh Now";
        }
      }
    }
  }

  document.getElementById("rd-match-btn").addEventListener("click", async () => {
    LifeLinkUI.clearAlert("req-detail-alert");
    try {
      const res = await LifeLinkAPI.request(`/api/matching/${encodeURIComponent(requestId)}/run`, { method: "POST" });
      LifeLinkUI.showAlert("req-detail-alert", res.message, "info");
      await loadAll();
    } catch (err) {
      LifeLinkUI.showAlert("req-detail-alert", err.message, "error");
    }
  });

  document.getElementById("rd-escalate-btn").addEventListener("click", async () => {
    LifeLinkUI.clearAlert("req-detail-alert");
    try {
      const res = await LifeLinkAPI.request(`/api/matching/${encodeURIComponent(requestId)}/escalate`, { method: "POST" });
      LifeLinkUI.showAlert("req-detail-alert", res.message, "info");
      await loadAll();
    } catch (err) {
      LifeLinkUI.showAlert("req-detail-alert", err.message, "error");
    }
  });

  document.getElementById("rd-fulfilled-btn").addEventListener("click", async () => {
    const donatedByDonorId = document.getElementById("rd-fulfill-donor-select")?.value || null;
    try {
      await LifeLinkAPI.request(`/api/requests/${encodeURIComponent(requestId)}/outcome`, {
        method: "POST",
        body: JSON.stringify({
          outcome: "fulfilled",
          donated_by_donor_id: donatedByDonorId,
          notes: donatedByDonorId
            ? "Fulfilled by matched donor (3-month cooldown applied)."
            : "Blood arranged and confirmed by requester.",
        }),
      });
      LifeLinkUI.showAlert("req-detail-alert", "Request marked fulfilled.", "success");
      await loadAll();
    } catch (err) {
      LifeLinkUI.showAlert("req-detail-alert", err.message, "error");
    }
  });

  document.getElementById("rd-unresolved-btn").addEventListener("click", async () => {
    try {
      await LifeLinkAPI.request(`/api/requests/${encodeURIComponent(requestId)}/outcome`, {
        method: "POST",
        body: JSON.stringify({ outcome: "unresolved", notes: "No confirmed blood source yet; continuing hospital coordination." }),
      });
      LifeLinkUI.showAlert("req-detail-alert", "Request recorded as unresolved while hospital coordination continues.", "warning");
      await loadAll();
    } catch (err) {
      LifeLinkUI.showAlert("req-detail-alert", err.message, "error");
    }
  });

  document.getElementById("rd-cancel-btn").addEventListener("click", async () => {
    const reason = window.prompt("Enter cancellation reason (sent to notified donors):", "Arranged locally / no longer required");
    if (reason === null) return;
    try {
      await LifeLinkAPI.request(`/api/requests/${encodeURIComponent(requestId)}/cancel`, {
        method: "POST",
        body: JSON.stringify({ reason: reason.trim() || "Cancelled by requester" }),
      });
      LifeLinkUI.showAlert("req-detail-alert", "Blood request cancelled and contacted donors notified.", "info");
      await loadAll();
    } catch (err) {
      LifeLinkUI.showAlert("req-detail-alert", err.message, "error");
    }
  });

  document.getElementById("rd-refresh-live-btn").addEventListener("click", () => loadAll(true));

  document.getElementById("rd-share-btn")?.addEventListener("click", async () => {
    try {
      const link = await LifeLinkAPI.request(`/api/share/${encodeURIComponent(requestId)}`, { method: "POST" });
      const panel = document.getElementById("rd-share-panel");
      const urlEl = document.getElementById("rd-share-url");
      urlEl.href = link.share_url;
      urlEl.textContent = link.share_url;
      document.getElementById("rd-wa-share").href = link.whatsapp_url;
      panel.classList.remove("hidden");
    } catch (err) {
      LifeLinkUI.showAlert("req-detail-alert", err.message, "error");
    }
  });

  document.getElementById("rd-disable-share-btn")?.addEventListener("click", async () => {
    try {
      await LifeLinkAPI.request(`/api/share/${encodeURIComponent(requestId)}/disable`, { method: "POST" });
      document.getElementById("rd-share-panel").classList.add("hidden");
      LifeLinkUI.showAlert("req-detail-alert", "Public share link disabled.", "info");
    } catch (err) {
      LifeLinkUI.showAlert("req-detail-alert", err.message, "error");
    }
  });

  document.getElementById("rd-coord-invite-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("rd-coord-alert");
    const ident = document.getElementById("rd-coord-identifier").value.trim();
    try {
      await LifeLinkAPI.request(`/api/coordinators/${encodeURIComponent(requestId)}/invite`, {
        method: "POST",
        body: JSON.stringify({ coordinator_identifier: ident }),
      });
      document.getElementById("rd-coord-identifier").value = "";
      LifeLinkUI.showAlert("rd-coord-alert", "Coordinator invitation sent.", "success");
      await loadAll();
    } catch (err) {
      LifeLinkUI.showAlert("rd-coord-alert", err.message, "error");
    }
  });

  document.getElementById("rd-coord-progress-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("rd-coord-alert");
    const notes = document.getElementById("rd-coord-progress-notes").value.trim();
    try {
      await LifeLinkAPI.request(`/api/coordinators/${encodeURIComponent(requestId)}/progress`, {
        method: "POST",
        body: JSON.stringify({ notes }),
      });
      document.getElementById("rd-coord-progress-notes").value = "";
      LifeLinkUI.showAlert("rd-coord-alert", "Progress update recorded and requester notified.", "success");
      await loadAll();
    } catch (err) {
      LifeLinkUI.showAlert("rd-coord-alert", err.message, "error");
    }
  });

  await loadAll();
  pollTimer = window.setInterval(() => {
    if (!document.hidden) loadAll();
  }, 15000);
});
