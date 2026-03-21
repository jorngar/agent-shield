const express = require("express");
const router = express.Router();
const { researchAgentVulnerabilities } = require("../controllers/researchController");

router.post("/agent-vulnerabilities", researchAgentVulnerabilities);

module.exports = router;
