// A Jest reporter that prints the outcome of every test as TAP, the way Vitest's ``tap-flat``
// does: ``ok N - path > suite > test``, with the path relative to Jest's root directory. A test
// file that failed to run is one ``not ok`` named after the file. It imports nothing of Forja's:
// Jest loads it from the repository's own installation.
const path = require("node:path");

class ForjaReporter {
  constructor(globalConfig) {
    this.root = globalConfig.rootDir;
  }

  onRunComplete(_contexts, results) {
    const rows = [];
    for (const file of results.testResults) {
      const name = path.relative(this.root, file.testFilePath).split(path.sep).join("/");
      if (file.testResults.length === 0) {
        if (file.testExecError || file.numFailingTests > 0) rows.push([false, name, ""]);
        continue;
      }
      for (const test of file.testResults) {
        const title = [name, ...test.ancestorTitles, test.title].join(" > ");
        const ran = test.status === "passed" || test.status === "failed";
        rows.push([test.status !== "failed", title, ran ? "" : " # SKIP"]);
      }
    }
    const lines = ["TAP version 13", `1..${rows.length}`];
    rows.forEach(([ok, title, note], index) => {
      lines.push(`${ok ? "ok" : "not ok"} ${index + 1} - ${title.replace(/\s+/g, " ")}${note}`);
    });
    process.stdout.write(lines.join("\n") + "\n");
  }
}

module.exports = ForjaReporter;
