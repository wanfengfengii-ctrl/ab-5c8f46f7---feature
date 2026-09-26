"use strict";

const SAMPLE = {
  max_curvature: 2,
  segments: [
    { points: [[-3, 0], [-2, 1], [-1, 0], [0, 0]] },
    { points: [[0, 0], [1, 0], [2, 1], [3, 0]] },
  ],
};

const $ = (id) => document.getElementById(id);
const segCountEl = $("segments");

function makeSegmentEditor(idx, points) {
  const wrap = document.createElement("div");
  wrap.className = "segment";
  wrap.dataset.idx = idx;
  let grid = '<div class="pt-grid">';
  for (let i = 0; i < 4; i++) {
    grid += `
      <div class="pt">
        <span>P${i}</span>
        <input type="number" step="1" data-pt="${i}" data-axis="x" value="${points[i][0]}" aria-label="第${idx +1}段 P${i} x">
        <input type="number" step="1" data-pt="${i}" data-axis="y" value="${points[i][1]}" aria-label="第${idx +1}段 P${i} y">
      </div>`;
  }
  grid += "</div>";
  wrap.innerHTML = `<h3>第 ${idx + 1} 段</h3>${grid}`;
  return wrap;
}

function defaultPoints(n) {
  // Continuous, tangent-continuous straight pieces as a safe starting draft.
  const segs = [];
  for (let i = 0; i < n; i++) {
    const x0 = 3 * i;
    segs.push([[x0, 0], [x0 + 1, 0], [x0 + 2, 0], [x0 + 3, 0]]);
  }
  return segs;
}

function renderEditors(n, values) {
  const points = values || defaultPoints(n);
  segCountEl.innerHTML = "";
  points.forEach((pts, i) => segCountEl.appendChild(makeSegmentEditor(i, pts)));
  segCountEl.querySelectorAll("input").forEach((el) =>
    el.addEventListener("input", drawPreview));
}

function readPayload() {
  const segments = [...segCountEl.querySelectorAll(".segment")].map((wrap) => {
    const pts = [[], [], [], []];
    wrap.querySelectorAll("input").forEach((input) => {
      pts[Number(input.dataset.pt)][input.dataset.axis === "x" ? 0 : 1] =
        Number(input.value);
    });
    return { points: pts };
  });
  return { segments, max_curvature: Number($("kmax").value) };
}

function isValidInteger(v) {
  return Number.isFinite(v) && Math.trunc(v) === v;
}

function validateDraft(payload) {
  if (!Number.isFinite(payload.max_curvature) || payload.max_curvature <= 0) {
    return "最大曲率必须是有限正数。";
  }
  for (const seg of payload.segments) {
    for (const pt of seg.points) {
      if (pt.length !== 2 || !isValidInteger(pt[0]) || !isValidInteger(pt[1])) {
        return "所有控制点必须填写整数 x、y 坐标。";
      }
    }
  }
  return null;
}

// ---------- SVG preview (display only; never used for audit decisions) ----

function bezPoint(p, t) {
  const u = 1 - t;
  const b = [u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3];
  return [0, 1].map((ax) => b.reduce((s, w, i) => s + w * p[i][ax], 0));
}

function drawPreview() {
  const svg = $("preview");
  svg.innerHTML = "";
  let payload;
  try { payload = readPayload(); } catch { return; }
  const all = payload.segments.flatMap((s) => s.points);
  if (!all.length) return;
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  let minX = Math.min(...xs), maxX = Math.max(...xs);
  let minY = Math.min(...ys), maxY = Math.max(...ys);
  if (maxX - minX < 1) { minX -= 1; maxX += 1; }
  if (maxY - minY < 1) { minY -= 1; maxY += 1; }
  const W = 640, H = 420, pad = 30;
  const sx = (x) => pad + ((x - minX) / (maxX - minX)) * (W - 2 * pad);
  const sy = (y) => H - pad - ((y - minY) / (maxY - minY)) * (H - 2 * pad);
  const NS = "http://www.w3.org/2000/svg";

  const path = document.createElementNS(NS, "path");
  let d = "";
  payload.segments.forEach((seg, si) => {
    const p = seg.points;
    for (let i = 0; i <= 80; i++) {
      const [x, y] = bezPoint(p, i / 80);
      d += (i === 0 && si === 0 ? "M" : "L") + sx(x).toFixed(2) + "," + sy(y).toFixed(2);
    }
  });
  path.setAttribute("d", d);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "#4da3ff");
  path.setAttribute("stroke-width", "2.5");
  svg.appendChild(path);

  payload.segments.forEach((seg) => {
    const poly = document.createElementNS(NS, "polyline");
    poly.setAttribute("points",
      seg.points.map((p) => sx(p[0]).toFixed(1) + "," + sy(p[1]).toFixed(1)).join(" "));
    poly.setAttribute("fill", "none");
    poly.setAttribute("stroke", "#5a7299");
    poly.setAttribute("stroke-dasharray", "4 4");
    poly.setAttribute("stroke-width", "1");
    svg.appendChild(poly);
    seg.points.forEach((p, i) => {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", sx(p[0])); c.setAttribute("cy", sy(p[1]));
      c.setAttribute("r", 3.5);
      c.setAttribute("fill", i === 0 || i === 3 ? "#ffb84d" : "#93a6c4");
      svg.appendChild(c);
    });
  });
}

