import type { Plugin } from "@opencode-ai/plugin"

interface SDLCSessionState {
  taskId: string | null
  currentPhase: string | null
  phaseSubmitted: boolean
  filesModified: string[]
  approvalPending: boolean
}

const sessions = new Map<string, SDLCSessionState>()

const PLUGIN_STATE_DIR = "./data/plugin_state"

function toolName(input: any): string {
  return String(input.args?.tool ?? input.tool ?? "")
}

async function ensurePluginStateDir(): Promise<void> {
  try {
    await Bun.spawn(["mkdir", "-p", PLUGIN_STATE_DIR]).exited
  } catch {
    // state persistence is best-effort
  }
}

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

export const SDLCEnforcer: Plugin = async ({ client }) => {
  return {
    event: async ({ event }) => {
      const sessionId = (event as any).session_id
      if (!sessionId) return

      switch (event.type) {
        case "session.created": {
          await ensurePluginStateDir()
          sessions.set(sessionId, {
            taskId: null,
            currentPhase: null,
            phaseSubmitted: false,
            filesModified: [],
            approvalPending: false,
          })
          try {
            const file = Bun.file(`${PLUGIN_STATE_DIR}/${sessionId}.json`)
            const stored = JSON.parse(await file.text())
            if (stored) Object.assign(sessions.get(sessionId)!, stored)
          } catch {
            // no stored state
          }
          break
        }

        case "session.deleted":
          sessions.delete(sessionId)
          break

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

    "tool.execute.before": async (input) => {
      const state = getState(input.sessionID)
      const tool = toolName(input)

      if ((tool === "edit" || tool === "write") && state.currentPhase) {
        const allowed = ["Coding", "Testing", null]
        if (!allowed.includes(state.currentPhase)) {
          throw new Error(
            `SDLC Phase Gate: File edits blocked in ${state.currentPhase}. ` +
              `Submit your output via sdlc_submit_output first.`,
          )
        }
      }

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

    "tool.execute.after": async (input) => {
      const state = getState(input.sessionID)
      const tool = toolName(input)
      const result = input.result as string | undefined
      if (!result) return

      try {
        const parsed = JSON.parse(result)

        if (tool === "sdlc_get_next_action") {
          if (parsed.phase) {
            state.currentPhase = parsed.phase
            state.phaseSubmitted = false
          }
          if (parsed.task_id) state.taskId = parsed.task_id
          if (parsed.requires_approval) state.approvalPending = true
        }

        if (tool === "sdlc_request_approval") {
          if (parsed.approved) state.approvalPending = false
          if (parsed.pending) state.approvalPending = true
        }

        if (tool === "sdlc_submit_output") {
          if (parsed.accepted) {
            state.phaseSubmitted = true
            state.currentPhase = parsed.next_phase ?? state.currentPhase
            state.approvalPending = false
            state.filesModified = []
          }
        }

        if ((tool === "edit" || tool === "write") && input.args?.path) {
          state.filesModified.push(String(input.args.path))
        }
      } catch {
        // parse errors are non-fatal
      }

      try {
        await ensurePluginStateDir()
        const stateFile = `${PLUGIN_STATE_DIR}/${input.sessionID}.json`
        const tmpFile = `${stateFile}.tmp`
        await Bun.write(
          tmpFile,
          JSON.stringify({
            taskId: state.taskId,
            currentPhase: state.currentPhase,
            phaseSubmitted: state.phaseSubmitted,
            approvalPending: state.approvalPending,
            filesModified: state.filesModified,
            updatedAt: new Date().toISOString(),
          }),
        )
        // atomic rename on same filesystem
        await Bun.spawn(["mv", tmpFile, stateFile]).exited
      } catch {
        // persistence errors are non-fatal
      }
    },

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
## Next Steps
1. Call sdlc_get_next_action(task_id="${state.taskId}") to resync
2. Continue from the returned phase
3. Do NOT restart from Chatting
`

      if (existingIdx >= 0) {
        output.context[existingIdx] = anchor
      } else {
        output.context.push(anchor)
      }
    },
  }
}

export default SDLCEnforcer
