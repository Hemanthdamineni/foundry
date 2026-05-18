#!/usr/bin/env node
/**
 * Foundry bootstrap: bridge to Python bootstrap engine.
 * Runs workspace bootstrap via the sdlc-mcp runtime.
 */

import { execSync } from "child_process";

function log(msg) {
  console.log(`[foundry] ${msg}`);
}

function main() {
  const cwd = process.cwd();
  log(`Bootstrapping workspace: ${cwd}`);

  try {
    execSync("sdlc-mcp bootstrap", {
      cwd,
      stdio: "inherit",
      timeout: 30000,
    });
    log("Workspace bootstrap complete");
  } catch {
    // Fall back to CLI bootstrap
    try {
      execSync("sdlc-mcp init --no-plugins", {
        cwd,
        stdio: "inherit",
        timeout: 30000,
      });
      log("Workspace bootstrap complete (CLI fallback)");
    } catch (err) {
      console.error("Workspace bootstrap failed:", err.message);
      process.exit(1);
    }
  }
}

main();
