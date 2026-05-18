/**
 * SDLC Enforcer Plugin for opencode.
 *
 * Enforcement-only — no formatting, no tracing, no decision recording.
 * Hard phase gates that no prompt can bypass.
 */
import type { Plugin } from "@opencode-ai/plugin"

interface SDLCSessionState {
  taskId: string | null
  currentPhase: string | null
  phaseSubmitted: boolean
  filesModified: string[]
  approvalPending: boolean
}

const SDLC_PLUGIN_STATE_DIR = "./data/plugin_state"
const sessions = new Map<string, SDLCSessionState>()

function getState(sessionId: string): SDLCSessionState {
  if (!sessions.has(sessionId)) {
    sessions.set(sessionId, {
      taskId: null,
      currentPhase: null,
      phaseSubmitted: false,
      filesModified: [],
      approvalPending: false,
    })
  }
  return sessions.get(sessionId)!
}

async function readStateFromDisk(sessionId: string): Promise<SDLCSessionState | null> {
  try {
    const path = `${SDLC_PLUGIN_STATE_DIR}/${sessionId}.json`
    const file = Bun.file(path)
    if (!(await file.exists())) return null
    const data = JSON.parse(await file.text())
    return data as SDLCSessionState
  } catch {
    return null
  }
}

async function writeStateToDisk(sessionId: string, state: SDLCSessionState): Promise<void> {
  try {
    const dir = SDLC_PLUGIN_STATE_DIR
    await Bun.write(`${dir}/.mkdir`, "")  // ensure dir exists
    const tmpPath = `${dir}/${sessionId}.json.tmp`
    const finalPath = `${dir}/${sessionId}.json`
    const payload = JSON.stringify({
      ...state,
      updatedAt: new Date().toISOString(),
    })
    await Bun.write(tmpPath, payload)
    // Atomic rename
    const fs = await import("node:fs/promises")
    await fs.rename(tmpPath, finalPath)
  } catch {
    // Non-critical — state will be resynced on next get_next_action
  }
}

export const SDLCEnforcer: Plugin = async ({ client }) => {
  return {
    // Single event handler: switch on event type.
    // Plugin scope: enforcement-only. State persistence, formatting, tracing = server-side.
    event: async ({ event }) => {
      const sessionId = (event as any).session_id
      if (!sessionId) return

      switch (event.type) {
        case "session.created": {
          sessions.set(sessionId, {
            taskId: null,
            currentPhase: null,
            phaseSubmitted: false,
            filesModified: [],
            approvalPending: false,
          })
          // Restore from disk
          const saved = await readStateFromDisk(sessionId)
          if (saved) Object.assign(sessions.get(sessionId)!, saved)
          break
        }

        case "session.deleted":
          sessions.delete(sessionId)
          break

        // Stop workaround: no native stop hook (PR #16598).
        // session.idle + client.session.prompt() re-injects continuation.
        case "session.idle": {
          const state = sessions.get(sessionId)
          if (!state || !state.currentPhase || state.currentPhase === "Done") return
          if (state.phaseSubmitted) return
          await client.session.prompt({
            sessionID: sessionId,
            parts: [
              {
                type: "text",
                text:
                  `[SDLC Enforcer] You are in ${state.currentPhase} phase ` +
                  `but have not called sdlc_submit_output. Complete and submit first.`,
              },
            ],
          })
          break
        }
      }
    },

    // Hard enforcement gates. Server handles formatting, tracing, state persistence.
    "tool.execute.before": async (input) => {
      const state = getState(input.sessionID)
      const tool = input.tool

      // Gate 1: Block file edits outside Coding/Testing phases
      if ((tool === "edit" || tool === "write") && state.currentPhase) {
        const allowed = ["Coding", "Testing", null]
        if (!allowed.includes(state.currentPhase)) {
          throw new Error(
            `SDLC Phase Gate: File edits blocked in ${state.currentPhase}. ` +
              `Submit your output via sdlc_submit_output first.`,
          )
        }
      }

      // Gate 2: Block edits/bash if approval pending
      if (
        state.approvalPending &&
        (tool === "edit" || tool === "write" || tool === "bash")
      ) {
        throw new Error(
          `SDLC Approval Gate: Awaiting user approval. ` +
            `Call sdlc_request_approval first.`,
        )
      }
    },

    // Minimal session sync only. Auto-formatting, tracing, decisions = server-side.
    "tool.execute.after": async (input) => {
      const state = getState(input.sessionID)
      const result = input.result as string | undefined
      if (!result) return

      try {
        const parsed = JSON.parse(result)

        if (input.args?.tool === "sdlc_get_next_action") {
          if (parsed.phase) {
            state.currentPhase = parsed.phase
            state.phaseSubmitted = false
          }
          if (parsed.task_id) {
            state.taskId = parsed.task_id
          }
          if (parsed.requires_approval) {
            state.approvalPending = true
          }
        }

        if (input.args?.tool === "sdlc_request_approval") {
          if (parsed.approved) {
            state.approvalPending = false
          }
        }

        if (input.args?.tool === "sdlc_submit_output") {
          if (parsed.accepted) {
            state.phaseSubmitted = true
            state.currentPhase = parsed.next_phase
            state.filesModified = []
          }
        }

        // Track file modifications
        if (
          (input.tool === "edit" || input.tool === "write") &&
          input.args?.path
        ) {
          const filePath = input.args.path as string
          if (!state.filesModified.includes(filePath)) {
            state.filesModified.push(filePath)
          }
        }

        // Persist state after every SDLC tool call
        if (
          input.args?.tool?.startsWith("sdlc_") &&
          state.taskId
        ) {
          await writeStateToDisk(input.sessionID, state)
        }
      } catch {
        // Parse failure — non-critical
      }
    },

    // Factory.ai-style anchored compaction: inject structured anchor.
    // Only processes newly-dropped spans; merges into existing anchor.
    "experimental.session.compacting": async (input, output) => {
      const state = getState(input.sessionID)
      if (!state.taskId && !state.currentPhase) return

      const existingIdx = output.context.findIndex(
        (c) =>
          typeof c === "string" && c.startsWith("## SDLC Session Anchor"),
      )
      const anchor = `## SDLC Session Anchor (CRITICAL)
## Current State
- task_id: ${state.taskId}
- current_phase: ${state.currentPhase}
- phase_submitted: ${state.phaseSubmitted}
- approval_pending: ${state.approvalPending}
## Files Modified
${state.filesModified.map((f) => `- ${f}`).join("\n") || "- (none)"}
## Next Steps
1. Call sdlc_get_next_action(task_id="${state.taskId}") to resync
2. Continue from the returned phase
3. Do NOT restart from Chatting
`
      if (existingIdx >= 0) {
        output.context[existingIdx] = anchor // replace, don't append
      } else {
        output.context.push(anchor)
      }
    },
  }
}

export default SDLCEnforcer
