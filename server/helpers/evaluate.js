const VERDICTS = require("./verdicts");
const { buildPrompt } = require("./promptBuilder");

const DENY_THRESHOLD = 70;
const PENDING_THRESHOLD = 40;

const DECISION_TO_VERDICT = {
  approve: VERDICTS.APPROVE,
  reject: VERDICTS.DENY,
  escalate: VERDICTS.PENDING,
};

/**
 * Fallback: threshold-based evaluation when OpenRouter is unavailable.
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
 * Send the XML prompt to OpenRouter and parse the verdict.
 * Falls back to threshold logic if OpenRouter fails.
 */
async function evaluate(mcpPayload, risk) {
  const messages = buildPrompt(mcpPayload);
  const apiKey = process.env.OPENROUTER_API_KEY;
  const model = process.env.OPENROUTER_MODEL || "qwen/qwen3-8b";

  if (!apiKey) {
    console.warn("OpenRouter not configured, using fallback evaluator");
    return fallbackEvaluate(risk);
  }

  try {
    const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [
          {
            role: "user",
            content: messages[0].content,
          },
        ],
        max_tokens: 1024,
        temperature: 0,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`OpenRouter HTTP ${response.status}: ${errorText.slice(0, 200)}`);
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content;

    if (!content) {
      throw new Error("No content in OpenRouter response");
    }

    // Extract JSON from response (model might wrap it in markdown)
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      throw new Error("No JSON found in model response");
    }

    const parsed = JSON.parse(jsonMatch[0]);

    const verdict = DECISION_TO_VERDICT[parsed.decision];
    if (!verdict) {
      throw new Error(`Invalid decision from model: ${parsed.decision}`);
    }

    console.log("========== MODEL RESPONSE ==========");
    console.log(JSON.stringify(parsed, null, 2));
    console.log("=====================================");

    return {
      verdict,
      reason: parsed.reason || risk.summary,
      risk_score: parsed.risk_score,
      risk_breakdown: parsed.risk_breakdown,
    };
  } catch (err) {
    console.error("OpenRouter evaluation failed, using fallback:", err.message);
    return fallbackEvaluate(risk);
  }
}

module.exports = evaluate;
