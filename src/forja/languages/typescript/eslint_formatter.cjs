// An ESLint formatter that prints one line per problem: path:line:col: message (rule).
// The paths are relative to the directory ESLint ran in, which none of ESLint's own formatters
// give. It imports nothing of Forja's: ESLint loads it from the repository's own installation.
const path = require("node:path");

module.exports = function format(results) {
  const lines = [];
  for (const result of results) {
    const file = path.relative(process.cwd(), result.filePath).split(path.sep).join("/");
    for (const message of result.messages) {
      const text = String(message.message).replace(/\s+/g, " ");
      lines.push(`${file}:${message.line || 1}:${message.column || 1}: ${text} (${message.ruleId || "eslint"})`);
    }
  }
  return lines.join("\n") + (lines.length ? "\n" : "");
};
