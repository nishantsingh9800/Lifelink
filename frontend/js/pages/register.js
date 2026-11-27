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
