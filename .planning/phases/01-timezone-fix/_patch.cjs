const fs = require('fs');
const p = '.planning/phases/01-timezone-fix/01-02-PLAN.md';
let s = fs.readFileSync(p, 'utf8');

const needle = '  <resume-signal>Type "approved" if the chart looks correct, or describe what looks off (specific hour buckets, specific sessions, any UTC-shift symptoms).</resume-signal>\n</task>';

const replacement = [
  '  <resume-signal>Type "approved" if the chart looks correct, or describe what looks off (specific hour buckets, specific sessions, any UTC-shift symptoms).</resume-signal>',
  '  <files>dashboard/app.py (read-only — running the app; no code changes)</files>',
  '  <action>',
  '    Pause for human verification. The executor agent MUST stop and wait for the user to complete the steps listed in <how-to-verify> above and reply with the resume signal. Do NOT proceed to Task 4 until the user types "approved" or confirms the chart looks correct.',
  '',
  '    Concrete behavior the agent performs:',
  '    1. Print the full <what-built> and <how-to-verify> blocks to the user.',
  '    2. Remind the user that Streamlit should be started with `streamlit run dashboard/app.py` from the repo root.',
  '    3. Wait for a reply. If the reply is "approved" (case-insensitive), record the approval in Task 4\'s SUMMARY.md under "Dashboard Visual Check". If the reply describes issues, STOP the plan and surface the issues to the user — do not auto-retry.',
  '  </action>',
  '  <verify>',
  '    <automated>echo "Human checkpoint — user reply required; no automated command."</automated>',
  '  </verify>',
  '  <acceptance_criteria>',
  '    - User has replied with either "approved" (or equivalent affirmation) OR a description of what is still broken.',
  '    - If approved: the user\'s exact reply text is captured verbatim so Task 4 can quote it in SUMMARY.md under "Dashboard Visual Check > Approved by user".',
  '    - If not approved: the plan stops here and the issue is surfaced; Task 4 does NOT run with a falsified approval.',
  '  </acceptance_criteria>',
  '  <done>',
  '    Human has approved the dashboard visual (or explicitly rejected with notes). The response is captured for inclusion in SUMMARY.md.',
  '  </done>',
  '</task>',
].join('\n');

if (!s.includes(needle)) {
  console.error('needle not found');
  process.exit(1);
}
s = s.replace(needle, replacement);
fs.writeFileSync(p, s);
console.log('patched');
