const vulnerabilityIntelService = require("../services/vulnerabilityIntelService");

function readOptions(req) {
  return {
    url: req.body?.url,
    goal: req.body?.goal,
    limit: req.query?.limit || req.body?.limit,
    tableName: req.query?.table_name || req.body?.table_name,
    browserProfile: req.body?.browser_profile,
  };
}

function mapErrorStatus(error) {
  if (error.code === "POSTGRES_NOT_CONFIGURED") {
    return 503;
  }

  return 500;
}

exports.getStoredAgentVulnerabilities = async (req, res) => {
  try {
    const result = await vulnerabilityIntelService.getStoredAgentVulnerabilities(
      readOptions(req),
    );

    return res.json(result);
  } catch (error) {
    return res.status(mapErrorStatus(error)).json({
      error: "vulnerability_intel_fetch_failed",
      message: error.message,
    });
  }
};

exports.refreshAgentVulnerabilities = async (req, res) => {
  try {
    const result = await vulnerabilityIntelService.refreshStoredAgentVulnerabilities(
      readOptions(req),
    );

    return res.json(result);
  } catch (error) {
    return res.status(mapErrorStatus(error)).json({
      error: "vulnerability_intel_refresh_failed",
      message: error.message,
    });
  }
};
