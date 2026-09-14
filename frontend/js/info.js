/* Travel Info page: transport + weather + events + feedback */
"use strict";
renderNav("/info");

/* transport */
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
    box.innerHTML = `<p style="text-align:center;color:var(--alert)">${esc(err.message)}. Try a suggestion from the list.</p>`;
  }
});

/* weather */
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
    const srcBadge = wx.source === "live"
      ? '<span class="live-badge">● LIVE — Open-Meteo</span>'
      : '<span class="live-badge model">seasonal model (offline)</span>';
    box.innerHTML = `
      <h3 style="text-align:center;color:var(--pine);margin:.4rem 0 .8rem">${esc(wx.place)} · next 7 days ${srcBadge}</h3>
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

/* ---------------- SOS & emergency ---------------- */

function getLocation() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude,
                         accuracy_m: Math.round(pos.coords.accuracy || 0) }),
      () => resolve(null),           // denied/unavailable -> SOS still fires without location
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 });
  });
}

const SVC_ICON = { hospital: "🏥", police: "👮", pharmacy: "💊" };

function svcRow(s) {
  return `
    <div class="svc-row">
      <span class="svc-ico">${SVC_ICON[s.type] || "📍"}</span>
      <div class="svc-info">
        <strong>${esc(s.name)}</strong>
        <span>${esc(s.place)} · ${s.distance_km} km ·
          <a href="tel:${esc(s.phone)}">${esc(s.phone)}</a> ·
          <a href="${esc(s.maps_link || "https://maps.google.com/?q=" + s.lat + "," + s.lon)}" target="_blank" rel="noopener">map ↗</a></span>
      </div>
    </div>`;
}

$("#sosBtn").addEventListener("click", async () => {
  const btn = $("#sosBtn");
  if (btn.disabled) return;
  btn.disabled = true;
  $("#sosHint").textContent = "Getting your location…";
  const loc = await getLocation();
  $("#sosHint").textContent = "Sending SOS alert…";
  try {
    const res = await api("/api/sos", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(loc || {}),
    });
    const c = res.contact || {};
    $("#sosHint").textContent = "";
    $("#sosResult").innerHTML = `
      <div class="sos-done">
        <h4>✅ SOS ${esc(res.reference)} raised — ${esc(res.created_at)}</h4>
        ${res.maps_link
          ? `<p>📍 Location captured: <a href="${esc(res.maps_link)}" target="_blank" rel="noopener">open in Google Maps ↗</a></p>`
          : `<p>📍 Location unavailable — alert raised without coordinates. Enable location for faster rescue.</p>`}
        ${c.name
          ? `<p>📨 Alert logged for <b>${esc(c.name)}</b> (${esc(c.relation || "contact")}) · ${esc(c.phone)}</p>`
          : `<p>⚠️ No emergency contact saved — add one below so alerts reach your family.</p>`}
        <div class="sos-helplines">${res.helplines.map((h) =>
          `<a href="tel:${esc(h.number)}"><strong>${esc(h.number)}</strong> ${esc(h.name)}</a>`).join("")}</div>
        ${res.nearby.length ? `<h5>Nearest help</h5>` + res.nearby.map(svcRow).join("") : ""}
      </div>`;
  } catch (err) {
    $("#sosHint").textContent = err.message;
  }
  setTimeout(() => { btn.disabled = false; }, 4000);
});

$("#emgForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/profile/emergency-contact", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      emg_name: $("#emgName").value.trim(),
      emg_phone: $("#emgPhone").value.trim(),
      emg_relation: $("#emgRelation").value,
    }),
  });
  $("#emgSaved").textContent = "✅ Saved — this contact will be alerted on SOS.";
  setTimeout(() => { $("#emgSaved").textContent = ""; }, 4000);
});

$("#nearbyBtn").addEventListener("click", async () => {
  const box = $("#nearbyResult");
  box.innerHTML = `<p style="color:var(--muted);margin-top:.6rem">Locating you…</p>`;
  const loc = await getLocation();
  if (!loc) {
    box.innerHTML = `<p style="color:var(--alert);margin-top:.6rem">Location permission needed — allow it in your browser and try again.</p>`;
    return;
  }
  try {
    const d = await api(`/api/emergency/nearby?lat=${loc.lat}&lon=${loc.lon}`);
    const col = (title, arr) => `
      <div class="svc-col">
        <h4>${title}</h4>
        ${arr.length ? arr.map(svcRow).join("") : `<p class="svc-none">None in dataset range</p>`}
      </div>`;
    box.innerHTML = `<div class="svc-grid">
      ${col("🏥 Hospitals", d.hospitals)}
      ${col("👮 Police", d.police)}
      ${col("💊 Pharmacies", d.pharmacies)}
    </div>`;
  } catch (err) {
    box.innerHTML = `<p style="color:var(--alert)">${esc(err.message)}</p>`;
  }
});

/* prefill saved emergency contact */
api("/api/profile").then((p) => {
  if (p.emg_name) $("#emgName").value = p.emg_name;
  if (p.emg_phone) $("#emgPhone").value = p.emg_phone;
  if (p.emg_relation) $("#emgRelation").value = p.emg_relation;
}).catch(() => {});

/* events */
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

/* feedback */
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

/* datalist */
(async function init() {
  loadEvents();
  try {
    const d = await api("/api/transport/destinations");
    $("#destList").innerHTML = d.destinations.concat(
      ["Kedarnath", "Badrinath", "Auli", "Valley of Flowers", "Jim Corbett", "Mukteshwar"])
      .map((x) => `<option value="${esc(x)}">`).join("");
  } catch (_) {}
})();
