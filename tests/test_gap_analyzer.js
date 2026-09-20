const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const { analyze, extractEntries, levelFor } = require("../agent-skills-gap/analyzer.js");

assert.equal(extractEntries('{"role":"user","content":"Fix this React bug"}\n{"role":"user","content":"Write tests"}').length, 2);
assert.equal(levelFor(0, 0).level, "Not measured");
assert.equal(levelFor(5, 0).level, "Covered");
assert.equal(levelFor(4, 2).level, "Critical");

const result = analyze([
  "User: Fix the React code and add tests",
  "User: Implement this API and refactor the repository",
  "User: Build this feature on a branch",
  "User: This UI has a broken layout and horrible visuals",
  "User: Redesign the landing page, the design looks bad",
  "User: You ignored the current brand UI",
].join("\n\n"));

assert.equal(result.schemaVersion, "agent-skills-gap/0.1");
assert.equal(result.strongest, "Coding");
assert.equal(result.weakest, "Visual design");
assert.equal(result.weakestLevel, "Critical");
assert.ok(result.recommended.length <= 7);
assert.ok(result.recommended.some((item) => item.skill === "design-taste-frontend"));
assert.equal(result.categories.find((item) => item.id === "spreadsheets").level, "Not measured");
assert.equal(result.categories.find((item) => item.id === "design").friction, 3);
assert.ok(!JSON.stringify(result).includes("horrible visuals"));

assert.throws(() => analyze("one prompt"), /at least two/i);

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "agent-skills-gap-test-"));
const input = path.join(tmp, "private-prompts.txt");
fs.writeFileSync(input, [
  "Write a product announcement.", "Draft the customer reply.", "Rewrite the launch post.",
  "The Excel sheet has a broken formula.", "The spreadsheet used the wrong column total.",
  "The workbook has duplicate column totals.",
].join("\n\n"));
execFileSync(process.execPath, [path.join(__dirname, "../agent-skills-gap/cli.js"), "--out", path.join(tmp, "out"), input]);
const cliResult = JSON.parse(fs.readFileSync(path.join(tmp, "out/skills-gap.json")));
const cliCard = fs.readFileSync(path.join(tmp, "out/skills-gap-card.svg"), "utf8");
assert.equal(cliResult.weakest, "Spreadsheet work");
assert.ok(cliResult.recommended.length <= 7);
assert.match(cliCard, /width="1200" height="630"/);
assert.ok(!cliCard.includes("private-prompts"));
fs.rmSync(tmp, { recursive: true, force: true });
console.log("gap analyzer tests passed");
