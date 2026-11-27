document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("incoming-requests");
  const auth = await LifeLinkAuth.requireAuth();
  if (!auth) return;

  const listEl = document.getElementById("incoming-list");
  const gateBanner = document.getElementById("face-gate-banner");
  const verifyPanel = document.getElementById("face-verify-panel");
  const videoEl = document.getElementById("inc-face-video");
  const canvasEl = document.getElementById("inc-face-canvas");
  const captureBtn = document.getElementById("inc-capture-accept-btn");

  let faceEnrolled = false;
  let pendingAcceptRequestId = "";
  let camStream = null;
  let watchId = null;

  function stopCam() {
    if (camStream) {
      camStream.getTracks().forEach((t) => t.stop());
      camStream = null;
    }
    videoEl.classList.add("hidden");
    captureBtn.classList.add("hidden");
  }

  function getMandatoryBrowserLocation() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("Browser geolocation is required to accept a blood request."));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
        () => reject(new Error("Location access is mandatory to accept a request. Please allow location permission and try again.")),
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
      );
    });
  }

  async function refreshAadhaarBanner() {
    try {
      const cfg = await LifeLinkAPI.getPublicConfig();
      const banner = document.getElementById("inc-aadhaar-banner");
      const card = document.getElementById("inc-aadhaar-card");
      if (!cfg.require_aadhaar_for_actions) {
        if (banner) {
          banner.textContent = "Aadhaar verification when donating is currently turned OFF (pre-deployment mode).";
          banner.classList.remove("hidden");
        }
        card?.classList.add("hidden");
      } else if (!auth.user.aadhaar_verified) {
        card?.classList.remove("hidden");
        banner?.classList.add("hidden");
      } else {
        card?.classList.add("hidden");
        if (banner) {
          banner.textContent = `Aadhaar verified (${auth.user.aadhaar_masked}) for blood donation.`;
          banner.classList.remove("hidden");
        }
      }
    } catch {
      /* non-blocking */
    }
  }
  refreshAadhaarBanner();

  document.getElementById("inc-aadhaar-btn")?.addEventListener("click", async () => {
    LifeLinkUI.clearAlert("incoming-alert");
    const num = (document.getElementById("inc-aadhaar-num")?.value || "").replace(/[\s-]/g, "");
    const consent = Boolean(document.getElementById("inc-aadhaar-consent")?.checked);
    try {
      const updated = await LifeLinkAPI.request("/api/auth/aadhaar/verify", {
        method: "POST",
        body: JSON.stringify({ aadhaar_number: num, aadhaar_consent: consent }),
      });
      LifeLinkAPI.setSession(LifeLinkAPI.getToken(), updated);
      auth.user = updated;
      refreshAadhaarBanner();
      LifeLinkUI.showAlert("incoming-alert", "Aadhaar verified for blood donation.", "success");
    } catch (err) {
      LifeLinkUI.showAlert("incoming-alert", err.message, "error");
    }
  });

  async function refreshFaceBanner() {
    try {
      const st = await LifeLinkAPI.request("/api/donors/me/face");
      faceEnrolled = Boolean(st.enrolled);
      gateBanner.classList.remove("hidden");
      if (faceEnrolled) {
        gateBanner.className = "alert alert-info";
        gateBanner.textContent =
          "Face identity verification is active on your profile. Accepting a request requires a quick live selfie check and location permission.";
      } else {
        gateBanner.className = "alert alert-warning";
        gateBanner.innerHTML =
          `Face verification not yet enrolled. <a href="/pages/donor-profile.html">Enroll your face on Donor Profile</a> to protect against donor impersonation.`;
      }
    } catch {
      gateBanner.classList.add("hidden");
    }
  }

  async function submitResponse(requestId, responseValue, faceBase64 = null) {
    LifeLinkUI.clearAlert("incoming-alert");
    try {
      let coords = { latitude: null, longitude: null };
      if (responseValue === "accepted") {
        coords = await getMandatoryBrowserLocation();
      }
      const res = await LifeLinkAPI.request(`/api/responses/${encodeURIComponent(requestId)}/respond`, {
        method: "POST",
        body: JSON.stringify({
          response: responseValue,
          face_image_base64: faceBase64,
          latitude: coords.latitude,
          longitude: coords.longitude,
        }),
      });
      verifyPanel.classList.add("hidden");
      stopCam();
      LifeLinkUI.showAlert(
        "incoming-alert",
        res.response === "accepted"
          ? "Acceptance recorded and your ~1 km privacy-safe arrival radius is now shared with the requester."
          : "Your 'NOT AVAILABLE' response has been recorded.",
        "success"
      );
      await loadIncoming();
    } catch (err) {
      LifeLinkUI.showAlert("incoming-alert", err.message, "error");
    }
  }

  async function sendTrackingUpdate(requestId, trackingStatus) {
    LifeLinkUI.clearAlert("incoming-alert");
    try {
      const coords = await getMandatoryBrowserLocation();
      await LifeLinkAPI.request(`/api/tracking/${encodeURIComponent(requestId)}/update`, {
        method: "POST",
        body: JSON.stringify({
          latitude: coords.latitude,
          longitude: coords.longitude,
          tracking_status: trackingStatus,
        }),
      });
      LifeLinkUI.showAlert(
        "incoming-alert",
        `Arrival status updated to '${LifeLinkUI.formatLabel(trackingStatus)}' (~1 km safety radius only).`,
        "success"
      );
    } catch (err) {
      LifeLinkUI.showAlert("incoming-alert", err.message, "error");
    }
  }

  document.getElementById("inc-start-cam-btn").addEventListener("click", async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      LifeLinkUI.showAlert("incoming-alert", "Camera unavailable. Use the verification photo selector instead.", "warning");
      return;
    }
    try {
      camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
      videoEl.srcObject = camStream;
      videoEl.classList.remove("hidden");
      captureBtn.classList.remove("hidden");
    } catch (err) {
      LifeLinkUI.showAlert("incoming-alert", `Camera error: ${err.message}`, "error");
    }
  });

  captureBtn.addEventListener("click", async () => {
    if (!pendingAcceptRequestId) return;
    canvasEl.width = videoEl.videoWidth || 480;
    canvasEl.height = videoEl.videoHeight || 360;
    canvasEl.getContext("2d").drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);
    const b64 = canvasEl.toDataURL("image/jpeg", 0.92);
    await submitResponse(pendingAcceptRequestId, "accepted", b64);
  });

  document.getElementById("inc-file-accept-btn").addEventListener("click", async () => {
    if (!pendingAcceptRequestId) return;
    const f = document.getElementById("inc-face-file").files?.[0];
    if (!f) {
      LifeLinkUI.showAlert("incoming-alert", "Select a front-facing photo or use the camera.", "error");
      return;
    }
    const b64 = await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result));
      r.onerror = () => reject(new Error("Could not read image."));
      r.readAsDataURL(f);
    });
    await submitResponse(pendingAcceptRequestId, "accepted", b64);
  });

  document.getElementById("inc-cancel-face-btn").addEventListener("click", () => {
    pendingAcceptRequestId = "";
    verifyPanel.classList.add("hidden");
    stopCam();
  });

  async function loadIncoming() {
    listEl.innerHTML = `<div class="card">Loading incoming donor alerts...</div>`;
    try {
      const items = await LifeLinkAPI.request("/api/responses/incoming");
      if (!items.length) {
        listEl.innerHTML = `
          <div class="empty-state">
            <h3>No incoming blood request alerts</h3>
            <p>Make sure your <a href="/pages/donor-profile.html">Donor Profile</a> is active and available to receive relevant alerts.</p>
          </div>
        `;
        return;
      }

      listEl.innerHTML = `<div class="grid-2">${items
        .map((item) => {
          const isClosed = ["fulfilled", "unresolved", "cancelled", "expired"].includes(item.request_status);
          const chatBtn = item.conversation_id
            ? `<a href="/pages/messages.html?conversation_id=${encodeURIComponent(item.conversation_id)}" class="btn btn-secondary btn-sm">Open Private Chat</a>`
            : "";

          const trackingControls =
            !isClosed && item.my_response === "accepted"
              ? `
              <div style="margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); display: flex; gap: 6px; flex-wrap: wrap;">
                <button type="button" class="btn btn-outline btn-sm track-upd-btn" data-id="${item.request_id}" data-status="en_route">Share: En Route</button>
                <button type="button" class="btn btn-outline btn-sm track-upd-btn" data-id="${item.request_id}" data-status="nearby">Share: Nearby</button>
                <button type="button" class="btn btn-primary btn-sm track-upd-btn" data-id="${item.request_id}" data-status="arrived_at_hospital">Arrived at Hospital</button>
                <button type="button" class="btn btn-outline btn-sm track-stop-btn" data-id="${item.request_id}">Stop Sharing</button>
              </div>
              `
              : "";

          const actions = isClosed
            ? `<span class="badge badge-neutral">Request ${LifeLinkUI.formatLabel(item.request_status)}</span>`
            : `
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button type="button" class="btn btn-primary btn-sm respond-btn" data-id="${item.request_id}" data-resp="accepted">
                  ${faceEnrolled ? "Verify Face, Location &amp; Accept" : "Enable Location &amp; Accept"}
                </button>
                <button type="button" class="btn btn-outline btn-sm respond-btn" data-id="${item.request_id}" data-resp="declined">
                  NOT AVAILABLE
                </button>
                ${chatBtn}
              </div>
              ${trackingControls}
            `;

          return `
            <div class="card">
              <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <strong>${LifeLinkUI.escapeHtml(item.hospital_name)}</strong>
                <span class="badge badge-red">${LifeLinkUI.escapeHtml(item.blood_group)} &middot; ${item.units_requested} unit(s)</span>
              </div>
              <p style="margin: 8px 0; color: var(--text-secondary); font-size: 0.92rem;">
                ${LifeLinkUI.escapeHtml(item.city)} &middot; ${LifeLinkUI.escapeHtml(item.approximate_location)}
              </p>
              <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px;">
                <span class="badge ${LifeLinkUI.statusBadgeClass(item.urgency)}">${LifeLinkUI.formatLabel(item.urgency)}</span>
                <span class="badge ${LifeLinkUI.statusBadgeClass(item.request_status)}">${LifeLinkUI.formatLabel(item.request_status)}</span>
                ${item.my_response ? `<span class="badge ${LifeLinkUI.statusBadgeClass(item.my_response)}">Your response: ${LifeLinkUI.formatLabel(item.my_response)}</span>` : ""}
              </div>
              <p class="form-hint" style="margin-bottom: 14px;">Match basis: ${LifeLinkUI.escapeHtml(item.match_reason)}</p>
              ${actions}
            </div>
          `;
        })
        .join("")}</div>`;

      document.querySelectorAll(".respond-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const reqId = btn.dataset.id;
          const respVal = btn.dataset.resp;
          if (respVal === "accepted" && faceEnrolled) {
            pendingAcceptRequestId = reqId;
            verifyPanel.classList.remove("hidden");
            verifyPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
            return;
          }
          await submitResponse(reqId, respVal);
        });
      });

      document.querySelectorAll(".track-upd-btn").forEach((btn) => {
        btn.addEventListener("click", () => sendTrackingUpdate(btn.dataset.id, btn.dataset.status));
      });

      document.querySelectorAll(".track-stop-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          if (watchId !== null && navigator.geolocation) {
            navigator.geolocation.clearWatch(watchId);
            watchId = null;
          }
          await LifeLinkAPI.request(`/api/tracking/${encodeURIComponent(btn.dataset.id)}/stop`, { method: "POST" });
          LifeLinkUI.showAlert("incoming-alert", "Live radius sharing stopped.", "info");
        });
      });
    } catch (err) {
      listEl.innerHTML = "";
      LifeLinkUI.showAlert("incoming-alert", err.message, "error");
    }
  }

  await refreshFaceBanner();
  await loadIncoming();
});
