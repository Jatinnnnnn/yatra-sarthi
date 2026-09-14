/* Explore page */
"use strict";
renderNav("/explore");

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
          ${p.crowd_now ? crowdBadge(p.crowd_now) : ""}
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

loadPois();
