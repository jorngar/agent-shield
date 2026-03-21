const express = require("express");
const router = express.Router();
const {
  getStoredAgentVulnerabilities,
  refreshAgentVulnerabilities,
} = require("../controllers/researchController");

router.get("/agent-vulnerabilities", getStoredAgentVulnerabilities);
router.post("/agent-vulnerabilities", getStoredAgentVulnerabilities);
router.post("/agent-vulnerabilities/refresh", refreshAgentVulnerabilities);

module.exports = router;
