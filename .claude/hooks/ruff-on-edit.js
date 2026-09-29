// PostToolUse hook (Edit|Write): lint the edited .py file with `ruff check`.
// Report only: never formats and never auto-fixes (the tree is not ruff-formatted).
// Exit 2 sends the findings to Claude via stderr; skip silently if ruff is unavailable.
const { spawnSync } = require("child_process");
const fs = require("fs");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  let file;
  try {
    file = JSON.parse(input).tool_input?.file_path;
  } catch {
    process.exit(0);
  }
  if (!file || !file.endsWith(".py") || !fs.existsSync(file)) process.exit(0);

  const cwd = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const attempts = [
    ["ruff", ["check", file]],
    ["python", ["-m", "ruff", "check", file]],
  ];
  for (const [cmd, args] of attempts) {
    const r = spawnSync(cmd, args, { cwd, encoding: "utf8" });
    if (r.error || r.status === null) continue; // command not found: try the next one
    if (r.status === 0) process.exit(0);
    const out = `${r.stdout || ""}${r.stderr || ""}`;
    if (/No module named ruff|not recognized|not found/i.test(out)) continue;
    process.stderr.write(out.slice(0, 4000));
    process.exit(2);
  }
  process.exit(0);
});
