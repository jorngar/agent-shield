const VERDICTS = require("./verdicts");
const { buildPrompt } = require("./promptBuilder");

const DENY_THRESHOLD = 70;
const PENDING_THRESHOLD = 40;

/**
 * Fallback: threshold-based evaluation when model is not used.
 */
function fallbackEvaluate(risk) {
  if (risk.recommended_action === "deny" || risk.risk_score >= DENY_THRESHOLD) {
    return { verdict: VERDICTS.DENY, reason: risk.summary };
  }

  if (risk.recommended_action === "review" || risk.risk_score >= PENDING_THRESHOLD) {
    return { verdict: VERDICTS.PENDING, reason: risk.summary };
  }

  return { verdict: VERDICTS.APPROVE, reason: risk.summary };
}

/**
 * Build the prompt and log it. Uses fallback for actual verdict for now.
 * TODO: send prompt to OpenRouter instead of logging.
 */
function evaluate(mcpPayload, risk) {
  const messages = buildPrompt(mcpPayload);

  console.log("========== PROMPT TO MODEL ==========");
  console.log(messages[0].content);
  console.log("======================================");

  return fallbackEvaluate(risk);
}

module.exports = evaluate;
