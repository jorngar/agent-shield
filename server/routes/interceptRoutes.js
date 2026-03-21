const express = require('express');
const router = express.Router();
const { intercept, getStatus, resolveDecision } = require("../controllers/interceptController");

router.post("/", intercept);
router.get("/:id", getStatus);
router.put("/:id/decision", resolveDecision);

module.exports = router;
