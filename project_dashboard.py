"""Build a stand-alone interactive chart of verified study outputs."""

import csv
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%%TITLE%%</title>
<style>
:root{font-family:system-ui,sans-serif;color:#1b2e2d;background:#f0f5f0}*{box-sizing:border-box}body{margin:0}
header{background:#183732;color:#f4f9f4;padding:2.2rem 1.2rem}header div,main{max-width:1050px;margin:auto}
h1{font-size:clamp(1.6rem,4.5vw,3.1rem);line-height:1.15;margin:0}header p{color:#d4e7de;margin:.75rem 0 0}
main{padding:1.2rem}section{background:white;border:1px solid #c9dbd3;border-radius:.6rem;padding:1.05rem}
.filters{display:flex;flex-wrap:wrap;gap:.9rem;align-items:end}label{display:grid;grid-template-columns:minmax(0,1fr);max-width:100%;gap:.3rem;font-weight:650}
select,button{font:inherit;padding:.48rem;border:1px solid #93afa4;border-radius:.38rem;background:#fff;color:#1b2e2d}
select{min-width:0;max-width:100%;text-overflow:ellipsis}
button{background:#176453;color:white;cursor:pointer}canvas{display:block;width:100%;height:350px;margin:.45rem 0}[hidden]{display:none!important}
#summary{min-height:1.6em;color:#365c55}.table{overflow:auto;max-height:390px}table{width:100%;border-collapse:collapse}
th,td{padding:.5rem;text-align:left;border-bottom:1px solid #dce6e0;white-space:nowrap}th{background:#edf4ee}
summary{cursor:pointer;font-weight:650}:focus-visible{outline:3px solid #a25632;outline-offset:3px}
@media(max-width:480px){canvas{height:300px}main{padding:.6rem}}
</style>
</head>
<body>
<header><div><h1>%%TITLE%%</h1><p>%%SUBTITLE%%</p></div></header>
<main><section>
<div class="filters">
  <label id="group-field">%%GROUP_LABEL%%<select id="group"></select></label>
  <label>Measure<select id="metric"></select></label>
  <button type="button" id="download">Export visible CSV</button>
</div>
<p id="summary" role="status" aria-live="polite"></p>
<canvas id="chart" role="img"></canvas>
<details><summary>Visible values</summary><div class="table"><table><thead id="heading"></thead><tbody id="rows"></tbody></table></div></details>
</section></main>
<script type="application/json" id="payload">%%PAYLOAD%%</script>
<script>
const data = JSON.parse(document.querySelector("#payload").textContent);
const $ = selector => document.querySelector(selector);
const palette = ["#157764","#24598a","#97563f","#7463a2","#5c7639"];
const group = $("#group"), metric = $("#metric"), canvas = $("#chart"), ctx = canvas.getContext("2d");
const rowGroups = data.group ? [...new Set(data.rows.map(row => row[data.group]))].sort() : [];
const empty = value => value === "" || value == null || !Number.isFinite(Number(value));
const format = new Intl.NumberFormat("en", {maximumFractionDigits: 3});
function option(parent, value, label) {
  const node = document.createElement("option"); node.value = value; node.textContent = label; parent.append(node);
}
for (const value of rowGroups) option(group, value, value);
if (!rowGroups.length) $("#group-field").hidden = true;
for (const [column, label] of Object.entries(data.values)) option(metric, column, label);
const selected = () => data.rows.filter(row => !data.group || row[data.group] === group.value);
function draw(rows) {
  const series = rows.filter(row => !empty(row[metric.value]));
  const bounds = canvas.getBoundingClientRect();
  canvas.width = Math.round(bounds.width * devicePixelRatio);
  canvas.height = Math.round(bounds.height * devicePixelRatio);
  ctx.scale(devicePixelRatio, devicePixelRatio);
  const width = bounds.width, height = bounds.height;
  const left = 65, top = 23, right = 22, bottom = 43;
  ctx.clearRect(0,0,width,height);
  if (!series.length) return;
  const values = series.map(row => Number(row[metric.value]));
  const low = Math.min(...values), high = Math.max(...values);
  const lo = low === high ? low - .5 : low, hi = low === high ? high + .5 : high;
  const y = value => top + (hi - value) * (height - top - bottom) / (hi - lo);
  const dates = series.map(row => Date.parse(row[data.x]));
  const time = data.temporal && Number.isFinite(dates[0]) && dates.at(-1) > dates[0];
  const x = index => left + ((time ? (dates[index] - dates[0]) / (dates.at(-1) - dates[0]) : index / Math.max(1, series.length - 1))) * (width - left - right);
  ctx.font = "12px system-ui";
  for (let tick=0; tick<=4; tick++) {
    const value = lo + (hi - lo) * tick / 4, h = y(value);
    ctx.strokeStyle = "#dce7df"; ctx.beginPath(); ctx.moveTo(left,h); ctx.lineTo(width-right,h); ctx.stroke();
    ctx.fillStyle = "#284a44"; ctx.fillText(format.format(value), 4, h + 4);
  }
  const indices = [...new Set([0,Math.floor((series.length-1)/2),series.length-1])];
  ctx.textAlign = "center";
  for (const index of indices) {
    ctx.fillStyle = "#284a44"; ctx.fillText(series[index][data.x].slice(0,16), x(index), height-13);
  }
  ctx.textAlign = "start";
  ctx.strokeStyle = palette[Math.max(0,metric.selectedIndex) % palette.length]; ctx.lineWidth = 2;
  if (data.temporal || data.series) {
    ctx.beginPath();
    values.forEach((value,i) => i ? ctx.lineTo(x(i),y(value)) : ctx.moveTo(x(i),y(value)));
    ctx.stroke();
  }
  ctx.fillStyle = ctx.strokeStyle;
  if (values.length<=55 || !(data.temporal || data.series)) values.forEach((v,i) => {
    ctx.beginPath();ctx.arc(x(i),y(v),3,0,2*Math.PI);ctx.fill();
  });
  canvas.setAttribute("aria-label", data.values[metric.value] + " across " + values.length + " plotted rows");
}
function render() {
  const rows = selected();
  const fields = [data.x, ...Object.keys(data.values)];
  const amounts = rows.filter(row => !empty(row[metric.value])).map(row => Number(row[metric.value]));
  $("#summary").textContent = amounts.length ? amounts.length + " numeric observations · mean " +
    format.format(amounts.reduce((a,b) => a+b,0) / amounts.length) + " · " + data.values[metric.value] :
    "No numeric observations for this selection.";
  const head = document.createElement("tr");
  for (const column of fields) {const cell=document.createElement("th");cell.scope="col";cell.textContent=data.values[column] || column;head.append(cell)}
  $("#heading").replaceChildren(head);
  $("#rows").replaceChildren(...rows.slice(0,500).map(row => {
    const tr=document.createElement("tr");
    for(const field of fields){const node=document.createElement("td");node.textContent=row[field]??"";tr.append(node)}
    return tr;
  }));
  draw(rows);
}
group.addEventListener("change", render);
metric.addEventListener("change", render);
new ResizeObserver(() => draw(selected())).observe(canvas);
$("#download").addEventListener("click", () => {
  const fields = Object.keys(data.rows[0]), quote = value => '"' + String(value ?? "").replaceAll('"','""') + '"';
  const csv = [fields.map(quote).join(","), ...selected().map(row => fields.map(field => quote(row[field])).join(","))].join("\\n");
  const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
  const link=document.createElement("a");link.href=url;link.download="study-selection.csv";link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
});
render();
</script>
</body>
</html>
"""


def build():
    config = json.loads((ROOT / "dashboard.json").read_text(encoding="utf-8"))
    with (ROOT / "reports" / config["input"]).open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows or not {config["x"], *config["values"]}.issubset(rows[0]):
        raise ValueError("Dashboard columns do not match the verified CSV.")
    columns = dict.fromkeys([config["x"], *config["values"], *([config["group"]] if config.get("group") else [])])
    config["rows"] = [{column: row[column] for column in columns} for row in rows]
    page = (PAGE.replace("%%TITLE%%", html.escape(config["title"]))
            .replace("%%SUBTITLE%%", html.escape(config["subtitle"]))
            .replace("%%GROUP_LABEL%%", html.escape(config.get("group_label", "Group")))
            .replace("%%PAYLOAD%%", json.dumps(config, ensure_ascii=False).replace("<", "\\u003c")))
    (ROOT / "dashboard.html").write_text(page, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    build()
