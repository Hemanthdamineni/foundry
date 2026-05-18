#!/usr/bin/env node
/**
 * Foundry doctor: validate Foundry installation and runtime.
 */

import { execSync } from "child_process";
import { existsSync, readFileSync } from "fs";
import { homedir } from "os";
import { join } from "path";

const OPENCODE_DIR = join(homedir(), ".config", "opencode");

function ok(msg) {
  console.log(`  ✓ ${msg}`);
}

function warn(msg) {
  console.log(`  ⚠ ${msg}`);
}

function fail(msg) {
  console.log(`  ✗ ${msg}`);
}

function checkPythonRuntime() {
  try {
    const result = execSync("sdlc-mcp --help", { stdio: "pipe", timeout: 10000 }).toString();
    if (result.includes("SDLC-MCP") || result.includes("structured development")) {
      ok("Python runtime (sdlc-mcp) installed");
      return true;
    }
    fail("sdlc-mcp not found");
    return false;
  } catch {
    fail("sdlc-mcp not installed. Run: pipx install sdlc-mcp");
    return false;
  }
}

function checkAgentFiles() {
  const agentsDir = join(OPENCODE_DIR, "agents");
  const required = ["foundry.md", "planner.md", "reviewer.md"];
  let allOk = true;
  for (const agent of required) {
    const path = join(agentsDir, agent);
    if (existsSync(path)) {
      ok(`Agent: ${agent}`);
    } else {
      warn(`Agent: ${agent} not found`);
      allOk = false;
    }
  }
  return allOk;
}

function checkSkillFile() {
  const path = join(OPENCODE_DIR, "skills", "foundry", "SKILL.md");
  if (existsSync(path)) {
    ok("SKILL.md installed");
    return true;
  }
  warn("SKILL.md not found");
  return false;
}

function checkPrompts() {
  const promptsDir = join(OPENCODE_DIR, "skills", "foundry", "prompts");
  if (existsSync(promptsDir)) {
    ok("Prompt files installed");
    return true;
  }
  warn("Prompt files not found");
  return false;
}

function checkContext() {
  const projectPath = join(OPENCODE_DIR, "context", "project", "README.md");
  const foundryPath = join(OPENCODE_DIR, "context", "foundry", "architecture.md");
  if (existsSync(projectPath) && existsSync(foundryPath)) {
    ok("Context files installed");
    return true;
  }
  warn("Context files not found");
  return false;
}

function checkMCPRegistration() {
  const configPaths = [
    join(OPENCODE_DIR, "opencode.json"),
    join(process.cwd(), "opencode.json"),
  ];

  for (const path of configPaths) {
    if (existsSync(path)) {
      try {
        const config = JSON.parse(readFileSync(path, "utf-8"));
        if (config.mcp?.["foundry-orchestrator"]) {
          ok(`MCP server registered in ${path}`);
          return true;
        }
      } catch {
        // skip invalid configs
      }
    }
  }
  warn("MCP server not registered in opencode.json");
  return false;
}

function main() {
  console.log("╭─────────────────────────────────────╮");
  console.log("│  Foundry Doctor                      │");
  console.log("╰─────────────────────────────────────╯");

  console.log("\nRuntime:");
  const checks = [checkPythonRuntime()];

  console.log("\nAgents:");
  checks.push(checkAgentFiles());

  console.log("\nSkills:");
  checks.push(checkSkillFile());

  console.log("\nPrompts:");
  checks.push(checkPrompts());

  console.log("\nContext:");
  checks.push(checkContext());

  console.log("\nMCP:");
  checks.push(checkMCPRegistration());

  console.log("\nDone.");
  process.exitCode = checks.every(Boolean) ? 0 : 1;
}

main();
