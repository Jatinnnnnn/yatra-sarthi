/* Planner page */
"use strict";
renderNav("/planner");

function renderPlan(plan) {
  const out = $("#planOutput");
  const groupLabel = plan.group_type === "general" ? "All travellers" :
    plan.group_type[0].toUpperCase() + plan.group_type.slice(1);

  let html = `
    <div class="plan-summary">
      <h3>${plan.days}-day circuit around ${esc(plan.hub)}
        <small>${MONTHS[plan.month]} · ${groupLabel}${plan.interests.length ? " · " + plan.interests.join(", ") : ""}</small>
      </h3>
      <div class="stat"><strong>₹${plan.est_cost.toLocaleString("en-IN")}</strong><span>est. per person</span></div>
      <div class="stat"><strong>${plan.itinerary.reduce((n, d) => n + d.stops.length, 0)}</strong><span>places covered</span></div>
      <div class="stat"><strong>${esc(plan.hub)}</strong><span>base hub</span></div>
    </div>`;

  if (plan.weather_changes && plan.weather_changes.length) {
    html += `<div class="replan-banner"><strong>⚠ Weather replanning applied.</strong>
      Risky outdoor stops were swapped automatically:
      <ul>` + plan.weather_changes.map((c) =>
        `<li>Day ${c.day}: <s>${esc(c.removed)}</s> → <b>${esc(c.added)}</b> (${esc(c.reason)})</li>`).join("")
      + `</ul></div>`;
  }

  html += plan.itinerary.map((d) => {
    const wx = d.weather;
    const wxHtml = wx ? `<span class="day-wx">${WX_ICON[wx.condition] || "🌡️"}
      ${wx.temp_max}°/${wx.temp_min}° · ${esc(wx.condition)} ${badge(wx.safety)}</span>` : "";
    const scheduleHtml = d.schedule && d.schedule.length ? `
      <div class="timeline-wrap">
        <button type="button" class="timeline-toggle" data-day="${d.day}">
          🕐 Hour-by-hour schedule <span class="tl-arrow">▾</span>
        </button>
        <div class="timeline" id="timeline-${d.day}" hidden>` +
          d.schedule.map((it) => `
          <div class="tl-item tl-${it.kind}">
            <div class="tl-time">${it.start}${it.end ? "<span>–" + it.end + "</span>" : ""}</div>
            <div class="tl-dot">${it.icon}</div>
            <div class="tl-text">
              <strong>${esc(it.title)}</strong>
              <span>${esc(it.note)}</span>
            </div>
          </div>`).join("") + `
        </div>
      </div>` : "";
    return `<div class="day-card">
      <div class="day-head"><h4>Day ${d.day} · ${esc(d.label)}</h4>${wxHtml}</div>
      <div class="day-body">` + d.stops.map((s) => `
        <div class="stop">
          <img src="${IMG(s.image)}" alt="${esc(s.name)}" loading="lazy" />
          <div>
            <h5>${esc(s.name)} ${s.note === "weather swap" ? '<span class="tag-swap">• swapped for weather</span>' :
              s.note === "continued" ? '<span class="tag-swap" style="color:var(--sky)">• continued</span>' :
              s.note === "check advisory" ? '<span class="tag-swap" style="color:var(--alert)">• check weather advisory before starting</span>' : ""}</h5>
            <p>${esc(s.description)}</p>
            <div class="stop-meta">
              <span>📍 ${esc(s.district)}</span><span>★ ${s.rating}</span>
              <span>${s.entry_fee ? "Entry ₹" + s.entry_fee : "Free entry"}</span>
              <span class="poi-cat">${esc(s.category.replace("_", " "))}</span>
            </div>
          </div>
        </div>`).join("") + `
      </div>
      ${scheduleHtml}
      <div class="day-cost">Day budget ≈ ₹${d.day_cost.toLocaleString("en-IN")} per person</div>
    </div>`;
  }).join("");

  if (plan.events && plan.events.length) {
    html += `<div class="card"><h4 style="color:var(--pine);margin-bottom:.5rem">🎪 During your trip</h4>`
      + eventsBlock(plan.events) + `</div>`;
  }
  const towns = (plan.bazaar_places && plan.bazaar_places.length) ? plan.bazaar_places : [plan.hub];
  html += `<div class="card" style="margin-top:1.1rem;text-align:center">
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:.6rem">Support the local economy — book verified restaurants, guides and taxis in the towns on <b>your route</b>: ${towns.map(esc).join(", ")}.</p>
    <a class="btn btn-primary" href="/bazaar?places=${encodeURIComponent(towns.join(","))}">Open Local Bazaar for this trip →</a>
  </div>`;
  out.innerHTML = html;
}

/* expand/collapse hour-by-hour schedules (delegated — plan re-renders) */
$("#planOutput").addEventListener("click", (e) => {
  const btn = e.target.closest(".timeline-toggle");
  if (!btn) return;
  const tl = document.getElementById(`timeline-${btn.dataset.day}`);
  if (!tl) return;
  tl.hidden = !tl.hidden;
  btn.querySelector(".tl-arrow").textContent = tl.hidden ? "▾" : "▴";
});

$("#planForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const interests = [...f.querySelectorAll("input[name=interests]:checked")].map((i) => i.value);
  const body = {
    destination: f.destination.value || null,
    days: Number(f.days.value) || 4,
    month: f.month.value ? Number(f.month.value) : null,
    budget: f.budget.value ? Number(f.budget.value) : null,
    group_type: f.group_type.value || null,
    interests,
  };
  $("#planOutput").innerHTML = `<div class="plan-placeholder card"><span class="ph-icon">⏳</span><p>Building your itinerary…</p></div>`;
  try {
    const plan = await api("/api/plan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    renderPlan(plan);
  } catch (err) {
    $("#planOutput").innerHTML = `<div class="plan-placeholder card"><span class="ph-icon">😕</span><p>${esc(err.message)}</p></div>`;
  }
});

/* plan handed over from the assistant */
const saved = sessionStorage.getItem("ys_plan");
if (saved) {
  try { renderPlan(JSON.parse(saved)); } catch (_) {}
  sessionStorage.removeItem("ys_plan");
}
