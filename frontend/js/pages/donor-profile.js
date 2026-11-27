document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("donor-profile");
  const auth = await LifeLinkAuth.requireAuth();
  if (!auth) return;

  function populate(donor) {
    document.getElementById("dp-blood-group").value = donor.blood_group;
    document.getElementById("dp-availability").value = donor.availability_status;
    document.getElementById("dp-last-donation").value = donor.last_donation_date || "";
    document.getElementById("dp-contact-method").value = donor.preferred_contact_method || "in_app_chat";
    document.getElementById("dp-notifications").checked = Boolean(donor.emergency_notifications_enabled);

    const badge = document.getElementById("dp-ver-badge");
    badge.textContent = LifeLinkUI.formatLabel(donor.verification_status);
    badge.className = `badge ${LifeLinkUI.statusBadgeClass(donor.verification_status)}`;

    document.getElementById("dp-review-note").textContent = donor.eligibility_review_note;

    const freezeBanner = document.getElementById("dp-freeze-banner");
    if (donor.is_frozen && donor.donor_frozen_until) {
      freezeBanner.classList.remove("hidden");
      freezeBanner.textContent =
        `Donor Account Cooldown Active: Your donor profile is frozen until ${donor.donor_frozen_until} ` +
        `(3-month recovery period after donation). You can still log in and submit blood requests as a requester.`;
    } else {
      freezeBanner.classList.add("hidden");
    }

    document.querySelectorAll(".quick-avail-btn").forEach((btn) => {
      if (btn.dataset.status !== "unavailable") {
        btn.disabled = Boolean(donor.is_frozen);
      }
    });
  }

  async function loadMyDocuments() {
    const listEl = document.getElementById("donor-docs-list");
    try {
      const docs = await LifeLinkAPI.request("/api/donors/me/documents");
      if (!docs.length) {
        listEl.innerHTML = `<div class="form-hint">No supporting documents uploaded yet.</div>`;
        return;
      }
      listEl.innerHTML = docs
        .map(
          (d) => `
          <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px; display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
            <div>
              <strong style="font-size: 0.92rem;">${LifeLinkUI.escapeHtml(d.document_type)}</strong>
              <div class="form-hint">Uploaded ${new Date(d.created_at).toLocaleString()}</div>
            </div>
            <span class="badge ${LifeLinkUI.statusBadgeClass(d.review_status)}">${LifeLinkUI.formatLabel(d.review_status)}</span>
          </div>
        `
        )
        .join("");
    } catch {
      listEl.innerHTML = "";
    }
  }

  async function loadCalendar() {
    try {
      const cal = await LifeLinkAPI.request("/api/donors/me/calendar");
      document.getElementById("cal-dates").value = (cal.available_dates || []).join(", ");
      document.getElementById("cal-distance").value = cal.preferred_distance_km || 25;
      document.getElementById("cal-pause-until").value = cal.paused_until || "";
      document.getElementById("cal-qh-start").value = cal.quiet_hours_start || "";
      document.getElementById("cal-qh-end").value = cal.quiet_hours_end || "";
      document.getElementById("dp-cal-updated").textContent = cal.last_availability_updated_at
        ? `Last updated: ${new Date(cal.last_availability_updated_at).toLocaleString()}`
        : "";
    } catch {
      /* ignore when profile not yet created */
    }
  }

  document.getElementById("donor-calendar-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("dp-cal-alert");
    const rawDates = document.getElementById("cal-dates").value;
    const dates = rawDates
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const qStart = document.getElementById("cal-qh-start").value || null;
    const qEnd = document.getElementById("cal-qh-end").value || null;
    try {
      const saved = await LifeLinkAPI.request("/api/donors/me/calendar", {
        method: "PUT",
        body: JSON.stringify({
          availability_status: document.getElementById("dp-availability").value,
          available_dates: dates,
          preferred_distance_km: Number(document.getElementById("cal-distance").value || 25),
          paused_until: document.getElementById("cal-pause-until").value || null,
          quiet_hours_start: qStart,
          quiet_hours_end: qEnd,
        }),
      });
      document.getElementById("dp-cal-updated").textContent = `Last updated: ${new Date(saved.last_availability_updated_at).toLocaleString()}`;
      LifeLinkUI.showAlert("dp-cal-alert", "Availability calendar & quiet hours saved.", "success");
    } catch (err) {
      LifeLinkUI.showAlert("dp-cal-alert", err.message, "error");
    }
  });

  async function loadTrustHistoryAndAppreciation() {
    try {
      const [trust, donHist, appr] = await Promise.all([
        LifeLinkAPI.request("/api/donors/me/trust-profile"),
        LifeLinkAPI.request("/api/donors/me/donations"),
        LifeLinkAPI.request("/api/donors/me/appreciation"),
      ]);
      const vi = trust.verified_indicators;
      const sd = trust.self_declared_indicators;
      document.getElementById("dp-trust-box").innerHTML = `
        <div style="display:grid; gap:6px; font-size:0.9rem;">
          <div><strong>Independently Verified:</strong> Phone ${vi.phone_verified ? "Verified" : "Pending"} &middot; Aadhaar ${vi.aadhaar_verified ? "Verified" : "Pending"} &middot; Docs ${LifeLinkUI.formatLabel(vi.document_verification_status)} &middot; Face ${vi.face_identity_enrolled ? "Enrolled" : "Not Enrolled"} &middot; Facility Donations: ${vi.evidence_backed_donations_count}</div>
          <div><strong>Self-Declared:</strong> Completion ${sd.profile_completion_percent}% &middot; Self-reported Donations: ${sd.self_reported_donations_count}</div>
          <div><strong>Response History:</strong> ${trust.response_summary.accepted_count} accepted / ${trust.response_summary.declined_count} declined (${LifeLinkUI.escapeHtml(trust.response_summary.declining_policy)})</div>
        </div>
        <p class="form-hint" style="margin: 8px 0 0;">${LifeLinkUI.escapeHtml(trust.trust_disclaimer)}</p>
      `;

      document.getElementById("dp-rec-public-cb").checked = Boolean(appr.recognition_public);
      document.getElementById("dp-appreciation-box").innerHTML = `
        <div style="border: 2px solid var(--primary-red); border-radius: var(--radius-md); padding: 12px; background: var(--bg);">
          <strong>${LifeLinkUI.escapeHtml(appr.digital_card.title)}</strong> (${LifeLinkUI.escapeHtml(appr.display_name)} &middot; ${LifeLinkUI.escapeHtml(appr.digital_card.blood_group)})
          <div style="margin: 6px 0; font-size:0.88rem;">Milestones: ${(appr.milestones || []).map((m) => `<span class="badge badge-success" style="margin:2px;">${LifeLinkUI.escapeHtml(m)}</span>`).join("")}</div>
          <div class="form-hint">${LifeLinkUI.escapeHtml(appr.digital_card.disclaimer)}</div>
        </div>
      `;

      const recs = donHist.records || [];
      document.getElementById("dp-donations-list").innerHTML = recs.length
        ? recs
          .map(
            (r) => `
            <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px; display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
              <div>
                <strong>${LifeLinkUI.escapeHtml(r.donation_date)}</strong> &middot; ${LifeLinkUI.formatLabel(r.donation_type)} (${r.guidance_window_days}d guidance) &middot; ${LifeLinkUI.escapeHtml(r.facility_name)}
                <div class="form-hint">${r.evidence_status === "verified_by_facility" ? "Verified by Facility" : "Self-Reported"}${r.is_corrected ? ` &middot; Corrected (${LifeLinkUI.escapeHtml(r.correction_reason || "")})` : ""}</div>
              </div>
              <button type="button" class="btn btn-outline btn-sm dp-correct-rec-btn" data-id="${r.id}">Correct Entry</button>
            </div>
          `
          )
          .join("")
        : `<p class="form-hint" style="margin:0;">No multi-entry donation history records added yet.</p>`;

      document.querySelectorAll(".dp-correct-rec-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const facility = window.prompt("Updated licensed facility name:");
          const reason = window.prompt("Reason for correction:");
          if (!facility || !reason) return;
          try {
            await LifeLinkAPI.request(`/api/donors/me/donations/${encodeURIComponent(btn.dataset.id)}`, {
              method: "PATCH",
              body: JSON.stringify({ facility_name: facility, correction_reason: reason }),
            });
            await loadTrustHistoryAndAppreciation();
          } catch (err) {
            LifeLinkUI.showAlert("dp-donations-alert", err.message, "error");
          }
        });
      });
    } catch {
      /* optional when profile not saved yet */
    }
  }

  document.getElementById("dp-donation-add-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("dp-donations-alert");
    try {
      await LifeLinkAPI.request("/api/donors/me/donations", {
        method: "POST",
        body: JSON.stringify({
          donation_date: document.getElementById("don-rec-date").value,
          donation_type: document.getElementById("don-rec-type").value,
          facility_name: document.getElementById("don-rec-facility").value.trim(),
        }),
      });
      e.target.reset();
      LifeLinkUI.showAlert("dp-donations-alert", "Self-reported donation record added.", "success");
      await loadTrustHistoryAndAppreciation();
    } catch (err) {
      LifeLinkUI.showAlert("dp-donations-alert", err.message, "error");
    }
  });

  document.getElementById("dp-reminder-btn")?.addEventListener("click", async () => {
    try {
      await LifeLinkAPI.request("/api/donors/me/availability-reminder", { method: "POST" });
      LifeLinkUI.showAlert("dp-donations-alert", "Availability review reminder sent to Notifications.", "info");
    } catch (err) {
      LifeLinkUI.showAlert("dp-donations-alert", err.message, "error");
    }
  });

  document.getElementById("dp-rec-public-cb")?.addEventListener("change", async (e) => {
    try {
      await LifeLinkAPI.request("/api/donors/me/appreciation", {
        method: "PATCH",
        body: JSON.stringify({ recognition_public: e.target.checked }),
      });
      await loadTrustHistoryAndAppreciation();
    } catch (err) {
      LifeLinkUI.showAlert("donor-alert", err.message, "error");
    }
  });

  try {
    const donor = await LifeLinkAPI.request("/api/donors/me");
    populate(donor);
    await Promise.all([loadMyDocuments(), loadFaceStatus(), loadCalendar(), loadTrustHistoryAndAppreciation()]);
  } catch (err) {
    if (err.status !== 404) {
      LifeLinkUI.showAlert("donor-alert", err.message, "error");
    }
  }

  document.getElementById("donor-profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("donor-alert");
    const lastDate = document.getElementById("dp-last-donation").value;
    try {
      const saved = await LifeLinkAPI.request("/api/donors/me", {
        method: "PUT",
        body: JSON.stringify({
          blood_group: document.getElementById("dp-blood-group").value,
          availability_status: document.getElementById("dp-availability").value,
          last_donation_date: lastDate || null,
          preferred_contact_method: document.getElementById("dp-contact-method").value,
          emergency_notifications_enabled: document.getElementById("dp-notifications").checked,
        }),
      });
      populate(saved);
      LifeLinkUI.showAlert("donor-alert", "Donor profile saved successfully.", "success");
    } catch (err) {
      LifeLinkUI.showAlert("donor-alert", err.message, "error");
    }
  });

  document.querySelectorAll(".quick-avail-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      LifeLinkUI.clearAlert("donor-alert");
      try {
        const updated = await LifeLinkAPI.request("/api/donors/me/availability", {
          method: "PATCH",
          body: JSON.stringify({ availability_status: btn.dataset.status }),
        });
        populate(updated);
        LifeLinkUI.showAlert("donor-alert", `Availability updated to ${LifeLinkUI.formatLabel(updated.availability_status)}.`, "success");
      } catch (err) {
        LifeLinkUI.showAlert("donor-alert", err.message, "error");
      }
    });
  });

  document.getElementById("dp-record-donation-btn").addEventListener("click", async () => {
    LifeLinkUI.clearAlert("donor-alert");
    try {
      const updated = await LifeLinkAPI.request("/api/donors/me/record-donation", {
        method: "POST",
        body: JSON.stringify({}),
      });
      populate(updated);
      LifeLinkUI.showAlert(
        "donor-alert",
        `Donation recorded! Donor outreach is frozen until ${updated.donor_frozen_until} (3 months).`,
        "success"
      );
    } catch (err) {
      LifeLinkUI.showAlert("donor-alert", err.message, "error");
    }
  });

  const fileInput = document.getElementById("doc-file");
  const fileInfo = document.getElementById("doc-file-info");
  const uploadBtn = document.getElementById("doc-upload-btn");

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      fileInfo.textContent = "No file selected.";
      return;
    }
    const kb = Math.max(1, Math.round(file.size / 1024));
    fileInfo.textContent = `Selected: ${file.name} (${kb} KB)`;
  });

  document.getElementById("donor-doc-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("donor-alert");
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      LifeLinkUI.showAlert("donor-alert", "Please select a document file to upload.", "error");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      LifeLinkUI.showAlert("donor-alert", "File exceeds the 5 MB limit.", "error");
      return;
    }

    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";
    try {
      const formData = new FormData();
      formData.append("document_type", document.getElementById("doc-type").value);
      formData.append("file", file);

      await LifeLinkAPI.request("/api/donors/me/documents/upload", {
        method: "POST",
        body: formData,
      });
      const refreshed = await LifeLinkAPI.request("/api/donors/me");
      populate(refreshed);
      await loadMyDocuments();
      e.target.reset();
      fileInfo.textContent = "No file selected.";
      LifeLinkUI.showAlert("donor-alert", "Document uploaded and submitted for administrator review.", "success");
    } catch (err) {
      LifeLinkUI.showAlert("donor-alert", err.message, "error");
    } finally {
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Upload Document for Review";
    }
  });

  // --- Face Identity Enrollment & Verification ---
  let activeStream = null;
  const videoEl = document.getElementById("face-video");
  const canvasEl = document.getElementById("face-canvas");
  const camWrap = document.getElementById("face-camera-wrap");
  const captureEnrollBtn = document.getElementById("face-capture-enroll-btn");
  const testVerifyBtn = document.getElementById("face-test-verify-btn");
  const faceBadge = document.getElementById("face-enroll-badge");

  async function loadFaceStatus() {
    try {
      const st = await LifeLinkAPI.request("/api/donors/me/face");
      if (st.enrolled) {
        faceBadge.textContent = "Face Enrolled";
        faceBadge.className = "badge badge-success";
      } else {
        faceBadge.textContent = "Not Enrolled";
        faceBadge.className = "badge badge-warning";
      }
    } catch {
      // Non-blocking
    }
  }

  function captureVideoBase64() {
    canvasEl.width = videoEl.videoWidth || 480;
    canvasEl.height = videoEl.videoHeight || 360;
    canvasEl.getContext("2d").drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);
    return canvasEl.toDataURL("image/jpeg", 0.92);
  }

  function readFileBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error("Could not read selected image file."));
      reader.readAsDataURL(file);
    });
  }

  document.getElementById("face-start-cam-btn").addEventListener("click", async () => {
    LifeLinkUI.clearAlert("face-enroll-alert");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      LifeLinkUI.showAlert("face-enroll-alert", "Camera access is unavailable in this browser. Use the photo upload option below.", "warning");
      return;
    }
    try {
      activeStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
      videoEl.srcObject = activeStream;
      camWrap.classList.remove("hidden");
      captureEnrollBtn.classList.remove("hidden");
      testVerifyBtn.classList.remove("hidden");
    } catch (err) {
      LifeLinkUI.showAlert("face-enroll-alert", `Unable to access camera: ${err.message}`, "error");
    }
  });

  async function submitFaceEnroll(imageBase64) {
    LifeLinkUI.clearAlert("face-enroll-alert");
    if (!document.getElementById("face-consent-cb").checked) {
      LifeLinkUI.showAlert("face-enroll-alert", "Please check the biometric consent box before enrolling.", "error");
      return;
    }
    try {
      const res = await LifeLinkAPI.request("/api/donors/me/face/enroll", {
        method: "POST",
        body: JSON.stringify({ image_base64: imageBase64, consent_given: true }),
      });
      await loadFaceStatus();
      LifeLinkUI.showAlert("face-enroll-alert", res.message, "success");
    } catch (err) {
      LifeLinkUI.showAlert("face-enroll-alert", err.message, "error");
    }
  }

  async function submitFaceVerify(imageBase64) {
    LifeLinkUI.clearAlert("face-enroll-alert");
    try {
      const res = await LifeLinkAPI.request("/api/donors/me/face/verify", {
        method: "POST",
        body: JSON.stringify({ image_base64: imageBase64 }),
      });
      const pct = Math.round(res.similarity_score * 100);
      LifeLinkUI.showAlert(
        "face-enroll-alert",
        `${res.message} (Similarity: ${pct}% · Threshold: ${Math.round(res.threshold * 100)}%)`,
        res.verified ? "success" : "error"
      );
    } catch (err) {
      LifeLinkUI.showAlert("face-enroll-alert", err.message, "error");
    }
  }

  captureEnrollBtn.addEventListener("click", () => submitFaceEnroll(captureVideoBase64()));
  testVerifyBtn.addEventListener("click", () => submitFaceVerify(captureVideoBase64()));

  document.getElementById("face-file-enroll-btn").addEventListener("click", async () => {
    const f = document.getElementById("face-file-input").files?.[0];
    if (!f) {
      LifeLinkUI.showAlert("face-enroll-alert", "Select a front-facing photo first.", "error");
      return;
    }
    await submitFaceEnroll(await readFileBase64(f));
  });

  document.getElementById("face-file-verify-btn").addEventListener("click", async () => {
    const f = document.getElementById("face-file-input").files?.[0];
    if (!f) {
      LifeLinkUI.showAlert("face-enroll-alert", "Select a photo to verify against your enrolled face.", "error");
      return;
    }
    await submitFaceVerify(await readFileBase64(f));
  });
});
