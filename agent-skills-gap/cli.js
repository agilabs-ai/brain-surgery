#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { analyze } = require("./analyzer.js");

function fail(message) { process.stderr.write(`${message}\n`); process.exit(2); }
function esc(value) { return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[char])); }
function wrap(value, limit = 34) {
  const words = String(value).split(/\s+/); const lines = []; let line = "";
  for (const word of words) {
    if (line && `${line} ${word}`.length > limit) { lines.push(line); line = word; }
    else line += `${line ? " " : ""}${word}`;
  }
  if (line) lines.push(line);
  return lines.slice(0, 3);
}

const args = process.argv.slice(2); let out = "out"; const inputs = [];
for (let i = 0; i < args.length; i += 1) {
  if (args[i] === "--out") { if (!args[i + 1]) fail("--out needs a directory"); out = args[++i]; }
  else if (args[i].startsWith("-")) fail(`unknown option: ${args[i]}`);
  else inputs.push(args[i]);
}
if (!inputs.length) fail("usage: node cli.js --out DIR INPUT [INPUT ...]");

let raw = "";
for (const input of inputs) {
  const stat = fs.statSync(input);
  if (!stat.isFile()) fail(`not a file: ${input}`);
  if (stat.size > 25 * 1024 * 1024) fail(`input exceeds 25MB: ${path.basename(input)}`);
  raw += `${fs.readFileSync(input, "utf8")}\n`;
}

let result;
try { result = analyze(raw); } catch (error) { fail(error.message); }
fs.mkdirSync(out, { recursive: true, mode: 0o700 });
fs.writeFileSync(path.join(out, "skills-gap.json"), `${JSON.stringify(result, null, 2)}\n`, { mode: 0o600 });

const title = wrap(result.headline);
const measured = result.categories.filter((item) => item.level !== "Not measured").slice(0, 5);
const titleSvg = title.map((line, index) => `<text x="64" y="${190 + index * 62}" class="title">${esc(line)}</text>`).join("");
const rows = measured.map((item, index) => {
  const y = 420 + index * 40;
  const tone = item.level === "Covered" ? "#62D49B" : item.level === "Critical" ? "#FF6961" : item.level === "Weak" ? "#FF9A50" : "#77A6FF";
  return `<text x="64" y="${y}" class="row">${esc(item.label)}</text><text x="760" y="${y}" text-anchor="end" class="rating" fill="${tone}">${esc(item.level.toUpperCase())}</text>`;
}).join("");
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><defs><radialGradient id="g" cx="85%" cy="20%"><stop offset="0" stop-color="#1769FF" stop-opacity=".58"/><stop offset="1" stop-color="#1769FF" stop-opacity="0"/></radialGradient><style>.brand,.title,.row{font-family:Arial,sans-serif;fill:#fff}.brand{font-size:24px;font-weight:800}.title{font-size:54px;font-weight:750;letter-spacing:-2px}.row{font-size:20px;font-weight:600}.mono,.rating{font-family:monospace;font-weight:700}.mono{font-size:17px;fill:#8FAEF5}.rating{font-size:17px}</style></defs><rect width="1200" height="630" fill="#080808"/><rect x="600" width="600" height="630" fill="url(#g)"/><text x="64" y="65" class="brand">EDGE</text><text x="64" y="110" class="mono">AGENT SKILLS GAP TEST</text>${titleSvg}${rows}<line x1="830" y1="68" x2="830" y2="558" stroke="#fff" stroke-opacity=".15"/><text x="895" y="245" class="title" style="font-size:118px">${result.recommended.length}</text><text x="895" y="290" class="mono">RECOMMENDED</text><text x="895" y="316" class="mono">SKILLS</text><text x="895" y="382" class="row" style="font-size:16px;fill:#aaa">${result.entries} private entries</text><text x="895" y="408" class="row" style="font-size:16px;fill:#aaa">analyzed locally.</text><text x="895" y="520" class="brand" style="font-size:18px">getedge.cc</text></svg>`;
fs.writeFileSync(path.join(out, "skills-gap-card.svg"), svg, { mode: 0o600 });
process.stdout.write(`${JSON.stringify({ out: path.resolve(out), entries: result.entries, strongest: result.strongest, weakest: result.weakest, recommendations: result.recommended.length })}\n`);
