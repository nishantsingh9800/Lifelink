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

  const forgotBtn = document.getElementById("forgot-toggle-btn");
  const forgotPanel = document.getElementById("forgot-panel");
  if (forgotBtn && forgotPanel) {
    forgotBtn.addEventListener("click", () => {
      forgotPanel.classList.toggle("hidden");
      const loginIdent = document.getElementById("login-identifier")?.value.trim();
      const recIdent = document.getElementById("rec-identifier");
      if (loginIdent && recIdent && !recIdent.value) recIdent.value = loginIdent;
    });
  }

  document.getElementById("recover-code-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    LifeLinkUI.clearAlert("recover-alert");
    const recBtn = document.getElementById("rec-submit-btn");
    if (recBtn) {
      recBtn.disabled = true;
      recBtn.textContent = "Resetting...";
    }
    try {
      const data = await LifeLinkAPI.request("/api/auth/recover-with-code", {
        method: "POST",
        body: JSON.stringify({
          identifier: document.getElementById("rec-identifier").value.trim(),
          recovery_code: document.getElementById("rec-code").value.trim(),
          new_password: document.getElementById("rec-new-password").value,
        }),
      });
      LifeLinkAPI.setSession(data.access_token, data.user);
      window.location.href = data.user.role === "admin" ? "/pages/admin.html" : "/pages/dashboard.html";
    } catch (err) {
      LifeLinkUI.showAlert("recover-alert", err.message, "error");
      if (recBtn) {
        recBtn.disabled = false;
        recBtn.textContent = "Reset Password & Sign In";
      }
    }
  });

  document.getElementById("rec-email-btn")?.addEventListener("click", async () => {
    LifeLinkUI.clearAlert("recover-alert");
    const email = document.getElementById("rec-identifier")?.value.trim() || "";
    if (!email.includes("@")) {
      LifeLinkUI.showAlert("recover-alert", "Enter your email address above first to request a reset email.", "warning");
      return;
    }
    try {
      const res = await LifeLinkAPI.request("/api/auth/forgot-password-email", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      LifeLinkUI.showAlert("recover-alert", res.message, res.status === "sent" ? "info" : "warning");
    } catch (err) {
      LifeLinkUI.showAlert("recover-alert", err.message, "error");
    }
  });
});
