/* ============ Yatra Sarthi — shared frontend helpers ============ */
"use strict";

const $ = (sel) => document.querySelector(sel);
const IMG = (name) => `/static/img/${name}`;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const WX_ICON = {
  "Clear": "☀️", "Sunny": "☀️", "Partly cloudy": "🌤️", "Cloudy": "☁️",
  "Light rain": "🌦️", "Rain": "🌧️", "Heavy rain": "⛈️",
  "Thunderstorm": "🌩️", "Snowfall": "🌨️",
};
const MODE_ICON = { rail: "🚆", air: "✈️", bus: "🚌", road: "🛣️", local: "🛺" };
const BIZ_ICON = { restaurant: "🍽️", cafe: "☕", taxi: "🚕", rental: "🛵",
  guide: "🥾", adventure: "🚣", artisan: "🧶", experience: "🌄" };
const MONTHS = ["", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (res.status === 401) { window.location.href = "/login"; throw new Error("Login required"); }
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Request failed");
  return res.json();
}

function badge(s) { return `<span class="badge ${s}">${s.toUpperCase()}</span>`; }
function crowdBadge(c) {
  const cls = { overcrowded: "alert", busy: "caution", comfortable: "good" }[c.level];
  return `<span class="badge ${cls}">${c.label} ${c.score}%</span>`;
}

/* ---------------- shared navigation ---------------- */
function renderNav(active) {
  const links = [
    ["/", "Home"], ["/planner", "Trip Planner"], ["/explore", "Explore"],
    ["/crowd", "Crowd Advisor"], ["/bazaar", "Local Bazaar"], ["/info", "Travel Info"],
  ];
  const nav = document.createElement("nav");
  nav.className = "nav";
  nav.innerHTML = `
    <div class="nav-inner">
      <a class="brand" href="/"><span class="brand-mark">🏔️</span><span><strong>Yatra</strong> Sarthi</span></a>
      <div class="nav-links" id="navLinks">
        ${links.map(([href, label]) =>
          `<a href="${href}" ${href === active ? 'class="nav-active"' : ""}>${label}</a>`).join("")}
        <span class="nav-user" id="navUser"></span>
        <button class="nav-logout" id="logoutBtn" type="button">Logout</button>
      </div>
      <button class="nav-burger" id="navBurger" aria-label="Menu">☰</button>
    </div>`;
  document.body.prepend(nav);
  $("#navBurger").addEventListener("click", () => $("#navLinks").classList.toggle("open"));
  $("#logoutBtn").addEventListener("click", async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  });
  api("/api/auth/me").then((u) => {
    $("#navUser").textContent = `👤 ${u.full_name.split(" ")[0]}`;
    if (u.role === "admin") {
      $("#logoutBtn").insertAdjacentHTML("beforebegin", '<a href="/admin" class="nav-admin">Admin</a>');
    }
  }).catch(() => {});
}

/* ---------------- shared render blocks ---------------- */
function weatherStrip(wx) {
  const src = wx.source === "live"
    ? '<div style="font-size:.72rem;margin-top:.4rem"><span class="live-badge">● LIVE — Open-Meteo</span></div>' : "";
  return src + `<div class="wx-strip">` + wx.forecast.map((d) => `
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

function eventsBlock(events) {
  return `<div class="mini-cards">` + events.map((e) => `
    <div class="mini-card"><div>
      <strong>${esc(e.name)}</strong>${esc(e.place)} · ${MONTHS[e.month]}<br />${esc(e.note)}
    </div></div>`).join("") + `</div>`;
}
