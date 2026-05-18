# SDLC Phase Guide

## Overview
The SDLC server enforces a sequential-but-flexible phase progression:
Chatting → Specs → Planning → Coding → Review ↔ Coding → Testing → Done

## Phase Lifecycle
1. **Create task**: `sdlc_create_task()` → starts at Chatting phase
2. **Get context**: `sdlc_get_next_action()` → returns phase instructions + context
3. **Execute phase**: Agent produces output following phase requirements
4. **Submit output**: `sdlc_submit_output()` → triggers:
   a. Schema validation (structural checks)
   b. Judge evaluation (LLM quality check)
   c. Optional: Multi-agent debate (if enabled)
   d. Phase transition (if accepted)

## Key Transitions
- Review → Coding: Revision loop (up to max_iterations)
- Review → Testing: Forward progress
- Max iterations reached: forced transition to Done
- Budget exhausted: automatic task cancellation

## Context Intelligence
- Repository is indexed for dependency-aware context retrieval
- AST parsing extracts symbols and imports deterministically
- Context is provided per-phase: relevant files + code chunks + graph summary

## Multi-Agent Debate
- Optional: activated when `BudgetPolicy.max_debate_rounds > 0`
- Agents have role-specific prompts (Specs, Planning, Coding, Review, Testing)
- Consensus is determined by meta-judge or majority vote fallback
- Can overturn a judge rejection if all agents agree

## Cross-Task Memory
- Optional: activated when `memory_enabled = true` in config
- Memories persist across tasks with tags, source, and importance
- Queried by phase, tags, keywords, or source
- Enables learning from past tasks without embeddings
