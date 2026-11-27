document.addEventListener("DOMContentLoaded", () => {
  LifeLinkUI.renderLayout("blood-banks");

  const form = document.getElementById("bb-search-form");
  const cityInput = document.getElementById("bb-city");
  const typeSelect = document.getElementById("bb-type-filter");
  const queryInput = document.getElementById("bb-query");
  const gpsBtn = document.getElementById("bb-gps-btn");
  const resultsEl = document.getElementById("bb-results-container");
  const sourceMetaEl = document.getElementById("bb-source-meta");
  const liveNoteEl = document.getElementById("bb-live-stock-note");
  const gmapsNearbyEl = document.getElementById("bb-gmaps-nearby-link");
  const urlParams = new URLSearchParams(window.location.search);
  const linkedRequestId = urlParams.get("request_id") || "";

  let gpsCoords = null;

  if (urlParams.get("city")) {
    cityInput.value = urlParams.get("city");
  } else {
    const stored = LifeLinkAPI.getStoredUser();
    if (stored?.city) {
      cityInput.value = stored.city;
    }
  }
  if (urlParams.get("q")) {
    queryInput.value = urlParams.get("q");
  }

  function formatTypeLabel(fType) {
    return fType === "blood_bank" ? "Blood Bank" : "Hospital";
  }

  async function runSearch() {
    LifeLinkUI.clearAlert("bb-search-alert");
    const searchBtn = document.getElementById("bb-search-btn");
    if (searchBtn && !searchBtn.dataset.origText) {
      searchBtn.dataset.origText = searchBtn.textContent.trim();
    }
    if (searchBtn) {
      searchBtn.disabled = true;
      searchBtn.textContent = "Searching...";
    }
    resultsEl.innerHTML = `<div class="card">Searching nearby blood banks &amp; hospitals...</div>`;

    const city = cityInput.value.trim();
    const query = queryInput.value.trim();
    const facilityType = typeSelect?.value || "all";
    const params = new URLSearchParams();
    if (city) params.set("city", city);
    if (query) params.set("q", query);
    if (facilityType !== "all") params.set("facility_type", facilityType);
    if (gpsCoords) {
      params.set("lat", String(gpsCoords.latitude));
      params.set("lon", String(gpsCoords.longitude));
    }

    try {
      const res = await LifeLinkAPI.request(`/api/blood-banks/nearby-live?${params.toString()}`);
      const banks = res.facilities || [];
      if (liveNoteEl && res.live_stock_note) {
        liveNoteEl.textContent = res.live_stock_note;
      }
      if (gmapsNearbyEl && res.maps_nearby_search_url) {
        gmapsNearbyEl.href = res.maps_nearby_search_url;
      }
      if (sourceMetaEl) {
        const srcList = (res.sources_used || []).length ? res.sources_used.join(" + ") : "No external source matched";
        sourceMetaEl.textContent = `Showing ${banks.length} facility result(s) · Sources: ${srcList}${gpsCoords ? " · Sorted by your GPS location" : ""}`;
      }
      if (res.provider_notice && !banks.length) {
        LifeLinkUI.showAlert("bb-search-alert", res.provider_notice, "info");
      }

      if (!banks.length) {
        resultsEl.innerHTML = `
          <div class="empty-state">
            <h3>No blood banks or hospitals loaded yet</h3>
            <p>
              Enter your city (e.g., Mathura, Delhi, Mumbai) or click <strong>Use My GPS Location</strong> to load real nearby blood banks and hospitals,
              or check live licensed stock on <a href="https://www.eraktkosh.in/BLDAHIMS/bloodbank/transactions/bbpublicindex.html" target="_blank" rel="noopener noreferrer">e-RaktKosh</a>.
            </p>
          </div>
        `;
        return;
      }

      const cards = banks
        .map((b) => {
          const logControls = linkedRequestId && b.is_platform_entry && LifeLinkAPI.getToken()
            ? `
              <div style="margin-top: 12px; display: flex; gap: 6px; flex-wrap: wrap;">
                <button type="button" class="btn btn-outline btn-sm bb-log-btn" data-bank="${LifeLinkUI.escapeHtml(b.id)}" data-outcome="contacted">Log: Contacted</button>
                <button type="button" class="btn btn-secondary btn-sm bb-log-btn" data-bank="${LifeLinkUI.escapeHtml(b.id)}" data-outcome="confirmed_available">Confirmed Available</button>
                <button type="button" class="btn btn-outline btn-sm bb-log-btn" data-bank="${LifeLinkUI.escapeHtml(b.id)}" data-outcome="unavailable">Unavailable</button>
              </div>
            `
            : "";

          const phoneBlock = b.phone
            ? `<p style="margin: 6px 0; font-size: 0.92rem;"><strong>Phone:</strong> <a href="tel:${LifeLinkUI.escapeHtml(b.phone)}">${LifeLinkUI.escapeHtml(b.phone)}</a>${b.mobile ? ` &middot; Mobile: <a href="tel:${LifeLinkUI.escapeHtml(b.mobile)}">${LifeLinkUI.escapeHtml(b.mobile)}</a>` : ""}</p>`
            : `<p style="margin: 6px 0; font-size: 0.9rem; color: var(--text-secondary);"><strong>Phone:</strong> Not listed in public map data &mdash; use <em>Find Contact on Google</em> below.</p>`;

          const stockTags = (b.stock_updates || []).length
            ? `<div style="margin: 8px 0; display: flex; gap: 6px; flex-wrap: wrap;">${b.stock_updates
                .map(
                  (u) =>
                    `<span class="badge ${LifeLinkUI.statusBadgeClass(u.availability_status)}">${LifeLinkUI.escapeHtml(u.blood_group)}: ${LifeLinkUI.formatLabel(u.availability_status)}</span>`
                )
                .join("")}</div>`
            : "";

          return `
          <div class="card">
            <div style="display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; flex-wrap: wrap;">
              <div>
                <h3 style="margin: 0; font-size: 1.05rem;">${LifeLinkUI.escapeHtml(b.facility_name)}</h3>
                <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px;">
                  <span class="badge ${b.facility_type === "blood_bank" ? "badge-red" : "badge-neutral"}">${formatTypeLabel(b.facility_type)}</span>
                  <span class="badge ${LifeLinkUI.statusBadgeClass(b.verification_status)}">${LifeLinkUI.formatLabel(b.verification_status)}</span>
                  ${b.operator_type ? `<span class="badge badge-neutral">${LifeLinkUI.formatLabel(b.operator_type)}</span>` : ""}
                  ${b.distance_km !== null && b.distance_km !== undefined ? `<span class="badge badge-neutral">${b.distance_km} km away</span>` : ""}
                </div>
              </div>
              <span class="badge ${LifeLinkUI.statusBadgeClass(b.availability_status)}">${LifeLinkUI.escapeHtml(b.availability_label)}</span>
            </div>
            <p style="margin: 8px 0; color: var(--text-secondary); font-size: 0.92rem;">
              ${LifeLinkUI.escapeHtml(b.address)}${b.city ? `, ${LifeLinkUI.escapeHtml(b.city)}` : ""}
            </p>
            ${phoneBlock}
            ${b.email ? `<p style="margin: 4px 0; font-size: 0.88rem;"><strong>Email:</strong> ${LifeLinkUI.escapeHtml(b.email)}</p>` : ""}
            ${b.opening_hours ? `<p style="margin: 4px 0; font-size: 0.88rem;"><strong>Hours:</strong> ${LifeLinkUI.escapeHtml(b.opening_hours)}</p>` : ""}
            ${stockTags}
            <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px;">
              ${b.phone ? `<a href="tel:${LifeLinkUI.escapeHtml(b.phone)}" class="btn btn-primary btn-sm">Call Facility</a>` : ""}
              <a href="${LifeLinkUI.escapeHtml(b.directions_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">Google Maps Directions</a>
              <a href="${LifeLinkUI.escapeHtml(b.google_search_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">Find Contact on Google</a>
              <a href="${LifeLinkUI.escapeHtml(b.eraktkosh_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">e-RaktKosh Stock</a>
              ${b.website ? `<a href="${LifeLinkUI.escapeHtml(b.website)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">Website</a>` : ""}
            </div>
            <p class="form-hint" style="margin: 8px 0 0;">
              Source: ${LifeLinkUI.escapeHtml(b.source)}
              ${b.last_verified_at ? ` &middot; Verified ${new Date(b.last_verified_at).toLocaleDateString()}` : ""}
            </p>
            ${logControls}
          </div>
        `;
        })
        .join("");

      resultsEl.innerHTML = `<div class="grid-2">${cards}</div>`;

      document.querySelectorAll(".bb-log-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          try {
            await LifeLinkAPI.request(`/api/blood-banks/${encodeURIComponent(btn.dataset.bank)}/contact-attempt`, {
              method: "POST",
              body: JSON.stringify({ request_id: linkedRequestId, outcome: btn.dataset.outcome }),
            });
            LifeLinkUI.showAlert("bb-search-alert", "Contact attempt recorded for your request.", "success");
            await runSearch();
          } catch (err) {
            LifeLinkUI.showAlert("bb-search-alert", err.message, "error");
          }
        });
      });
    } catch (err) {
      resultsEl.innerHTML = "";
      LifeLinkUI.showAlert("bb-search-alert", err.message, "error");
    } finally {
      if (searchBtn) {
        searchBtn.disabled = false;
        searchBtn.textContent = searchBtn.dataset.origText || "Search Nearby";
      }
    }
  }

  gpsBtn?.addEventListener("click", () => {
    LifeLinkUI.clearAlert("bb-search-alert");
    if (!navigator.geolocation) {
      LifeLinkUI.showAlert("bb-search-alert", "Browser GPS is unavailable. Enter your city name instead.", "warning");
      return;
    }
    gpsBtn.disabled = true;
    gpsBtn.textContent = "Locating...";
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        gpsCoords = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
        gpsBtn.disabled = false;
        gpsBtn.textContent = "GPS Active";
        await runSearch();
      },
      () => {
        gpsBtn.disabled = false;
        gpsBtn.textContent = "Use My GPS Location";
        LifeLinkUI.showAlert("bb-search-alert", "Location permission denied. Enter your city name (e.g., Mathura) instead.", "warning");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
    );
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    gpsCoords = null;
    if (gpsBtn) gpsBtn.textContent = "Use My GPS Location";
    runSearch();
  });

  typeSelect?.addEventListener("change", () => runSearch());

  async function loadVerifiedPartnerHospitals() {
    const el = document.getElementById("bb-verified-hospitals");
    if (!el) return;
    try {
      const hospitals = await LifeLinkAPI.request("/api/hospitals/verified");
      if (!hospitals.length) {
        el.innerHTML = `<p class="form-hint" style="margin:0;">No verified partner hospitals listed yet.</p>`;
        return;
      }
      el.innerHTML = hospitals
        .map(
          (h) => `
          <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
              <strong>${LifeLinkUI.escapeHtml(h.hospital_name)} (${LifeLinkUI.escapeHtml(h.city)})</strong>
              <span class="badge badge-success">Platform Verified</span>
            </div>
            <div class="form-hint">${LifeLinkUI.escapeHtml(h.address)} &middot; Official Phone: ${LifeLinkUI.escapeHtml(h.official_phone)}</div>
          </div>
        `
        )
        .join("");
    } catch {
      el.innerHTML = `<p class="form-hint" style="margin:0;">Unable to load partner hospitals right now.</p>`;
    }
  }

  runSearch();
  loadVerifiedPartnerHospitals();
});
