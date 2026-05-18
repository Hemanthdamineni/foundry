#!/usr/bin/env node
/**
 * Foundry postinstall hook
 * Installs Python runtime, registers MCP server, links agents/prompts.
 */

import { execSync, spawnSync } from "child_process";
import { existsSync, mkdirSync, cpSync, readFileSync, writeFileSync } from "fs";
import { homedir } from "os";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = join(__dirname, "..");
const WORKSPACE_ROOT = join(PACKAGE_ROOT, "..");
const RUNTIME_PROJECT_CANDIDATES = [
  join(PACKAGE_ROOT, "sdlc-mcp"),
  join(WORKSPACE_ROOT, "sdlc-mcp"),
];
const LOCAL_RUNTIME_CANDIDATES = [
  {
    src: join(PACKAGE_ROOT, "sdlc-mcp", "src"),
    python: join(PACKAGE_ROOT, ".venv", "bin", "python"),
  },
  {
    src: join(WORKSPACE_ROOT, "sdlc-mcp", "src"),
    python: join(WORKSPACE_ROOT, ".venv", "bin", "python"),
  },
];
const OPENCODE_DIR = join(homedir(), ".config", "opencode");
const PIPX_RUNTIME_BIN = join(homedir(), ".local", "bin", "sdlc-mcp");
const SKILLS_DIR = join(OPENCODE_DIR, "skills", "foundry");
const AGENTS_DIR = join(OPENCODE_DIR, "agents");
const CONTEXT_DIR = join(OPENCODE_DIR, "context");
const OPENCODE_CONFIGS = [
  join(OPENCODE_DIR, "opencode.json"),
];

function log(msg) {
  console.log(`[foundry] ${msg}`);
}

function warn(msg) {
  console.warn(`[foundry] ${msg}`);
}

function run(cmd) {
  try {
    return execSync(cmd, { stdio: "pipe", timeout: 120000 }).toString().trim();
  } catch {
    return null;
  }
}

function runWithEnv(cmd, env) {
  try {
    return execSync(cmd, {
      stdio: "pipe",
      timeout: 120000,
      env: { ...process.env, ...env },
    }).toString().trim();
  } catch {
    return null;
  }
}

function sh(value) {
  return `"${String(value).replace(/(["\\$`])/g, "\\$1")}"`;
}

function isRuntimeHelp(help) {
  return Boolean(help && (help.includes("SDLC-MCP") || help.includes("structured development")));
}

function installedRuntime() {
  if (isRuntimeHelp(run("sdlc-mcp --help"))) {
    return { command: ["sdlc-mcp"], environment: {} };
  }
  if (existsSync(PIPX_RUNTIME_BIN) && isRuntimeHelp(run(`${sh(PIPX_RUNTIME_BIN)} --help`))) {
    return { command: [PIPX_RUNTIME_BIN], environment: {} };
  }
  return null;
}

function localRuntime() {
  for (const candidate of LOCAL_RUNTIME_CANDIDATES) {
    if (!existsSync(candidate.src) || !existsSync(candidate.python)) {
      continue;
    }
    const env = { PYTHONPATH: candidate.src };
    const check = runWithEnv(
      `${sh(candidate.python)} -c "import mcp, sdlc_mcp"`,
      env,
    );
    if (check === null) {
      continue;
    }
    return {
      command: [candidate.python, "-m", "sdlc_mcp"],
      environment: env,
    };
  }
  return null;
}

function bundledRuntimeProject() {
  for (const projectPath of RUNTIME_PROJECT_CANDIDATES) {
    if (existsSync(join(projectPath, "pyproject.toml")) && existsSync(join(projectPath, "src"))) {
      return projectPath;
    }
  }
  return null;
}

function installRuntimeFromPath(projectPath) {
  log(`Installing bundled Python runtime from ${projectPath}...`);

  const uvResult = run(`uv tool install --reinstall ${sh(projectPath)}`);
  const uvRuntime = installedRuntime();
  if (uvResult !== null && uvRuntime) {
    log("Installed bundled runtime via uv");
    return uvRuntime;
  }

  const pipxResult = run(`pipx install --force ${sh(projectPath)}`);
  const pipxRuntime = installedRuntime();
  if (pipxResult !== null && pipxRuntime) {
    log("Installed bundled runtime via pipx");
    return pipxRuntime;
  }

  return null;
}

