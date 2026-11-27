document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("create-request");
  const auth = await LifeLinkAuth.requireAuth();
  if (!auth) return;

  const params = new URLSearchParams(window.location.search);
  if (params.get("blood_group")) document.getElementById("req-blood-group").value = params.get("blood_group");
  if (params.get("city")) document.getElementById("req-city").value = params.get("city");
  if (params.get("hospital_name")) document.getElementById("req-hospital").value = params.get("hospital_name");
  if (params.get("urgency")) document.getElementById("req-urgency").value = params.get("urgency");

  const form = document.getElementById("create-request-form");
  const submitBtn = document.getElementById("req-submit-btn");
  const reviewBtn = document.getElementById("req-review-btn");
  const reviewPanel = document.getElementById("req-review-panel");
  const confirmPanel = document.getElementById("req-confirmation-panel");
  const confirmSubmitBtn = document.getElementById("req-confirm-submit-btn");
  let isSubmitting = false;

  try {
    const cfg = await LifeLinkAPI.getPublicConfig();
    if (!cfg.require_aadhaar_for_actions) {
      const note = document.getElementById("req-aadhaar-off-note");
      if (note) {
        note.textContent = "Aadhaar verification when requesting/receiving blood is currently turned OFF (pre-deployment mode).";
        note.classList.remove("hidden");
      }
    } else if (!auth.user.aadhaar_verified) {
      document.getElementById("req-aadhaar-verify-card")?.classList.remove("hidden");
    }
  } catch {
    /* non-blocking */
  }

  document.getElementById("req-aadhaar-btn")?.addEventListener("click", async () => {
    LifeLinkUI.clearAlert("req-form-alert");
    const num = (document.getElementById("req-aadhaar-num")?.value || "").replace(/[\s-]/g, "");
    const consent = Boolean(document.getElementById("req-aadhaar-consent")?.checked);
    try {
      const updated = await LifeLinkAPI.request("/api/auth/aadhaar/verify", {
        method: "POST",
        body: JSON.stringify({ aadhaar_number: num, aadhaar_consent: consent }),
      });
      LifeLinkAPI.setSession(LifeLinkAPI.getToken(), updated);
      auth.user = updated;
      document.getElementById("req-aadhaar-verify-card")?.classList.add("hidden");
      LifeLinkUI.showAlert("req-form-alert", "Aadhaar verified. You can now submit your blood request.", "success");
    } catch (err) {
      LifeLinkUI.showAlert("req-form-alert", err.message, "error");
    }
  });

  // Populate authorized family accounts if user has any active family permissions
  try {
    const fam = await LifeLinkAPI.request("/api/family/contacts");
    const activeBehalf = (fam.authorized_for || []).filter((c) => c.status === "active" && c.can_create_requests);
    if (activeBehalf.length) {
      document.getElementById("req-behalf-wrap")?.classList.remove("hidden");
      const sel = document.getElementById("req-behalf-select");
      activeBehalf.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c.owner_user_id;
        opt.textContent = `${c.owner_display_name} (${c.relationship})`;
        sel.appendChild(opt);
      });
    }
  } catch {
    /* optional */
  }

  function buildPayload() {
    const whenVal = document.getElementById("req-when").value;
    const coordName = document.getElementById("req-coord-name")?.value.trim() || null;
    const coordRel = document.getElementById("req-coord-rel")?.value.trim() || null;
    const onBehalf = document.getElementById("req-behalf-select")?.value || null;
    return {
      patient_reference_name: document.getElementById("req-patient").value.trim(),
      blood_group: document.getElementById("req-blood-group").value,
      units_requested: Number(document.getElementById("req-units").value),
      hospital_name: document.getElementById("req-hospital").value.trim(),
      hospital_location: document.getElementById("req-hospital-loc").value.trim(),
      city: document.getElementById("req-city").value.trim(),
      approximate_location: document.getElementById("req-approx-loc").value.trim(),
      urgency: document.getElementById("req-urgency").value,
      requester_contact_preference: document.getElementById("req-contact-pref").value,
      additional_information: document.getElementById("req-notes").value.trim() || null,
      requested_for: whenVal ? new Date(whenVal).toISOString() : null,
      is_emergency_quick: Boolean(document.getElementById("req-quick-mode")?.checked),
      coordinator_contact_name: coordName,
      coordinator_contact_relation: coordRel,
      on_behalf_of_user_id: onBehalf,
      consent_given: document.getElementById("req-consent").checked,
    };
  }

  function showReviewSummary() {
    if (!form.reportValidity()) return;
    LifeLinkUI.clearAlert("req-form-alert");
    const p = buildPayload();
    document.getElementById("req-review-summary").innerHTML = `
      <div><strong>Patient / Reference:</strong> ${LifeLinkUI.escapeHtml(p.patient_reference_name)}</div>
      <div><strong>Blood Group &amp; Units:</strong> ${LifeLinkUI.escapeHtml(p.blood_group)} &middot; ${p.units_requested} unit(s)</div>
      <div><strong>Hospital:</strong> ${LifeLinkUI.escapeHtml(p.hospital_name)} (${LifeLinkUI.escapeHtml(p.hospital_location)})</div>
      <div><strong>City &amp; Area:</strong> ${LifeLinkUI.escapeHtml(p.city)} &middot; ${LifeLinkUI.escapeHtml(p.approximate_location)}</div>
      <div><strong>Urgency:</strong> ${LifeLinkUI.formatLabel(p.urgency)} (not medically verified until hospital confirms)</div>
      ${p.coordinator_contact_name ? `<div><strong>Coordinator / Attendant:</strong> ${LifeLinkUI.escapeHtml(p.coordinator_contact_name)} (${LifeLinkUI.escapeHtml(p.coordinator_contact_relation || "Family")})</div>` : ""}
    `;
    reviewPanel.classList.remove("hidden");
    reviewPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function submitRequest() {
    if (isSubmitting) return;
    if (!form.reportValidity()) return;
    LifeLinkUI.clearAlert("req-form-alert");
    isSubmitting = true;
    submitBtn.disabled = true;
    confirmSubmitBtn.disabled = true;
    submitBtn.textContent = "Submitting request...";
    confirmSubmitBtn.textContent = "Submitting...";

    try {
      const created = await LifeLinkAPI.request("/api/requests", {
        method: "POST",
        body: JSON.stringify(buildPayload()),
      });
      let matchResult = null;
      try {
        matchResult = await LifeLinkAPI.request(`/api/matching/${encodeURIComponent(created.id)}/run`, {
          method: "POST",
        });
      } catch {
        /* Non-fatal: user can still trigger matching from request details */
      }
      const displayStatus = matchResult?.status || created.status;
      const notifiedCount = Number(matchResult?.notified_count || 0);
      form.classList.add("hidden");
      reviewPanel.classList.add("hidden");
      confirmPanel.classList.remove("hidden");
      document.getElementById("req-confirm-details").innerHTML = `
        <strong>Request ID:</strong> <code>${LifeLinkUI.escapeHtml(created.id)}</code><br/>
        <strong>Current Status:</strong> <span class="badge ${LifeLinkUI.statusBadgeClass(displayStatus)}">${LifeLinkUI.formatLabel(displayStatus)}</span><br/>
        <strong>Donors Notified Immediately:</strong> ${notifiedCount} eligible donor(s) alerted
        ${matchResult?.message ? `<div class="form-hint" style="margin-top:6px;">${LifeLinkUI.escapeHtml(matchResult.message)}</div>` : ""}
      `;
      document.getElementById("req-confirm-safety").textContent = created.safety_notice;
      document.getElementById("req-track-link").href = `/pages/request-details.html?id=${encodeURIComponent(created.id)}`;
    } catch (err) {
      LifeLinkUI.showAlert("req-form-alert", err.message, "error");
      submitBtn.disabled = false;
      confirmSubmitBtn.disabled = false;
      submitBtn.textContent = "Submit Blood Request";
      confirmSubmitBtn.textContent = "Confirm & Submit Request";
      isSubmitting = false;
    }
  }

  reviewBtn.addEventListener("click", showReviewSummary);
  document.getElementById("req-edit-btn").addEventListener("click", () => {
    reviewPanel.classList.add("hidden");
  });
  confirmSubmitBtn.addEventListener("click", submitRequest);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await submitRequest();
  });
});
