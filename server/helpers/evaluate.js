const VERDICTS = require('./verdicts');

const BLOCKED_KEYWORDS = ['rm', 'delete', 'drop', 'exec', 'passwd', 'shadow', 'credentials'];
const REVIEW_KEYWORDS = ['write', 'update', 'modify', 'send', 'post', 'install'];

/**
 * Decide whether to approve, deny, or hold a tool call.
 * Evaluates based on the MCP summary.
 * Placeholder logic — replace with Qwen / rules engine later.
 */
function evaluate({ tool_name, tool_args, summary }) {
  const text = `${tool_name} ${summary}`.toLowerCase();

  for (const word of BLOCKED_KEYWORDS) {
    if (text.includes(word)) {
      return { verdict: VERDICTS.DENY, reason: `Contains blocked keyword: ${word}` };
    }
  }

  for (const word of REVIEW_KEYWORDS) {
    if (text.includes(word)) {
      return { verdict: VERDICTS.PENDING, reason: `Contains review keyword: ${word}` };
    }
  }

  return { verdict: VERDICTS.APPROVE, reason: 'Allowed by default policy' };
}

module.exports = evaluate;
