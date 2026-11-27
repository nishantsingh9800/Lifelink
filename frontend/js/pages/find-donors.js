document.addEventListener("DOMContentLoaded", () => {
  LifeLinkUI.renderLayout("find-donors");

  const form = document.getElementById("donor-search-form");
  const resultsEl = document.getElementById("donor-results-container");

  async function runSearch() {
    LifeLinkUI.clearAlert("donor-search-alert");
    resultsEl.innerHTML = `<div class="card">Searching registered potential donors...</div>`;

    const bloodGroup = document.getElementById("search-blood-group").value;
    const city = document.getElementById("search-city").value.trim();

    const params = new URLSearchParams();
    if (bloodGroup) params.set("blood_group", bloodGroup);
    if (city) params.set("city", city);

    try {
      const donors = await LifeLinkAPI.request(`/api/public/donors?${params.toString()}`);
      if (!donors.length) {
        resultsEl.innerHTML = `
          <div class="empty-state">
            <h3>No available potential donors matched your filters</h3>
            <p>
              LifeLink never displays fabricated donors. If you have an active medical need,
              check the <a href="/pages/blood-banks.html">Blood-Bank Directory</a> or contact the
              treating hospital's blood bank directly.
            </p>
          </div>
        `;
        return;
      }

      const cards = donors
        .map(
          (d) => `
          <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
              <strong style="font-size: 1.05rem;">${LifeLinkUI.escapeHtml(d.display_name)}</strong>
              <span class="badge badge-red">${LifeLinkUI.escapeHtml(d.blood_group)}</span>
            </div>
            <p style="margin: 8px 0; color: var(--text-secondary); font-size: 0.92rem;">
              ${LifeLinkUI.escapeHtml(d.city)} &middot; ${LifeLinkUI.escapeHtml(d.approximate_location)}
            </p>
            <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px;">
              <span class="badge badge-neutral">Status: ${LifeLinkUI.escapeHtml(d.availability_status.replace(/_/g, " "))}</span>
              <span class="badge ${d.verification_status === "verified" ? "badge-success" : "badge-warning"}">
                ${LifeLinkUI.escapeHtml(d.verification_status.replace(/_/g, " "))}
              </span>
            </div>
            <p class="form-hint" style="margin-top: 10px; margin-bottom: 0;">${LifeLinkUI.escapeHtml(d.match_label)}</p>
          </div>
        `
        )
        .join("");

      resultsEl.innerHTML = `<div class="grid-3">${cards}</div>`;
    } catch (err) {
      resultsEl.innerHTML = "";
      LifeLinkUI.showAlert("donor-search-alert", err.message, "error");
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    runSearch();
  });

  runSearch();
});
