const express = require('express');
const router = express.Router();
const { getAuditLog } = require('../controllers/auditController');

router.get('/', getAuditLog);
router.get('/all', getAuditLog);

module.exports = router;
