/**
 * Decide whether to approve, deny, or hold a tool call.
 * Placeholder logic — replace with Qwen / rules engine later.
 */
function evaluate(toolCall) {
  const toolName = (toolCall.params?.name || '').toLowerCase();

  const blocked = ['rm', 'delete', 'drop', 'exec'];
  for (const word of blocked) {
    if (toolName.includes(word)) {
      return { verdict: 'deny', reason: `Tool name contains blocked keyword: ${word}` };
    }
  }

  return { verdict: 'approve', reason: 'Allowed by default policy' };
}

module.exports = evaluate;
