const express = require("express");
const router = express.Router();
const { reportSessionResult } = require("../controllers/sessionController");

router.post("/result", reportSessionResult);

module.exports = router;
