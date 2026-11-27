document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("login");

  try {
    const cfg = await LifeLinkAPI.getPublicConfig();
    if (cfg.dev_auth_mode) {
      LifeLinkUI.showAlert(
        "auth-mode-banner",
        "Local Development Mode active (Supabase credentials not configured). Using local SQLite authentication for demonstration.",
        "info"
      );
    }
  } catch {
    // Non-blocking
  }

  const form = document.getElementById("login-form");
  const submitBtn = document.getElementById("login-submit-btn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("login-alert");
    submitBtn.disabled = true;
    submitBtn.textContent = "Signing in...";

    try {
      const identifier = document.getElementById("login-identifier").value.trim();
      const password = document.getElementById("login-password").value;

      const data = await LifeLinkAPI.request("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ identifier, password }),
      });

      LifeLinkAPI.setSession(data.access_token, data.user);
      window.location.href = data.user.role === "admin" ? "/pages/admin.html" : "/pages/dashboard.html";
    } catch (err) {
      LifeLinkUI.showAlert("login-alert", err.message, "error");
      submitBtn.disabled = false;
      submitBtn.textContent = "Sign In";
    }
  });
});