function ensurePythonRuntime() {
  log("Checking Python runtime...");

  const local = localRuntime();
  if (local) {
    log("Using local sdlc-mcp runtime for development install");
    return local;
  }

  const bundled = bundledRuntimeProject();
  if (bundled) {
    const bundledRuntime = installRuntimeFromPath(bundled);
    if (bundledRuntime) {
      return bundledRuntime;
    }
  }

  const installed = installedRuntime();
  if (installed) {
    log("Python runtime already installed");
    return installed;
  }

  log("Installing sdlc-mcp Python runtime...");
  const uvResult = run("uv tool install sdlc-mcp");
  const uvRuntime = installedRuntime();
  if (uvResult !== null && uvRuntime) {
    log("Installed via uv");
    return uvRuntime;
  }

  const pipxResult = run("pipx install sdlc-mcp");
  const pipxRuntime = installedRuntime();
  if (pipxResult !== null && pipxRuntime) {
    log("Installed via pipx");
    return pipxRuntime;
  }

  warn("Could not install sdlc-mcp. Run: pipx install sdlc-mcp");
  return null;
}

function linkAgents() {
  log("Installing agent definitions...");
  const agentsDir = join(PACKAGE_ROOT, "agents");
  if (!existsSync(agentsDir)) return;

  mkdirSync(AGENTS_DIR, { recursive: true });

  const agents = [
    "foundry.md",
    "planner.md",
    "architect.md",
    "reviewer.md",
    "debugger.md",
    "validator.md",
    "researcher.md",
  ];

  for (const agent of agents) {
    const src = join(agentsDir, agent);
    const dst = join(AGENTS_DIR, agent);
    if (existsSync(src)) {
      cpSync(src, dst, { force: true });
      log(`  Agent: ${agent}`);
    }
  }
}

function linkPrompts() {
  log("Installing prompt files...");
  const promptsDir = join(PACKAGE_ROOT, "prompts");
  if (!existsSync(promptsDir)) return;

  mkdirSync(join(SKILLS_DIR, "prompts"), { recursive: true });
  cpSync(promptsDir, join(SKILLS_DIR, "prompts"), { recursive: true, force: true });
  log("  Prompts installed");
}

function linkSkills() {
  log("Installing skill files...");
  const bundledSkillDir = join(PACKAGE_ROOT, ".opencode", "skills", "foundry");
  const skillsDir = existsSync(bundledSkillDir) ? bundledSkillDir : join(PACKAGE_ROOT, "skills");
  if (!existsSync(skillsDir)) return;

  mkdirSync(SKILLS_DIR, { recursive: true });
  cpSync(skillsDir, SKILLS_DIR, { recursive: true, force: true });
  log("  Skills installed");
}

function linkContext() {
  log("Installing context files...");
  const contextDir = join(PACKAGE_ROOT, ".opencode", "context");
  if (!existsSync(contextDir)) return;

  mkdirSync(CONTEXT_DIR, { recursive: true });
  cpSync(contextDir, CONTEXT_DIR, { recursive: true, force: true });
  log("  Context installed");
}

function registerMCPServer(runtime) {
  log("Registering MCP server...");

  for (const configPath of OPENCODE_CONFIGS) {
    let config = {};
    if (existsSync(configPath)) {
      try {
        config = JSON.parse(readFileSync(configPath, "utf-8"));
      } catch {
        warn(`Could not parse ${configPath}`);
      }
    }

    config.$schema = config.$schema || "https://opencode.ai/config.json";
    config.mcp = config.mcp || {};
    if (!config.mcp["foundry-orchestrator"]) {
      config.mcp["foundry-orchestrator"] = {
        type: "local",
        command: runtime.command,
        enabled: true,
        environment: runtime.environment,
      };
      log(`  MCP server registered in ${configPath}`);
    } else {
      log(`  MCP server already registered in ${configPath}`);
    }

    writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n");
  }
}

function shouldRunRuntime(args) {
  const commands = new Set(["serve", "bootstrap", "init", "doctor", "models", "repair", "upgrade"]);
  return args.some((arg) => arg === "--workspace" || arg.startsWith("--workspace="))
    || commands.has(args[0]);
}

function runRuntime(args) {
  const runtime = localRuntime() || installedRuntime();
  if (!runtime) {
    console.error("[foundry] Runtime not installed. Run `foundry-install` first.");
    process.exit(1);
  }
  const result = spawnSync(
    runtime.command[0],
    [...runtime.command.slice(1), ...args],
    {
      stdio: "inherit",
      env: { ...process.env, ...runtime.environment },
    },
  );
  process.exit(result.status ?? 1);
}

function main() {
  const args = process.argv.slice(2);
  if (shouldRunRuntime(args)) {
    runRuntime(args);
  }

  log("Installing Foundry agent...\n");

  const runtime = ensurePythonRuntime();
  if (!runtime) {
    process.exit(1);
  }
  linkAgents();
  linkPrompts();
  linkSkills();
  linkContext();
  registerMCPServer(runtime);

  log("\nFoundry installed successfully!");
  log("Open any workspace and select the Foundry agent to begin.");
  log("");
  log("Usage:");
  log("  1. opencode");
  log("  2. Select foundry agent");
  log("  3. Describe your task");
}

main();
