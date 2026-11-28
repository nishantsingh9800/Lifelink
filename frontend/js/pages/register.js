document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("register");

  const roleSelect = document.getElementById("reg-role");
  const bloodGroupWrap = document.getElementById("reg-blood-group-wrap");
  const bloodGroupSelect = document.getElementById("reg-blood-group");

  const refParam = new URLSearchParams(window.location.search).get("ref");
  const refInput = document.getElementById("reg-referral");
  if (refParam && refInput) refInput.value = refParam;

  function syncRoleFields() {
    const isDonor = roleSelect.value === "donor";
    bloodGroupWrap.classList.toggle("hidden", !isDonor);
    bloodGroupSelect.required = isDonor;
  }

  roleSelect.addEventListener("change", syncRoleFields);
  syncRoleFields();

  try {
    const cfg = await LifeLinkAPI.getPublicConfig();
    if (cfg.dev_auth_mode) {
      LifeLinkUI.showAlert(
        "register-mode-banner",
        "Local Development Mode active. You can register and sign in without Aadhaar while Aadhaar e-KYC is turned off.",
        "info"
      );
    }
  } catch {
    // Non-blocking
  }

  const form = document.getElementById("register-form");
  const submitBtn = document.getElementById("reg-submit-btn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("register-alert");
    submitBtn.disabled = true;
    submitBtn.textContent = "Creating account...";

    try {
      const dobVal = document.getElementById("reg-dob").value;
      const roleVal = roleSelect.value;

      const payload = {
        full_name: document.getElementById("reg-name").value.trim(),
        email: document.getElementById("reg-email").value.trim(),
        phone_number: document.getElementById("reg-phone").value.trim(),
        password: document.getElementById("reg-password").value,
        date_of_birth: dobVal || null,
        city: document.getElementById("reg-city").value.trim(),
        approximate_location: document.getElementById("reg-location").value.trim(),
        role_preference: roleVal,
        blood_group: roleVal === "donor" ? bloodGroupSelect.value : null,
        referral_code: document.getElementById("reg-referral")?.value.trim() || null,
        terms_accepted: document.getElementById("reg-terms").checked,
      };

      const data = await LifeLinkAPI.request("/api/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      if (data.access_token) {
        LifeLinkAPI.setSession(data.access_token, data.user);
      }

      const codes = data.recovery_codes || [];
      const recoveryPanel = document.getElementById("reg-recovery-panel");
      if (codes.length && recoveryPanel) {
        form.classList.add("hidden");
        recoveryPanel.classList.remove("hidden");
        const listEl = document.getElementById("reg-recovery-codes-list");
        if (listEl) {
          listEl.innerHTML = codes
            .map(
              (c) => `<div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px; text-align: center; background: #fff; font-weight: 700;">${LifeLinkUI.escapeHtml(c)}</div>`
            )
            .join("");
        }
        const codesText = `LifeLink Backup Recovery Codes (${payload.email}):\n\n${codes.join("\n")}\n\nEach code can be used once on Login -> Forgot Password.`;
        document.getElementById("reg-copy-codes-btn")?.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(codesText);
            document.getElementById("reg-copy-codes-btn").textContent = "Copied!";
          } catch {
            /* clipboard fallback ignored */
          }
        });
        document.getElementById("reg-download-codes-btn")?.addEventListener("click", () => {
          const blob = new Blob([codesText], { type: "text/plain" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "lifelink-recovery-codes.txt";
          a.click();
          URL.revokeObjectURL(url);
        });
        document.getElementById("reg-continue-btn")?.addEventListener("click", () => {
          if (data.access_token) {
            window.location.href = "/pages/dashboard.html";
          } else {
            window.location.href = "/pages/login.html";
          }
        });
      } else if (data.access_token) {
        window.location.href = "/pages/dashboard.html";
      } else {
        LifeLinkUI.showAlert("register-alert", data.message, "success");
        submitBtn.disabled = false;
        submitBtn.textContent = "Create Verified Account";
      }
    } catch (err) {
      LifeLinkUI.showAlert("register-alert", err.message, "error");
      submitBtn.disabled = false;
      submitBtn.textContent = "Create Verified Account";
    }
  });
});
