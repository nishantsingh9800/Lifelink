document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("dashboard");

  const authResult = await LifeLinkAuth.requireAuth();
  if (!authResult) return;

  const user = authResult.user;
  LifeLinkUI.renderLayout("dashboard");

  document.getElementById("dash-loading").classList.add("hidden");
  document.getElementById("dash-content").classList.remove("hidden");

  function renderProfile(u) {
    document.getElementById("dash-role-badge").textContent = `Role: ${u.role.toUpperCase()}`;
    const verBadge = document.getElementById("dash-verified-badge");
    verBadge.textContent = u.phone_verified ? "Phone Verified" : "Phone Unverified";
    verBadge.className = `badge ${u.phone_verified ? "badge-success" : "badge-warning"}`;

    const aadhaarBadge = document.getElementById("dash-aadhaar-badge");
    aadhaarBadge.textContent = `${u.aadhaar_verified ? "Aadhaar Verified" : "Aadhaar Pending"} (${u.aadhaar_masked || "XXXX-XXXX-0000"})`;
    aadhaarBadge.className = `badge ${u.aadhaar_verified ? "badge-success" : "badge-warning"}`;

    document.getElementById("dash-welcome").textContent = `Welcome, ${u.full_name}`;
    document.getElementById("dash-location-line").textContent = `${u.city} (${u.approximate_location}) · ${u.email || ""}`;

    document.getElementById("prof-name").value = u.full_name;
    document.getElementById("prof-city").value = u.city;
    document.getElementById("prof-location").value = u.approximate_location;
    document.getElementById("prof-phone").value = u.phone_number;
  }

  renderProfile(user);
  if (user.role === "hospital") {
    document.getElementById("dash-hospital-btn")?.classList.remove("hidden");
  }

  async function loadCoordinatorAssignments() {
    const listEl = document.getElementById("dash-coord-list");
    if (!listEl) return;
    try {
      const items = await LifeLinkAPI.request("/api/coordinators/my-assignments");
      if (!items.length) {
        listEl.innerHTML = `<p class="form-hint" style="margin: 0;">No emergency coordinator invitations or assignments.</p>`;
        return;
      }
      listEl.innerHTML = items
        .map(
          (a) => `
          <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;">
            <div>
              <strong>${LifeLinkUI.escapeHtml(a.request_blood_group || "Blood Request")}</strong> &middot; ${LifeLinkUI.escapeHtml(a.request_hospital_name || "")}
              <div class="form-hint">Assignment: <span class="badge ${LifeLinkUI.statusBadgeClass(a.status)}">${LifeLinkUI.formatLabel(a.status)}</span> &middot; Request: ${LifeLinkUI.formatLabel(a.request_status || "active")}</div>
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
              ${
                a.status === "invited"
                  ? `<button type="button" class="btn btn-primary btn-sm coord-resp-btn" data-id="${a.id}" data-accept="true">Accept Assignment</button>
                     <button type="button" class="btn btn-outline btn-sm coord-resp-btn" data-id="${a.id}" data-accept="false">Decline</button>`
                  : ""
              }
              ${
                a.status === "active"
                  ? `<a href="/pages/request-details.html?id=${encodeURIComponent(a.request_id)}" class="btn btn-secondary btn-sm">Open Coordination View</a>`
                  : ""
              }
            </div>
          </div>
        `
        )
        .join("");

      document.querySelectorAll(".coord-resp-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          LifeLinkUI.clearAlert("dash-coord-alert");
          try {
            await LifeLinkAPI.request(`/api/coordinators/${encodeURIComponent(btn.dataset.id)}/respond`, {
              method: "POST",
              body: JSON.stringify({ accept: btn.dataset.accept === "true" }),
            });
            LifeLinkUI.showAlert("dash-coord-alert", "Coordinator response saved.", "success");
            await loadCoordinatorAssignments();
          } catch (err) {
            LifeLinkUI.showAlert("dash-coord-alert", err.message, "error");
          }
        });
      });
    } catch {
      listEl.innerHTML = `<p class="form-hint" style="margin: 0;">Unable to load coordinator assignments.</p>`;
    }
  }
  loadCoordinatorAssignments();

  async function loadFamilyAndPrefs() {
    try {
      const [fam, prefs] = await Promise.all([
        LifeLinkAPI.request("/api/family/contacts"),
        LifeLinkAPI.request("/api/users/me/preferences"),
      ]);
      document.getElementById("pref-in-app").checked = Boolean(prefs.in_app_enabled);
      document.getElementById("pref-quiet-hours").checked = Boolean(prefs.quiet_hours_enabled);
      document.getElementById("pref-emerg-override").checked = Boolean(prefs.emergency_override_quiet_hours);

      const famList = document.getElementById("dash-family-list");
      const rows = [
        ...(fam.granted_by_me || []).map((c) => ({ ...c, dir: "granted" })),
        ...(fam.authorized_for || []).map((c) => ({ ...c, dir: "received" })),
      ];
      famList.innerHTML = rows.length
        ? rows
            .map((c) => {
              const label = c.dir === "granted"
                ? `Authorized: <strong>${LifeLinkUI.escapeHtml(c.member_display_name)}</strong> (${LifeLinkUI.escapeHtml(c.relationship)})`
                : `On Behalf Of: <strong>${LifeLinkUI.escapeHtml(c.owner_display_name)}</strong> (${LifeLinkUI.escapeHtml(c.relationship)})`;
              const actions =
                c.dir === "received" && c.status === "pending"
                  ? `<button type="button" class="btn btn-primary btn-sm fam-resp-btn" data-id="${c.id}" data-accept="true">Accept</button>
                     <button type="button" class="btn btn-outline btn-sm fam-resp-btn" data-id="${c.id}" data-accept="false">Decline</button>`
                  : c.dir === "granted" && (c.status === "active" || c.status === "pending")
                    ? `<button type="button" class="btn btn-outline btn-sm fam-revoke-btn" data-id="${c.id}">Revoke</button>`
                    : "";
              return `
                <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px; display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                  <div>${label} <span class="badge ${LifeLinkUI.statusBadgeClass(c.status)}">${LifeLinkUI.formatLabel(c.status)}</span></div>
                  <div style="display:flex; gap:6px;">${actions}</div>
                </div>
              `;
            })
            .join("")
        : `<p class="form-hint" style="margin:0;">No trusted family contacts linked yet.</p>`;

      document.querySelectorAll(".fam-resp-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await LifeLinkAPI.request(`/api/family/contacts/${encodeURIComponent(btn.dataset.id)}/respond`, {
            method: "POST",
            body: JSON.stringify({ accept: btn.dataset.accept === "true" }),
          });
          await loadFamilyAndPrefs();
        });
      });
      document.querySelectorAll(".fam-revoke-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          await LifeLinkAPI.request(`/api/family/contacts/${encodeURIComponent(btn.dataset.id)}/revoke`, {
            method: "POST",
          });
          LifeLinkUI.showAlert("dash-family-alert", "Family authorization revoked.", "info");
          await loadFamilyAndPrefs();
        });
      });
    } catch {
      /* optional */
    }
  }
  loadFamilyAndPrefs();

  document.getElementById("dash-family-invite-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("dash-family-alert");
    try {
      await LifeLinkAPI.request("/api/family/contacts", {
        method: "POST",
        body: JSON.stringify({
          member_identifier: document.getElementById("fam-identifier").value.trim(),
          relationship: document.getElementById("fam-relation").value.trim(),
        }),
      });
      e.target.reset();
      LifeLinkUI.showAlert("dash-family-alert", "Family member authorization sent.", "success");
      await loadFamilyAndPrefs();
    } catch (err) {
      LifeLinkUI.showAlert("dash-family-alert", err.message, "error");
    }
  });

  document.getElementById("dash-prefs-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("dash-prefs-alert");
    try {
      await LifeLinkAPI.request("/api/users/me/preferences", {
        method: "PATCH",
        body: JSON.stringify({
          in_app_enabled: document.getElementById("pref-in-app").checked,
          quiet_hours_enabled: document.getElementById("pref-quiet-hours").checked,
          emergency_override_quiet_hours: document.getElementById("pref-emerg-override").checked,
        }),
      });
      LifeLinkUI.showAlert("dash-prefs-alert", "Notification preferences saved.", "success");
    } catch (err) {
      LifeLinkUI.showAlert("dash-prefs-alert", err.message, "error");
    }
  });

  async function loadReferrals() {
    const box = document.getElementById("dash-referral-box");
    if (!box) return;
    try {
      const ref = await LifeLinkAPI.request("/api/referrals/me");
      box.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
          <div>
            <strong>Your Referral Code:</strong> <code>${LifeLinkUI.escapeHtml(ref.referral_code)}</code><br/>
            <span class="form-hint">Invite Link: <a href="${LifeLinkUI.escapeHtml(ref.referral_url)}">${LifeLinkUI.escapeHtml(ref.referral_url)}</a></span>
          </div>
          <span class="badge badge-success">${ref.successful_referrals_count} Successful Referral(s)</span>
        </div>
        <p class="form-hint" style="margin: 8px 0 0;">${LifeLinkUI.escapeHtml(ref.anti_abuse_notice)}</p>
      `;
    } catch {
      box.innerHTML = `<span class="form-hint">Referral summary unavailable right now.</span>`;
    }
  }
  loadReferrals();

  // Configure phone verification UI based on public backend config
  const verifyCard = document.getElementById("phone-verify-card");
  if (!user.phone_verified) {
    verifyCard.classList.remove("hidden");
    try {
      const cfg = await LifeLinkAPI.getPublicConfig();
      if (cfg.phone_otp_enabled) {
        document.getElementById("phone-verify-desc").textContent =
          "Verify your phone number via SMS OTP to activate full emergency coordination.";
        document.getElementById("otp-live-controls").classList.remove("hidden");
      } else if (cfg.dev_auth_mode) {
        document.getElementById("phone-verify-desc").textContent =
          "Live SMS OTP is not configured in this local environment. You can complete clearly labelled development-only verification below.";
        document.getElementById("otp-dev-controls").classList.remove("hidden");
      } else {
        document.getElementById("phone-verify-desc").textContent =
          "SMS OTP provider is not yet configured by the administrator.";
      }
    } catch {
      document.getElementById("phone-verify-desc").textContent = "Unable to check OTP configuration.";
    }
  }

  const devVerifyBtn = document.getElementById("dev-verify-phone-btn");
  if (devVerifyBtn) {
    devVerifyBtn.addEventListener("click", async () => {
      LifeLinkUI.clearAlert("phone-verify-alert");
      try {
        const updated = await LifeLinkAPI.request("/api/auth/dev-verify-phone", { method: "POST" });
        LifeLinkAPI.setSession(LifeLinkAPI.getToken(), updated);
        renderProfile(updated);
        verifyCard.classList.add("hidden");
      } catch (err) {
        LifeLinkUI.showAlert("phone-verify-alert", err.message, "error");
      }
    });
  }

  const sendOtpBtn = document.getElementById("send-otp-btn");
  if (sendOtpBtn) {
    sendOtpBtn.addEventListener("click", async () => {
      LifeLinkUI.clearAlert("phone-verify-alert");
      try {
        const res = await LifeLinkAPI.request("/api/auth/otp/send", {
          method: "POST",
          body: JSON.stringify({ phone_number: user.phone_number }),
        });
        LifeLinkUI.showAlert("phone-verify-alert", res.message, "info");
      } catch (err) {
        LifeLinkUI.showAlert("phone-verify-alert", err.message, "error");
      }
    });
  }

  const verifyOtpBtn = document.getElementById("verify-otp-btn");
  if (verifyOtpBtn) {
    verifyOtpBtn.addEventListener("click", async () => {
      LifeLinkUI.clearAlert("phone-verify-alert");
      const code = document.getElementById("otp-code-input").value.trim();
      try {
        await LifeLinkAPI.request("/api/auth/otp/verify", {
          method: "POST",
          body: JSON.stringify({ phone_number: user.phone_number, otp_code: code }),
        });
        const refreshed = await LifeLinkAuth.fetchCurrentUser();
        if (refreshed) renderProfile(refreshed);
        verifyCard.classList.add("hidden");
      } catch (err) {
        LifeLinkUI.showAlert("phone-verify-alert", err.message, "error");
      }
    });
  }

  document.getElementById("profile-update-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("profile-update-alert");
    try {
      const updated = await LifeLinkAPI.request("/api/users/me", {
        method: "PATCH",
        body: JSON.stringify({
          full_name: document.getElementById("prof-name").value.trim(),
          city: document.getElementById("prof-city").value.trim(),
          approximate_location: document.getElementById("prof-location").value.trim(),
        }),
      });
      LifeLinkAPI.setSession(LifeLinkAPI.getToken(), updated);
      renderProfile(updated);
      LifeLinkUI.showAlert("profile-update-alert", "Profile updated successfully.", "success");
    } catch (err) {
      LifeLinkUI.showAlert("profile-update-alert", err.message, "error");
    }
  });
});
