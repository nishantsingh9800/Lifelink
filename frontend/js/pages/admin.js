document.addEventListener("DOMContentLoaded", async () => {
  LifeLinkUI.renderLayout("admin");

  const authResult = await LifeLinkAuth.requireAuth(["admin"]);
  if (!authResult) return;

  const loadingEl = document.getElementById("admin-loading");
  if (authResult.forbidden) {
    loadingEl.classList.add("hidden");
    LifeLinkUI.showAlert(
      "admin-alert",
      "Access Denied (403): Administrator privileges are required and enforced by the backend.",
      "error"
    );
    return;
  }

  LifeLinkUI.renderLayout("admin");

  function renderMapCard(title, obj) {
    const entries = Object.entries(obj || {});
    const body = entries.length
      ? entries.map(([k, v]) => `<div><strong>${LifeLinkUI.escapeHtml(k)}:</strong> ${LifeLinkUI.escapeHtml(v)}</div>`).join("")
      : `<span class="form-hint">No records yet</span>`;
    return `<div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px;"><strong>${LifeLinkUI.escapeHtml(title)}</strong><div style="margin-top: 8px; font-size: 0.9rem;">${body}</div></div>`;
  }

  async function loadOverviewAndAnalytics() {
    const [stats, analytics] = await Promise.all([
      LifeLinkAPI.request("/api/admin/overview"),
      LifeLinkAPI.request("/api/admin/analytics"),
    ]);
    document.getElementById("admin-disclaimer").textContent = stats.disclaimer;
    const cards = [
      { label: "Total Registered Users", value: stats.total_users },
      { label: "Total Donors", value: stats.total_donors },
      { label: "Verified Donors", value: stats.verified_donors },
      { label: "Active Blood Requests", value: stats.active_requests },
      { label: "Requests Fulfilled", value: stats.fulfilled_requests },
      { label: "Requests Unresolved", value: stats.unresolved_requests },
      { label: "Pending Document Reviews", value: stats.pending_document_reviews },
      { label: "Open Reports", value: stats.open_reports },
    ];
    document.getElementById("admin-stats-grid").innerHTML = cards
      .map(
        (c) => `<div class="card"><div class="stat-label">${LifeLinkUI.escapeHtml(c.label)}</div><div class="stat-value">${LifeLinkUI.escapeHtml(c.value)}</div></div>`
      )
      .join("");

    document.getElementById("admin-analytics-grid").innerHTML = [
      renderMapCard("Requests by Status", analytics.requests_by_status),
      renderMapCard("Requests by Blood Group", analytics.requests_by_blood_group),
      renderMapCard("Requests by City", analytics.requests_by_city),
      renderMapCard("Donor Responses", analytics.donor_responses_by_type),
    ].join("");
  }

  async function loadUsers() {
    const role = document.getElementById("admin-role-filter").value;
    const search = document.getElementById("admin-user-search").value.trim();
    const params = new URLSearchParams();
    if (role) params.set("role", role);
    if (search) params.set("search", search);

    const users = await LifeLinkAPI.request(`/api/admin/users?${params.toString()}`);
    const tbody = document.getElementById("admin-users-tbody");
    if (!users.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color: var(--text-secondary);">No matching users found.</td></tr>`;
      return;
    }
    tbody.innerHTML = users
      .map((u) => {
        const nextStatus = u.account_status === "active" ? "suspended" : "active";
        const btnLabel = u.account_status === "active" ? "Suspend" : "Activate";
        return `
        <tr>
          <td>${LifeLinkUI.escapeHtml(u.full_name)}</td>
          <td>${LifeLinkUI.escapeHtml(u.email || "-")}</td>
          <td><span class="badge badge-red">${LifeLinkUI.escapeHtml(u.role)}</span></td>
          <td>${LifeLinkUI.escapeHtml(u.aadhaar_masked || "XXXX-XXXX-0000")} ${u.aadhaar_verified ? "(Verified)" : "(Pending)"}</td>
          <td>${LifeLinkUI.escapeHtml(u.city)}</td>
          <td>${LifeLinkUI.escapeHtml(u.account_status)}</td>
          <td>${u.id !== authResult.user.id ? `<button type="button" class="btn btn-outline btn-sm user-status-btn" data-id="${u.id}" data-status="${nextStatus}">${btnLabel}</button>` : "-"}</td>
        </tr>
      `;
      })
      .join("");

    document.querySelectorAll(".user-status-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await LifeLinkAPI.request(`/api/admin/users/${encodeURIComponent(btn.dataset.id)}/status`, {
          method: "PATCH",
          body: JSON.stringify({ account_status: btn.dataset.status }),
        });
        await loadAll();
      });
    });
  }

  async function loadDocsAndReportsAndRequestsAndBanks() {
    const [docs, reports, reqs, banks, storageCfg, hospitals, integ] = await Promise.all([
      LifeLinkAPI.request("/api/admin/donor-documents"),
      LifeLinkAPI.request("/api/admin/reports"),
      LifeLinkAPI.request("/api/admin/requests"),
      LifeLinkAPI.request("/api/blood-banks"),
      LifeLinkAPI.request("/api/admin/storage-config"),
      LifeLinkAPI.request("/api/admin/hospitals").catch(() => []),
      LifeLinkAPI.request("/api/integrations/status").catch(() => null),
    ]);

    const driveBanner = document.getElementById("admin-drive-banner");
    if (storageCfg && storageCfg.google_drive_folder_url) {
      driveBanner.classList.remove("hidden");
      const modeText = storageCfg.google_drive_auto_upload_enabled
        ? "Automatic Google Drive API upload is active."
        : "Drive folder linked. Local/Supabase storage is active until GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE is configured.";
      driveBanner.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;">
          <span><strong>Verification Drive Folder:</strong> ${LifeLinkUI.escapeHtml(modeText)}</span>
          <a href="${LifeLinkUI.escapeHtml(storageCfg.google_drive_folder_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm">
            Open Google Drive Folder
          </a>
        </div>
      `;
    } else {
      driveBanner.classList.add("hidden");
    }

    document.getElementById("admin-docs-list").innerHTML = docs.length
      ? docs
          .map(
            (d) => `
          <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;">
            <strong>${LifeLinkUI.escapeHtml(d.document_type)}</strong> &middot; <span class="badge ${LifeLinkUI.statusBadgeClass(d.review_status)}">${LifeLinkUI.formatLabel(d.review_status)}</span>
            <div class="form-hint">${LifeLinkUI.escapeHtml(d.storage_path)}</div>
            <div style="margin-top: 8px; display:flex; gap:6px; flex-wrap: wrap;">
              <button type="button" class="btn btn-outline btn-sm doc-view-btn" data-id="${d.id}">View File</button>
              ${d.review_status === "pending_review" ? `<button type="button" class="btn btn-primary btn-sm doc-rev-btn" data-id="${d.id}" data-status="verified">Verify</button><button type="button" class="btn btn-outline btn-sm doc-rev-btn" data-id="${d.id}" data-status="rejected">Reject</button>` : ""}
            </div>
          </div>
        `
          )
          .join("")
      : `<p class="form-hint">No verification documents submitted yet.</p>`;

    document.querySelectorAll(".doc-view-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const res = await fetch(`/api/admin/donor-documents/${encodeURIComponent(btn.dataset.id)}/file`, {
            headers: { Authorization: `Bearer ${LifeLinkAPI.getToken()}` },
          });
          if (!res.ok) throw new Error("Unable to load stored document file.");
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          window.open(url, "_blank", "noopener");
        } catch (err) {
          LifeLinkUI.showAlert("admin-alert", err.message, "error");
        }
      });
    });

    document.querySelectorAll(".doc-rev-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await LifeLinkAPI.request(`/api/admin/donor-documents/${encodeURIComponent(btn.dataset.id)}`, {
          method: "PATCH",
          body: JSON.stringify({ review_status: btn.dataset.status }),
        });
        await loadAll();
      });
    });

    document.getElementById("admin-reports-list").innerHTML = reports.length
      ? reports
          .map(
            (r) => `
          <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;">
            <strong>${LifeLinkUI.escapeHtml(r.reason)}</strong> &middot; <span class="badge ${LifeLinkUI.statusBadgeClass(r.status)}">${LifeLinkUI.formatLabel(r.status)}</span>
            <div style="margin-top: 8px; display:flex; gap:6px;">
              <button type="button" class="btn btn-outline btn-sm rep-btn" data-id="${r.id}" data-status="resolved">Resolve</button>
              <button type="button" class="btn btn-outline btn-sm rep-btn" data-id="${r.id}" data-status="dismissed">Dismiss</button>
            </div>
          </div>
        `
          )
          .join("")
      : `<p class="form-hint">No reports submitted.</p>`;

    document.querySelectorAll(".rep-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await LifeLinkAPI.request(`/api/admin/reports/${encodeURIComponent(btn.dataset.id)}`, {
          method: "PATCH",
          body: JSON.stringify({ status: btn.dataset.status }),
        });
        await loadAll();
      });
    });

    document.getElementById("admin-requests-list").innerHTML = reqs.length
      ? reqs
          .map(
            (r) => `
          <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;">
            <strong>${LifeLinkUI.escapeHtml(r.patient_reference_name)} (${LifeLinkUI.escapeHtml(r.blood_group)})</strong>
            <span class="badge ${LifeLinkUI.statusBadgeClass(r.status)}" style="margin-left: 6px;">${LifeLinkUI.formatLabel(r.status)}</span>
            <div class="form-hint">${LifeLinkUI.escapeHtml(r.hospital_name)}, ${LifeLinkUI.escapeHtml(r.city)}</div>
            <div style="margin-top: 8px;"><button type="button" class="btn btn-outline btn-sm mod-req-btn" data-id="${r.id}">Close / Cancel</button></div>
          </div>
        `
          )
          .join("")
      : `<p class="form-hint">No blood requests recorded.</p>`;

    document.querySelectorAll(".mod-req-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await LifeLinkAPI.request(`/api/admin/requests/${encodeURIComponent(btn.dataset.id)}/moderate`, {
          method: "PATCH",
          body: JSON.stringify({ status: "cancelled", notes: "Closed by administrator moderation" }),
        });
        await loadAll();
      });
    });

    document.getElementById("admin-bb-list").innerHTML = banks
      .map(
        (b) => `
        <div style="display:flex; justify-content:space-between; align-items:center; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 10px;">
          <span><strong>${LifeLinkUI.escapeHtml(b.facility_name)}</strong> (${LifeLinkUI.escapeHtml(b.city)})</span>
          <button type="button" class="btn btn-outline btn-sm del-bb-btn" data-id="${b.id}">Delete</button>
        </div>
      `
      )
      .join("");

    document.querySelectorAll(".del-bb-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await LifeLinkAPI.request(`/api/admin/blood-banks/${encodeURIComponent(btn.dataset.id)}`, { method: "DELETE" });
        await loadAll();
      });
    });

    const hospListEl = document.getElementById("admin-hospitals-list");
    if (hospListEl) {
      hospListEl.innerHTML = hospitals.length
        ? hospitals
            .map(
              (h) => `
            <div style="border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px;">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
                <strong>${LifeLinkUI.escapeHtml(h.hospital_name)} (${LifeLinkUI.escapeHtml(h.city)})</strong>
                <span class="badge ${LifeLinkUI.statusBadgeClass(h.verification_status)}">${LifeLinkUI.formatLabel(h.verification_status)}</span>
              </div>
              <div class="form-hint">Reg #: ${LifeLinkUI.escapeHtml(h.registration_number)} &middot; Rep: ${LifeLinkUI.escapeHtml(h.authorized_rep_name)} (${LifeLinkUI.escapeHtml(h.authorized_rep_role)})</div>
              <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px;">
                ${(h.documents || [])
                  .map((d) => `<button type="button" class="btn btn-outline btn-sm hosp-doc-btn" data-id="${d.id}">View ${LifeLinkUI.escapeHtml(d.document_type)}</button>`)
                  .join("")}
                <button type="button" class="btn btn-secondary btn-sm hosp-rev-btn" data-id="${h.id}" data-status="under_review">Mark Under Review</button>
                <button type="button" class="btn btn-primary btn-sm hosp-rev-btn" data-id="${h.id}" data-status="verified">Verify</button>
                <button type="button" class="btn btn-outline btn-sm hosp-rev-btn" data-id="${h.id}" data-status="rejected">Reject</button>
                <button type="button" class="btn btn-outline btn-sm hosp-rev-btn" data-id="${h.id}" data-status="suspended">Suspend</button>
              </div>
            </div>
          `
            )
            .join("")
        : `<p class="form-hint" style="margin:0;">No hospital registrations submitted yet.</p>`;

      document.querySelectorAll(".hosp-doc-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          try {
            const res = await fetch(`/api/admin/hospitals/documents/${encodeURIComponent(btn.dataset.id)}/file`, {
              headers: { Authorization: `Bearer ${LifeLinkAPI.getToken()}` },
            });
            if (!res.ok) throw new Error("Unable to open hospital document.");
            const blob = await res.blob();
            window.open(URL.createObjectURL(blob), "_blank", "noopener");
          } catch (err) {
            LifeLinkUI.showAlert("admin-alert", err.message, "error");
          }
        });
      });

      document.querySelectorAll(".hosp-rev-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const notes = window.prompt(`Decision notes for ${btn.dataset.status}:`, `Reviewed by administrator as ${btn.dataset.status}`);
          if (!notes) return;
          await LifeLinkAPI.request(`/api/admin/hospitals/${encodeURIComponent(btn.dataset.id)}/review`, {
            method: "PATCH",
            body: JSON.stringify({ verification_status: btn.dataset.status, notes }),
          });
          await loadAll();
        });
      });
    }

    const integEl = document.getElementById("admin-integrations-list");
    if (integEl && integ && integ.integrations) {
      integEl.innerHTML = Object.entries(integ.integrations)
        .map(
          ([k, v]) => `
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 10px; flex-wrap:wrap;">
          <div>
            <strong>${LifeLinkUI.formatLabel(k)}</strong>
            <div class="form-hint">Fallback: ${LifeLinkUI.escapeHtml(v.fallback)}</div>
          </div>
          <span class="badge ${v.configured ? "badge-success" : "badge-neutral"}">${LifeLinkUI.formatLabel(v.status)}</span>
        </div>
      `
        )
        .join("");
    }
  }

  async function loadAll() {
    await Promise.all([loadOverviewAndAnalytics(), loadUsers(), loadDocsAndReportsAndRequestsAndBanks()]);
  }

  try {
    await loadAll();
    loadingEl.classList.add("hidden");
    document.getElementById("admin-content").classList.remove("hidden");
  } catch (err) {
    loadingEl.classList.add("hidden");
    LifeLinkUI.showAlert("admin-alert", err.message, "error");
  }

  document.getElementById("admin-user-filter-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    await loadUsers();
  });

  document.getElementById("admin-bb-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    await LifeLinkAPI.request("/api/admin/blood-banks", {
      method: "POST",
      body: JSON.stringify({
        facility_name: document.getElementById("abb-name").value.trim(),
        address: document.getElementById("abb-address").value.trim(),
        city: document.getElementById("abb-city").value.trim(),
        phone: document.getElementById("abb-phone").value.trim(),
        source: document.getElementById("abb-source").value.trim(),
      }),
    });
    e.target.reset();
    await loadAll();
  });
});
