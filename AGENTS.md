# JAKA Paint Project Instructions

Before changing this project, read the reusable prompt block in `AI_DEVELOPMENT_PROMPT.md` and follow its scope, testing, and safety constraints. Ignore the task template below that prompt block unless the user explicitly chooses it as the current task.

If the prompt file is missing, unreadable, or malformed, report that problem instead of silently skipping the instructions. The stage list is a task menu, not permission to implement every stage. Without a current task, run only the baseline checks in stage 0 and suggest one next step. After completing the requested task, report results and wait for the next task.

- Work only on the single stage or feature explicitly requested. If the user has given a clear task, state a short plan and proceed; ask a question only when a missing detail blocks implementation.
- Preserve `core/lineart_to_points.py`, the `convert_to_jaka()` interface, generated JAKA TXT structure, and existing regression behavior unless the user explicitly requests a core conversion change.
- Read the relevant code and tests before editing. Run the relevant tests and `python -m py_compile` after changes, and report only checks that actually ran.
- Keep the learner-facing application language product-focused. Do not label the application as a tutorial, teaching prototype, or unfinished Vibe Coding project.
- Do not invent controller APIs, device addresses, credentials, Tool IDs, User Frame IDs, coordinates, heights, speeds, or workspace limits. Use a simulator for controller development until the model, controller version, and official interface are confirmed.
- Never add automatic power-on, enable, alarm clearing, interlock bypass, or automatic motion retry. Network connectivity is not proof that drawing completed; uncertain device state must remain visibly uncertain.
- Treat the directory containing this `AGENTS.md` as the project root, regardless of its local folder name. Do not modify unrelated projects outside this root for a JAKA Paint task.
