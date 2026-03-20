const express = require('express');
const router = express.Router();
const { getAuditLog } = require('../controllers/auditController');

router.get('/', getAuditLog);

module.exports = router;
