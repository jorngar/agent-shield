const VERDICTS = require("./verdicts");

const DENY_THRESHOLD = 70;
const PENDING_THRESHOLD = 40;

/**
 * Map MCP risk assessment to a verdict.
 * Uses risk_score + recommended_action from the MCP response.
 */
function evaluate(risk) {
  if (risk.recommended_action === "deny" || risk.risk_score >= DENY_THRESHOLD) {
    return { verdict: VERDICTS.DENY, reason: risk.summary };
  }

  if (risk.recommended_action === "review" || risk.risk_score >= PENDING_THRESHOLD) {
    return { verdict: VERDICTS.PENDING, reason: risk.summary };
  }

  return { verdict: VERDICTS.APPROVE, reason: risk.summary };
}

module.exports = evaluate;
