fetch("/api/v1/admin/reports").then(r => r.json()).then(d => {
  const tb = document.querySelector("#mod-table tbody");
  tb.innerHTML = d.reports.map(r => `
    <tr>
      <td>${r.created_at ? r.created_at.slice(11, 16) : ""}</td>
      <td>${r.type_code}</td>
      <td>${r.status}</td>
      <td>${r.trust.toFixed(2)} (${r.pos}/${r.neg})</td>
      <td>${r.has_abuse ? "oui" : ""}</td>
      <td>
        <button data-hide="${r.id}">Masquer</button>
        <button data-rest="${r.id}">Rétablir</button>
      </td>
    </tr>`).join("");
  tb.onclick = async (e) => {
    const h = e.target.getAttribute("data-hide");
    const s = e.target.getAttribute("data-rest");
    if (h) await fetch("/api/v1/admin/reports/" + h + "/hide", { method: "POST" });
    if (s) await fetch("/api/v1/admin/reports/" + s + "/restore", { method: "POST" });
    if (h || s) location.reload();
  };
});
