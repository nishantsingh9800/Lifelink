document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("home");
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  const loadingEl = document.getElementById("sr-loading");

  if (!token) {
    loadingEl.classList.add("hidden");
    LifeLinkUI.showAlert("sr-alert", "Missing shared request token.", "error");
    return;
  }

  try {
    const data = await LifeLinkAPI.request(`/api/public/shared/${encodeURIComponent(token)}`);
    loadingEl.classList.add("hidden");
    document.getElementById("sr-body").classList.remove("hidden");
    document.getElementById("sr-group").textContent = `${data.blood_group} · ${data.units_requested} unit(s)`;
    const st = document.getElementById("sr-status");
    st.textContent = LifeLinkUI.formatLabel(data.status);
    st.className = `badge ${LifeLinkUI.statusBadgeClass(data.status)}`;

    const hv = document.getElementById("sr-hosp-ver");
    hv.textContent = `Hospital: ${LifeLinkUI.formatLabel(data.hospital_verification_status)}`;
    hv.className = `badge ${data.hospital_verification_status === "confirmed_genuine" ? "badge-success" : "badge-neutral"}`;

    document.getElementById("sr-hospital").textContent = `${data.hospital_name} (${data.hospital_location})`;
    document.getElementById("sr-city").textContent = `${data.city} · ${data.approximate_location}`;
    document.getElementById("sr-urgency").textContent = LifeLinkUI.formatLabel(data.urgency);
    document.getElementById("sr-expires").textContent = new Date(data.expires_at).toLocaleString();
    document.getElementById("sr-notice").textContent = data.safety_notice;
  } catch (err) {
    loadingEl.classList.add("hidden");
    LifeLinkUI.showAlert("sr-alert", err.message, "error");
  }

  document.getElementById("sr-report-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await LifeLinkAPI.request(`/api/public/shared/${encodeURIComponent(token)}/report`, {
        method: "POST",
        body: JSON.stringify({
          reason: document.getElementById("sr-rep-reason").value.trim(),
          description: document.getElementById("sr-rep-desc").value.trim() || null,
        }),
      });
      LifeLinkUI.showAlert("sr-alert", "Report submitted to moderators for review.", "info");
      e.target.reset();
    } catch (err) {
      LifeLinkUI.showAlert("sr-alert", err.message, "error");
    }
  });
});