// ---------- result rendering ------------------------------------------------

function fmt(v, digits = 6) {
  return Number.isFinite(v) ? Number(v).toFixed(digits).replace(/\.?0+$/, "") : String(v);
}

function renderPass(result) {
  const rows = result.segments.map((s) => `
    <tr>
      <td>第 ${s.index + 1} 段</td>
      <td class="num">${fmt(s.max_curvature)}</td>
      <td class="num">t = ${fmt(s.location.t)}</td>
      <td class="num">(${fmt(s.location.x)}, ${fmt(s.location.y)})</td>
    </tr>`).join("");
  return `
    <div class="banner pass">✓ 审计通过：各段拼接连续，曲率均未超过 κ<sub>max</sub> = ${fmt(result.max_curvature)}</div>
    <table>
      <thead><tr><th>段落</th><th>段内最大曲率</th><th>对应参数</th><th>坐标</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderFail(error) {
  const rows = [];
  const push = (k, v) => rows.push(
    `<div class="row"><span class="k">${k}</span><code>${v}</code></div>`);
  if (error.segment !== null) push("问题段", `第 ${error.segment + 1} 段`);
  if (error.parameter !== null) push("曲线参数 t", fmt(error.parameter, 9));
  if (error.point) push("坐标", `(${fmt(error.point[0], 6)}, ${fmt(error.point[1], 6)})`);
  if (error.curvature !== undefined) push("实际曲率", fmt(error.curvature));
  if (error.max_curvature !== undefined) push("最大曲率", fmt(error.max_curvature));
  if (error.curvature_end !== undefined) {
    push("前段端曲率", fmt(error.curvature_end));
    push("后段端曲率", fmt(error.curvature_start));
  }
  if (error.tangent_end) {
    push("前段端切向量", `(${error.tangent_end.join(", ")})`);
    push("后段端切向量", `(${error.tangent_start.join(", ")})`);
  }
  if (error.point_end) {
    push("前段终点", `(${error.point_end.join(", ")})`);
    push("后段起点", `(${error.point_next.join(", ")})`);
  }
  return `
    <div class="banner fail">✗ 审计不通过（最早问题）：${error.message}</div>
    <div class="detail">
      <div class="row"><span class="k">原因代码</span><code>${error.code}</code></div>
      ${rows.join("")}
    </div>`;
}

async function runAudit() {
  const payload = readPayload();
  const localError = validateDraft(payload);
  const box = $("result");
  box.classList.remove("hidden");
  if (localError) {
    box.innerHTML = `<div class="banner fail">✗ ${localError}</div>`;
    return;
  }
  box.innerHTML = `<div class="banner" style="color:var(--muted);border-color:var(--border);background:var(--panel-2)">正在进行精确根隔离审计…</div>`;
  try {
    const res = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    box.innerHTML = body.ok ? renderPass(body) : renderFail(body.error);
  } catch (err) {
    box.innerHTML = `<div class="banner fail">✗ 无法连接审计服务：${err.message}</div>`;
  }
}

async function checkHealth() {
  const dot = $("healthDot"), text = $("healthText");
  try {
    const res = await fetch("/api/health");
    const body = await res.json();
    dot.className = "dot ok";
    text.textContent = body.status === "ok" ? "审计服务在线" : "服务状态异常";
  } catch {
    dot.className = "dot bad";
    text.textContent = "审计服务不可达";
  }
}

$("auditBtn").addEventListener("click", runAudit);
$("sampleBtn").addEventListener("click", () => {
  $("kmax").value = SAMPLE.max_curvature;
  $("segCount").value = SAMPLE.segments.length;
  renderEditors(SAMPLE.segments.length, SAMPLE.segments.map((s) => s.points));
  drawPreview();
});
$("segCount").addEventListener("change", (e) => {
  let n = Math.max(2, Math.min(5, Number(e.target.value) || 2));
  e.target.value = n;
  renderEditors(n);
  drawPreview();
});

renderEditors(2, SAMPLE.segments.map((s) => s.points));
$("kmax").value = SAMPLE.max_curvature;
drawPreview();
checkHealth();
setInterval(checkHealth, 10000);
