/* Local Bazaar page: business directory + bookings */
"use strict";
renderNav("/bazaar");

let currentBiz = null;

function bizCard(b) {
  return `<div class="biz-card">
    <div class="biz-head">
      <span class="biz-ico">${BIZ_ICON[b.type] || "🏪"}</span>
      <div>
        <h4>${esc(b.name)}</h4>
        <div class="biz-loc">📍 ${esc(b.place)} · <span class="poi-cat">${esc(b.type)}</span></div>
      </div>
      <span class="biz-rating">★ ${b.rating}</span>
    </div>
    <p class="biz-spec">${esc(b.speciality)}</p>
    <p class="biz-note">🤝 ${esc(b.note)}</p>
    <div class="biz-foot">
      <span class="biz-price">₹${Number(b.price).toLocaleString("en-IN")} <small>${esc(b.price_unit)}</small></span>
      <button class="btn btn-primary btn-sm" data-book="${b.id}">Book Now</button>
    </div>
  </div>`;
}

let bizCache = [];
/* trip mode: /bazaar?places=Rishikesh,Haridwar (set by the Trip Planner) */
let tripTowns = (new URLSearchParams(location.search).get("places") || "")
  .split(",").map((t) => t.trim()).filter(Boolean);

function tripBanner() {
  const el = $("#tripBanner");
  if (!el) return;
  if (tripTowns.length) {
    el.innerHTML = `🧭 Showing local businesses <b>on your trip route</b>: ${tripTowns.map(esc).join(", ")}
      <button type="button" id="clearTrip">Show all places</button>`;
    el.hidden = false;
    $("#clearTrip").addEventListener("click", () => {
      tripTowns = [];
      history.replaceState(null, "", "/bazaar");
      el.hidden = true;
      $("#bizPlace").disabled = false;
      loadBiz();
    });
    $("#bizPlace").value = "";
    $("#bizPlace").disabled = true;   // trip route decides the places
  } else {
    el.hidden = true;
    $("#bizPlace").disabled = false;
  }
}

async function loadBiz() {
  const params = new URLSearchParams();
  if (tripTowns.length) params.set("places", tripTowns.join(","));
  else if ($("#bizPlace").value) params.set("place", $("#bizPlace").value);
  if ($("#bizType").value) params.set("type", $("#bizType").value);
  const data = await api(`/api/businesses?${params}`);
  bizCache = data.businesses;
  if (!$("#bizPlace").dataset.filled) {
    $("#bizPlace").innerHTML = `<option value="">All places</option>` +
      data.places.map((p) => `<option>${esc(p)}</option>`).join("");
    $("#bizType").innerHTML = `<option value="">All types</option>` +
      data.types.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
    $("#bizPlace").dataset.filled = "1";
    const pre = new URLSearchParams(location.search).get("place");
    if (pre && !tripTowns.length && data.places.includes(pre)) { $("#bizPlace").value = pre; return loadBiz(); }
  }
  $("#bizGrid").innerHTML = bizCache.map(bizCard).join("") ||
    `<p style="text-align:center;color:var(--muted)">No businesses listed for ${tripTowns.length ? "the towns on this route yet" : "those filters"}.</p>`;
}
$("#bizPlace").addEventListener("change", loadBiz);
$("#bizType").addEventListener("change", loadBiz);
tripBanner();

/* ------------- booking modal ------------- */
const modalBack = $("#modalBack");

$("#bizGrid").addEventListener("click", (e) => {
  const id = e.target.dataset.book;
  if (!id) return;
  currentBiz = bizCache.find((b) => b.id === Number(id));
  $("#modalTitle").textContent = `Book — ${currentBiz.name}`;
  $("#modalSub").textContent =
    `${currentBiz.place} · ₹${currentBiz.price.toLocaleString("en-IN")} ${currentBiz.price_unit} · contact ${currentBiz.contact}`;
  $("#bookForm").hidden = false;
  $("#bookDone").hidden = true;
  $("#bookErr").textContent = "";
  const dateInput = document.querySelector("#bookForm input[name=visit_date]");
  const tomorrow = new Date(Date.now() + 86400000);
  dateInput.min = new Date().toISOString().slice(0, 10);
  dateInput.value = tomorrow.toISOString().slice(0, 10);
  modalBack.hidden = false;
});

$("#modalCancel").addEventListener("click", () => { modalBack.hidden = true; });
$("#modalClose").addEventListener("click", () => { modalBack.hidden = true; loadBookings(); });
modalBack.addEventListener("click", (e) => { if (e.target === modalBack) modalBack.hidden = true; });

$("#bookForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentBiz) {   // safety: modal open without a selected business
    modalBack.hidden = true;
    return;
  }
  const f = e.target;
  try {
    const r = await api("/api/bookings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        business_id: currentBiz.id,
        visit_date: f.visit_date.value,
        people: Number(f.people.value),
        note: f.note.value.trim(),
      }),
    });
    $("#bookForm").hidden = true;
    $("#bookDone").hidden = false;
    $("#bookDoneMsg").innerHTML =
      `✅ Booking confirmed at <b>${esc(r.business)}</b>!<br />Reference: <b>${esc(r.reference)}</b><br />
       <small>The business will contact you — or call them at ${esc(currentBiz.contact)}.</small>`;
  } catch (err) {
    $("#bookErr").textContent = err.message;
  }
});

/* ------------- my bookings ------------- */
async function loadBookings() {
  const data = await api("/api/bookings");
  $("#bookingList").innerHTML = data.bookings.length ? data.bookings.map((b) => `
    <div class="booking-row ${b.status}">
      <span class="biz-ico">${BIZ_ICON[b.type] || "🏪"}</span>
      <div class="booking-main">
        <strong>${esc(b.name)}</strong>
        <span>${esc(b.place)} · ${esc(b.visit_date)} · ${b.people} people${b.note ? " · " + esc(b.note) : ""}</span>
      </div>
      <span class="booking-ref">YS-${String(b.id).padStart(5, "0")}</span>
      ${b.status === "confirmed"
        ? `<button class="btn-cancel" data-cancel="${b.id}">Cancel</button>`
        : `<span class="badge alert">CANCELLED</span>`}
    </div>`).join("")
    : `<p style="text-align:center;color:var(--muted)">No bookings yet — book a local restaurant, guide or taxi above. 🛍️</p>`;
}
$("#bookingList").addEventListener("click", async (e) => {
  const id = e.target.dataset.cancel;
  if (!id) return;
  await api(`/api/bookings/${id}`, { method: "DELETE" });
  loadBookings();
});

loadBiz();
loadBookings();
