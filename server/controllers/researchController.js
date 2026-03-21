const { researchAgentVulnerabilities } = require("../services/tinyfishResearchService");

exports.researchAgentVulnerabilities = async (req, res) => {
  try {
    const result = await researchAgentVulnerabilities({
      url: req.body?.url,
      goal: req.body?.goal,
      limit: req.body?.limit,
      tableName: req.body?.table_name,
      browserProfile: req.body?.browser_profile,
    });

    return res.json(result);
  } catch (error) {
    return res.status(500).json({
      error: "tinyfish_research_failed",
      message: error.message,
    });
  }
};
