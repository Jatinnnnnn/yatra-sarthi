/* ============ Yatra Sarthi — frontend logic ============ */
"use strict";

const $ = (sel) => document.querySelector(sel);
const IMG = (name) => `/static/img/${name}`;

const WX_ICON = {
  "Clear": "☀️", "Sunny": "☀️", "Partly cloudy": "🌤️", "Cloudy": "☁️",
  "Light rain": "🌦️", "Rain": "🌧️", "Heavy rain": "⛈️",
  "Thunderstorm": "🌩️", "Snowfall": "🌨️",
};
const MODE_ICON = { rail: "🚆", air: "✈️", bus: "🚌", road: "🛣️", local: "🛺" };
const MONTHS = ["", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Request failed");
  return res.json();
}
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------------- nav ---------------- */
$("#navBurger").addEventListener("click", () => $("#navLinks").classList.toggle("open"));
document.querySelectorAll("#navLinks a").forEach((a) =>
  a.addEventListener("click", () => $("#navLinks").classList.remove("open")));

/* ---------------- chat ---------------- */
const chatWindow = $("#chatWindow");

function addMsg(html, who) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  div.innerHTML = `<div class="msg-bubble">${html}</div>`;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return div;
}

function badge(s) { return `<span class="badge ${s}">${s.toUpperCase()}</span>`; }

function poiMiniCards(pois) {
  return `<div class="mini-cards">` + pois.map((p) => `
    <div class="mini-card">
      <img src="${IMG(p.image)}" alt="${esc(p.name)}" loading="lazy" />
      <div><strong>${esc(p.name)}</strong>${esc(p.district)} · ★ ${p.rating}</div>
    </div>`).join("") + `</div>`;
}

function weatherStrip(wx) {
  return `<div class="wx-strip">` + wx.forecast.map((d) => `
    <div class="wx-day">
      <div>${d.day}</div>
      <div class="wx-icon">${WX_ICON[d.condition] || "🌡️"}</div>
      <strong>${d.temp_max}° / ${d.temp_min}°</strong>
      <div>${esc(d.condition)}</div>
      ${badge(d.safety)}
    </div>`).join("") + `</div>`;
}

function transportBlock(t) {
  return `<div class="tr-steps" style="margin-top:.6rem">` + t.steps.map((s) => `
    <div class="tr-step"><span class="tr-ico">${MODE_ICON[s.mode] || "📍"}</span>
    <span class="tr-mode">${esc(s.mode)}</span><span>${esc(s.detail)}</span></div>`).join("")
    + `</div><div class="tr-fare">Est. full taxi from railhead: ₹${t.taxi_fare_est.toLocaleString("en-IN")}</div>`;
}

function hotelsBlock(hotels) {
  return `<div class="mini-cards">` + hotels.map((h) => `
    <div class="mini-card"><div>
      <strong>${esc(h.name)}</strong>${esc(h.place)} · ${esc(h.band)}<br />
      ₹${Number(h.price_per_night).toLocaleString("en-IN")}/night · ★ ${h.rating}
    </div></div>`).join("") + `</div>`;
}

function eventsBlock(events) {
  return `<div class="mini-cards">` + events.map((e) => `
    <div class="mini-card"><div>
      <strong>${esc(e.name)}</strong>${esc(e.place)} · ${MONTHS[e.month]}<br />${esc(e.note)}
    </div></div>`).join("") + `</div>`;
}

