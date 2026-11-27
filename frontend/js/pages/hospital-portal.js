document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("hospital-portal");
  const auth = await LifeLinkAuth.requireAuth(["hospital", "admin"]);
  if (!auth) return;

  if (auth.forbidden) {
    LifeLinkUI.showAlert("hp-alert", "Access Denied (403): Hospital or Administrator account required.", "error");
    return;
  }

  async function refreshHospitalAadhaarBanner() {
    try {
      const cfg = await LifeLinkAPI.getPublicConfig();
      const banner = document.getElementById("hp-aadhaar-banner");
      const card = document.getElementById("hp-aadhaar-card");
      if (!cfg.require_aadhaar_for_actions) {
        if (banner) {
          banner.textContent = "Aadhaar verification for hospital registering staff is currently turned OFF (pre-deployment mode).";
          banner.classList.remove("hidden");
        }
        card?.classList.add("hidden");
      } else if (!auth.user.aadhaar_verified) {
        card?.classList.remove("hidden");
        banner?.classList.add("hidden");
      } else {
        card?.classList.add("hidden");
        if (banner) {
          banner.textContent = `Authorized representative Aadhaar verified (${auth.user.aadhaar_masked}).`;
          banner.classList.remove("hidden");
        }
      }
    } catch {
      /* non-blocking */
    }
  }
  refreshHospitalAadhaarBanner();

  document.getElementById("hp-aadhaar-btn")?.addEventListener("click", async () => {
    LifeLinkUI.clearAlert("hp-alert");
    const num = (document.getElementById("hp-aadhaar-num")?.value || "").replace(/[\s-]/g, "");
    const consent = Boolean(document.getElementById("hp-aadhaar-consent")?.checked);
    try {
      const updated = await LifeLinkAPI.request("/api/auth/aadhaar/verify", {
        method: "POST",
        body: JSON.stringify({ aadhaar_number: num, aadhaar_consent: consent }),
      });
      LifeLinkAPI.setSession(LifeLinkAPI.getToken(), updated);
      auth.user = updated;
      refreshHospitalAadhaarBanner();
      LifeLinkUI.showAlert("hp-alert", "Hospital representative Aadhaar verified.", "success");
    } catch (err) {
      LifeLinkUI.showAlert("hp-alert", err.message, "error");
    }
  });

  async function loadHospitalProfile() {
    try {
      const data = await LifeLinkAPI.request("/api/hospitals/me");
      const h = data.hospital;
      const badge = document.getElementById("hp-status-badge");
      badge.textContent = LifeLinkUI.formatLabel(h.verification_status);
      badge.className = `badge ${LifeLinkUI.statusBadgeClass(h.verification_status)}`;

      document.getElementById("hp-admin-notes").textContent = h.admin_notes
        ? `Administrator Notes: ${h.admin_notes}`
        : h.badge_disclaimer;

      document.getElementById("hp-name").value = h.hospital_name;
      document.getElementById("hp-reg-no").value = h.registration_number;
      document.getElementById("hp-city").value = h.city;
      document.getElementById("hp-address").value = h.address;
      document.getElementById("hp-phone").value = h.official_phone;
      document.getElementById("hp-email").value = h.official_email || "";
      document.getElementById("hp-rep-name").value = h.authorized_rep_name;
      document.getElementById("hp-rep-role").value = h.authorized_rep_role;

      const docs = data.documents || [];
      document.getElementById("hp-docs-list").innerHTML = docs.length
        ? docs
            .map(
              (d) => `
            <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 10px; display:flex; justify-content:space-between; align-items:center; gap:8px;">
              <div><strong>${LifeLinkUI.escapeHtml(d.document_type)}</strong><div class="form-hint">${new Date(d.created_at).toLocaleString()}</div></div>
              <span class="badge ${LifeLinkUI.statusBadgeClass(d.review_status)}">${LifeLinkUI.formatLabel(d.review_status)}</span>
            </div>
          `
            )
            .join("")
        : `<p class="form-hint" style="margin:0;">No hospital licensing documents uploaded yet.</p>`;

      const hist = data.verification_history || [];
      document.getElementById("hp-history-list").innerHTML = hist.length
        ? hist
            .map(
              (item) => `
            <div style="border-left: 3px solid var(--primary-red); padding-left: 10px;">
              <strong>${LifeLinkUI.formatLabel(item.new_status)}</strong>
              <div class="form-hint">${new Date(item.created_at).toLocaleString()} &middot; ${LifeLinkUI.escapeHtml(item.notes || "")}</div>
            </div>
          `
            )
            .join("")
        : `<p class="form-hint" style="margin:0;">No verification events yet.</p>`;

      if (h.verification_status === "verified" && auth.user.role === "hospital") {
        await loadHospitalRequests();
      } else {
        document.getElementById("hp-requests-list").innerHTML = `
          <div class="alert alert-warning" style="margin:0;">
            Hospital status is <strong>${LifeLinkUI.formatLabel(h.verification_status)}</strong>. Request confirmation and closure actions unlock only after administrator verification.
          </div>
        `;
      }
    } catch {
      document.getElementById("hp-requests-list").innerHTML =
        `<p class="form-hint" style="margin:0;">Submit your hospital registration details first.</p>`;
    }
  }

  async function loadHospitalRequests(manual = false) {
    const el = document.getElementById("hp-requests-list");
    const refreshBtn = document.getElementById("hp-refresh-reqs-btn");
    if (refreshBtn && !refreshBtn.dataset.origText) {
      refreshBtn.dataset.origText = refreshBtn.textContent.trim();
    }
    if (manual && refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.textContent = "Refreshing...";
    }
    try {
      const rows = await LifeLinkAPI.request("/api/hospitals/requests");
      if (!rows.length) {
        el.innerHTML = `<p class="form-hint" style="margin:0;">No active blood requests currently matched to your hospital facility.</p>`;
        return;
      }
      el.innerHTML = rows
        .map(
          (r) => `
        <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px;">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
            <strong>${LifeLinkUI.escapeHtml(r.patient_reference_name)} &middot; ${LifeLinkUI.escapeHtml(r.blood_group)} (${r.units_requested} units)</strong>
            <div>
              <span class="badge ${LifeLinkUI.statusBadgeClass(r.status)}">${LifeLinkUI.formatLabel(r.status)}</span>
              <span class="badge ${r.hospital_verification_status === "confirmed_genuine" ? "badge-success" : "badge-neutral"}">Hospital: ${LifeLinkUI.formatLabel(r.hospital_verification_status || "unconfirmed")}</span>
            </div>
          </div>
          <div class="form-hint">${LifeLinkUI.escapeHtml(r.hospital_name)} (${LifeLinkUI.escapeHtml(r.city)}) &middot; ID: <code>${LifeLinkUI.escapeHtml(r.id)}</code></div>
          ${
            !["fulfilled", "cancelled", "expired"].includes(r.status)
              ? `<div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
                   <button type="button" class="btn btn-primary btn-sm hp-confirm-btn" data-id="${r.id}">Confirm Genuine &amp; Needed</button>
                   <button type="button" class="btn btn-secondary btn-sm hp-close-btn" data-id="${r.id}" data-status="fulfilled">Mark Fulfilled</button>
                   <button type="button" class="btn btn-outline btn-sm hp-close-btn" data-id="${r.id}" data-status="cancelled">Cancel (No Longer Needed)</button>
                   <a href="/pages/request-details.html?id=${encodeURIComponent(r.id)}" class="btn btn-outline btn-sm">Open Tracking</a>
                 </div>`
              : ""
          }
        </div>
      `
        )
        .join("");

      document.querySelectorAll(".hp-confirm-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          LifeLinkUI.clearAlert("hp-alert");
          try {
            await LifeLinkAPI.request(`/api/hospitals/requests/${encodeURIComponent(btn.dataset.id)}/confirm`, {
              method: "POST",
              body: JSON.stringify({
                verification_decision: "confirmed_genuine",
                still_required: true,
                notes: "Confirmed genuine and still required by verified hospital officer.",
              }),
            });
            LifeLinkUI.showAlert("hp-alert", "Request confirmed as genuine.", "success");
            await loadHospitalRequests();
          } catch (err) {
            LifeLinkUI.showAlert("hp-alert", err.message, "error");
          }
        });
      });

      document.querySelectorAll(".hp-close-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          LifeLinkUI.clearAlert("hp-alert");
          const reason = window.prompt(`Reason for marking request as ${btn.dataset.status}:`, "Confirmed by hospital transfusion team");
          if (!reason) return;
          try {
            await LifeLinkAPI.request(`/api/hospitals/requests/${encodeURIComponent(btn.dataset.id)}/close`, {
              method: "POST",
              body: JSON.stringify({ status: btn.dataset.status, reason }),
            });
            LifeLinkUI.showAlert("hp-alert", `Request marked ${btn.dataset.status}.`, "info");
            await loadHospitalRequests();
          } catch (err) {
            LifeLinkUI.showAlert("hp-alert", err.message, "error");
          }
        });
      });
    } catch (err) {
      el.innerHTML = `<div class="alert alert-warning" style="margin:0;">${LifeLinkUI.escapeHtml(err.message)}</div>`;
    } finally {
      if (refreshBtn && manual) {
        refreshBtn.disabled = false;
        refreshBtn.textContent = refreshBtn.dataset.origText || "Refresh Requests";
      }
    }
  }

  document.getElementById("hp-reg-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("hp-alert");
    try {
      await LifeLinkAPI.request("/api/hospitals/me", {
        method: "POST",
        body: JSON.stringify({
          hospital_name: document.getElementById("hp-name").value.trim(),
          registration_number: document.getElementById("hp-reg-no").value.trim(),
          city: document.getElementById("hp-city").value.trim(),
          address: document.getElementById("hp-address").value.trim(),
          official_phone: document.getElementById("hp-phone").value.trim(),
          official_email: document.getElementById("hp-email").value.trim() || null,
          authorized_rep_name: document.getElementById("hp-rep-name").value.trim(),
          authorized_rep_role: document.getElementById("hp-rep-role").value.trim(),
        }),
      });
      LifeLinkUI.showAlert("hp-alert", "Hospital registration submitted for administrator review.", "success");
      await loadHospitalProfile();
    } catch (err) {
      LifeLinkUI.showAlert("hp-alert", err.message, "error");
    }
  });

  document.getElementById("hp-doc-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("hp-alert");
    const fileInput = document.getElementById("hp-doc-file");
    if (!fileInput.files || !fileInput.files[0]) return;
    const fd = new FormData();
    fd.append("document_type", document.getElementById("hp-doc-type").value);
    fd.append("file", fileInput.files[0]);
    try {
      const res = await fetch("/api/hospitals/me/documents/upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${LifeLinkAPI.getToken()}` },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      fileInput.value = "";
      LifeLinkUI.showAlert("hp-alert", "Hospital verification document uploaded.", "success");
      await loadHospitalProfile();
    } catch (err) {
      LifeLinkUI.showAlert("hp-alert", err.message, "error");
    }
  });

  document.getElementById("hp-refresh-reqs-btn").addEventListener("click", () => loadHospitalRequests(true));

  await loadHospitalProfile();
});
