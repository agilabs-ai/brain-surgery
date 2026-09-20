(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GapAnalyzer = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const CATEGORIES = [
    {
      id: "research",
      label: "Research verification",
      task: /\b(research|source|citation|cite|verify|fact[- ]?check|find|search|paper|study|evidence|link)\b/i,
      friction: /\b(fake|wrong|unverified|missing (?:source|citation)|made up|hallucin|didn.t (?:search|verify)|no (?:source|citation))\b/i,
      skills: ["firecrawl-search", "firecrawl-research-index", "dataset-integrity-audit"],
    },
    {
      id: "spreadsheets",
      label: "Spreadsheet work",
      task: /\b(spreadsheet|excel|workbook|worksheet|csv|pivot|formula|google sheets?|xlsx|cell|column|row)\b/i,
      friction: /\b(wrong (?:cell|column|formula|total)|broken formula|bad (?:csv|sheet)|misaligned|duplicate column|formatting issue)\b/i,
      skills: ["spreadsheets", "excel-live-control", "oxygen-table-tidy"],
    },
    {
      id: "design",
      label: "Visual design",
      task: /\b(design|ui|ux|visual|layout|landing page|website|card|slide|brand|image|frontend|responsive|mobile|css|figma)\b/i,
      friction: /\b(ugly|horrible|slop|broken layout|ignored .*ui|off[- ]brand|bad design|looks bad|visuals? (?:are|is) wrong|operating .*blind)\b/i,
      skills: ["design-taste-frontend", "reuse-existing-assets", "approvalui"],
    },
    {
      id: "coding",
      label: "Coding",
      task: /\b(code|coding|bug|fix|implement|refactor|test|build|repository|repo|git|branch|python|javascript|typescript|react|api|database|deploy)\b/i,
      friction: /\b(build failed|tests? fail|regression|syntax error|traceback|wrong implementation|broke|doesn.t compile|didn.t fix)\b/i,
      skills: ["review", "workplan", "hindsight-coding-agent"],
    },
    {
      id: "writing",
      label: "Writing",
      task: /\b(write|rewrite|draft|post|copy|caption|article|email|message|reply|tone|voice|headline|script)\b/i,
      friction: /\b(generic|robotic|ai slop|wrong tone|not my voice|too long|bad copy|weak hook|sounds like ai)\b/i,
      skills: ["voice-humanizer", "ai-slop-detector", "dm-voice-fede"],
    },
    {
      id: "operations",
      label: "Tool execution",
      task: /\b(run|command|terminal|tool|browser|upload|download|schedule|publish|render|ffmpeg|ssh|server|permission|timeout)\b/i,
      friction: /\b(error|failed|failure|timeout|timed out|permission denied|rejected|unmatched|not found|broken|didn.t run)\b/i,
      skills: ["agent-infra-fixer", "run-to-publishable-result", "local-session-audit"],
    },
  ];

  const GENERAL_FRICTION = /\b(wtf|what the fuck|terrible|horrible|wrong|ignored|broken|failed|failure|why did you|doesn.t make sense|completely missed)\b/i;

  function flattenStrings(value, out) {
    if (typeof value === "string") out.push(value);
    else if (Array.isArray(value)) value.forEach((item) => flattenStrings(item, out));
    else if (value && typeof value === "object") {
      if (typeof value.text === "string") out.push(value.text);
      else if (typeof value.content === "string") out.push(value.content);
      else if (value.content) flattenStrings(value.content, out);
      else if (value.message) flattenStrings(value.message, out);
    }
    return out;
  }

  function extractEntries(raw) {
    const text = String(raw || "").replace(/\u0000/g, "").trim();
    if (!text) return [];
    const lines = text.split(/\r?\n/);
    const entries = [];
    let parsed = 0;
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.length > 2_000_000) continue;
      try {
        const item = JSON.parse(trimmed);
        const role = item.role || item.type || item.message?.role || item.payload?.role || "unknown";
        const content = item.content ?? item.message?.content ?? item.payload?.content ?? item.text ?? item.prompt;
        const bits = flattenStrings(content, []).filter(Boolean);
        if (bits.length) {
          entries.push({ role: String(role).toLowerCase(), text: bits.join(" ").slice(0, 100000) });
          parsed += 1;
        }
      } catch (_) {}
    }
    if (!parsed) {
      return text
        .split(/\n{2,}|(?=\b(?:User|Human|Assistant):\s*)/i)
        .map((part) => part.replace(/^\s*(?:User|Human|Assistant):\s*/i, "").trim())
        .filter(Boolean)
        .map((part) => ({ role: "user", text: part.slice(0, 100000) }));
    }
    return entries.filter((entry) => !/(assistant|tool_result|tool_use)/.test(entry.role) || /error|failed|timeout/i.test(entry.text));
  }

  function levelFor(tasks, friction) {
    if (tasks < 2) return { level: "Not measured", rank: 0, confidence: "low" };
    const rate = friction / tasks;
    if (tasks >= 3 && friction >= 2 && rate >= 0.5) return { level: "Critical", rank: 4, confidence: tasks >= 5 ? "high" : "medium" };
    if (tasks >= 3 && friction >= 1 && rate >= 0.25) return { level: "Weak", rank: 3, confidence: tasks >= 5 ? "high" : "medium" };
    if (tasks >= 2 && friction === 0) return { level: "Covered", rank: 1, confidence: tasks >= 5 ? "high" : "medium" };
    return { level: "Developing", rank: 2, confidence: "medium" };
  }

  function analyze(raw) {
    const entries = extractEntries(raw);
    if (entries.length < 2) throw new Error("Add at least two prompts or log entries to get a defensible result.");
    const categories = CATEGORIES.map((category) => {
      let tasks = 0;
      let friction = 0;
      for (const entry of entries) {
        if (!category.task.test(entry.text)) continue;
        tasks += 1;
        if (category.friction.test(entry.text) || GENERAL_FRICTION.test(entry.text)) friction += 1;
      }
      return { ...category, tasks, friction, ...levelFor(tasks, friction) };
    });
    const measured = categories.filter((item) => item.level !== "Not measured");
    if (!measured.length) throw new Error("There is not enough task evidence in this sample yet. Add more complete prompts or session logs.");

    const strongest = measured.slice().sort((a, b) => a.rank - b.rank || b.tasks - a.tasks)[0];
    const weakest = measured.slice().sort((a, b) => b.rank - a.rank || b.friction - a.friction || b.tasks - a.tasks)[0];
    const gaps = categories.filter((item) => item.rank >= 2).sort((a, b) => b.rank - a.rank || b.friction - a.friction);
    const recommended = [];
    for (const gap of gaps) {
      for (const skill of gap.skills) {
        if (!recommended.some((item) => item.skill === skill)) recommended.push({ skill, category: gap.label, urgency: gap.level });
        if (recommended.length === 7) break;
      }
      if (recommended.length === 7) break;
    }
    const surprising = weakest.rank >= 3
      ? `${weakest.label} breaks down in ${weakest.friction} of ${weakest.tasks} relevant entries.`
      : `${strongest.label} appears most reliable, while ${weakest.label.toLowerCase()} still needs more support.`;
    return {
      schemaVersion: "agent-skills-gap/0.1",
      entries: entries.length,
      categories: categories.map(({ task, skills, ...item }) => item),
      strongest: strongest.label,
      weakest: weakest.label,
      weakestLevel: weakest.level,
      surprising,
      recommended,
      headline: `My AI is strong at ${strongest.label.toLowerCase()}, ${weakest.level === "Critical" ? "terrible" : "weak"} at ${weakest.label.toLowerCase()}.`,
    };
  }

  return { analyze, extractEntries, levelFor, categories: CATEGORIES.map(({ id, label }) => ({ id, label })) };
});