async function sendChat(text) {
  addMsg(esc(text), "user");
  const typing = addMsg('<span class="typing">Yatra Sarthi is thinking…</span>', "bot");
  try {
    const data = await api("/api/assistant", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    let html = esc(data.reply);
    if (data.weather) html += weatherStrip(data.weather);
    if (data.transport) html += transportBlock(data.transport);
    if (data.hotels) html += hotelsBlock(data.hotels);
    if (data.events) html += eventsBlock(data.events);
    if (data.pois) html += poiMiniCards(data.pois);
    if (data.plan) {
      html += `<div style="margin-top:.5rem">Opening it in the Trip Planner below ⤵</div>`;
      renderPlan(data.plan);
      setTimeout(() => $("#planner").scrollIntoView({ behavior: "smooth" }), 400);
    }
    typing.querySelector(".msg-bubble").innerHTML = html;
  } catch (err) {
    typing.querySelector(".msg-bubble").textContent =
      "Sorry, something went wrong. Please try again.";
  }
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

$("#chatForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("#chatText").value.trim();
  if (!text) return;
  $("#chatText").value = "";
  sendChat(text);
});
$("#chatSuggest").addEventListener("click", (e) => {
  if (e.target.tagName === "BUTTON") sendChat(e.target.textContent);
});

/* ---------------- planner ---------------- */
let currentPlan = null;

function renderPlan(plan) {
  currentPlan = plan;
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
      <div class="day-cost">Day budget ≈ ₹${d.day_cost.toLocaleString("en-IN")} per person</div>
    </div>`;
  }).join("");

  if (plan.events && plan.events.length) {
    html += `<div class="card"><h4 style="color:var(--pine);margin-bottom:.5rem">🎪 During your trip</h4>`
      + eventsBlock(plan.events) + `</div>`;
  }
  out.innerHTML = html;
}

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

/* ---------------- explore ---------------- */
let poiTimer = null;
async function loadPois() {
  const params = new URLSearchParams();
  const q = $("#exploreSearch").value.trim();
  const c = $("#exploreCategory").value;
  const d = $("#exploreDistrict").value;
  if (q) params.set("q", q);
  if (c) params.set("category", c);
  if (d) params.set("district", d);
  const data = await api(`/api/pois?${params}`);
  if (!$("#exploreCategory").dataset.filled) {
    $("#exploreCategory").innerHTML = `<option value="">All categories</option>` +
      data.categories.map((x) => `<option value="${x}">${x.replace("_", " ")}</option>`).join("");
    $("#exploreDistrict").innerHTML = `<option value="">All districts</option>` +
      data.districts.map((x) => `<option>${x}</option>`).join("");
    $("#exploreCategory").dataset.filled = "1";
  }
  $("#poiGrid").innerHTML = data.pois.map((p) => `
    <div class="poi-card">
      <img src="${IMG(p.image)}" alt="${esc(p.name)}" loading="lazy" />
      <div class="poi-body">
        <h4>${esc(p.name)}</h4>
        <div class="poi-loc">📍 ${esc(p.district)} district · near ${esc(p.nearest_hub)}</div>
        <p>${esc(p.description)}</p>
        <div class="poi-foot">
          <span class="poi-rating">★ ${p.rating}</span>
          <span class="poi-cat">${esc(p.category.replace("_", " "))}</span>
        </div>
      </div>
    </div>`).join("") || `<p style="text-align:center;color:var(--muted)">No places match those filters.</p>`;
}
$("#exploreSearch").addEventListener("input", () => {
  clearTimeout(poiTimer); poiTimer = setTimeout(loadPois, 300);
});
$("#exploreCategory").addEventListener("change", loadPois);
$("#exploreDistrict").addEventListener("change", loadPois);

/* ---------------- transport ---------------- */
$("#transportForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dest = $("#transportDest").value.trim();
  if (!dest) return;
  const box = $("#transportResult");
  box.innerHTML = `<p style="text-align:center;color:var(--muted)">Finding routes…</p>`;
  try {
    const t = await api(`/api/transport?destination=${encodeURIComponent(dest)}`);
    box.innerHTML = `
      <div class="tr-head"><h3>Reaching ${esc(t.destination)}</h3>
        <p style="color:var(--muted);font-size:.85rem">Gateway: ${esc(t.gateway)}</p></div>
      <div class="tr-reco">✅ <strong>Recommended:</strong> ${esc(t.recommended)}</div>
      ${transportBlock(t)}`;
  } catch (err) {
    box.innerHTML = `<p style="text-align:center;color:var(--alert)">${esc(err.message)}. Try one of the suggestions in the box.</p>`;
  }
});

/* ---------------- weather ---------------- */
$("#weatherForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const place = $("#weatherPlace").value.trim();
  if (!place) return;
  const box = $("#weatherResult");
  box.innerHTML = `<p style="text-align:center;color:var(--muted)">Fetching forecast…</p>`;
  try {
    const wx = await api(`/api/weather?place=${encodeURIComponent(place)}`);
    const worst = wx.forecast.find((d) => d.safety === "alert") ||
                  wx.forecast.find((d) => d.safety === "caution");
    box.innerHTML = `
      <h3 style="text-align:center;color:var(--pine);margin:.4rem 0 .8rem">${esc(wx.place)} · next 7 days</h3>
      <div class="wx-grid">` + wx.forecast.map((d) => `
        <div class="wx-cell">
          <div class="d">${d.day}, ${d.date.slice(8)}/${d.date.slice(5, 7)}</div>
          <div class="ico">${WX_ICON[d.condition] || "🌡️"}</div>
          <div class="t">${d.temp_max}° / ${d.temp_min}°</div>
          <div class="c">${esc(d.condition)} · rain ${d.rain_chance}%</div>
          ${badge(d.safety)}
        </div>`).join("") + `</div>
      <div class="wx-advice">💡 ${esc((worst || wx.forecast[0]).advice)}</div>`;
  } catch (err) {
    box.innerHTML = `<p style="text-align:center;color:var(--alert)">${esc(err.message)}</p>`;
  }
});

/* ---------------- events ---------------- */
async function loadEvents() {
  const m = $("#eventMonth").value;
  const data = await api(`/api/events${m ? `?month=${m}` : ""}`);
  $("#eventGrid").innerHTML = data.events.map((e) => `
    <div class="event-card">
      <h4>${esc(e.name)}</h4>
      <div class="ev-meta">📍 ${esc(e.place)} · 🗓️ ${MONTHS[e.month]} · ${e.duration_days} day${e.duration_days > 1 ? "s" : ""}</div>
      <p>${esc(e.note)}</p>
    </div>`).join("") || `<p style="text-align:center;color:var(--muted)">No events listed for this month.</p>`;
}
$("#eventMonth").addEventListener("change", loadEvents);

/* ---------------- feedback ---------------- */
let fbRating = 0;
$("#stars").addEventListener("click", (e) => {
  if (e.target.dataset.v) {
    fbRating = Number(e.target.dataset.v);
    document.querySelectorAll("#stars button").forEach((b) =>
      b.classList.toggle("on", Number(b.dataset.v) <= fbRating));
  }
});
$("#feedbackForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!fbRating) { $("#feedbackDone").textContent = "Please select a star rating first."; return; }
  await api("/api/feedback", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating: fbRating, comment: $("#feedbackComment").value.trim() }),
  });
  $("#feedbackDone").textContent = "Dhanyavaad! Your feedback has been recorded. 🙏";
  $("#feedbackComment").value = "";
});

/* ---------------- datalist + init ---------------- */
(async function init() {
  loadPois();
  loadEvents();
  try {
    const d = await api("/api/transport/destinations");
    $("#destList").innerHTML = d.destinations.concat(
      ["Kedarnath", "Badrinath", "Auli", "Valley of Flowers", "Jim Corbett", "Mukteshwar"])
      .map((x) => `<option value="${esc(x)}">`).join("");
  } catch (_) { /* non-critical */ }
})();
