// SessionStart hook: print docs/ai/STATE.md to stdout so it is added to context.
const fs = require("fs");
const path = require("path");

const MAX_CHARS = 10000;
const root = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const file = path.join(root, "docs", "ai", "STATE.md");

try {
  let text = fs.readFileSync(file, "utf8");
  if (text.length > MAX_CHARS) {
    text = text.slice(0, MAX_CHARS) + "\n[STATE.md truncated: run /sync-state to trim it]\n";
  }
  process.stdout.write(text);
} catch {
  process.stdout.write("docs/ai/STATE.md not found (it is gitignored per machine). Run /sync-state to create it.\n");
}
