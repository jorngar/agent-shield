const express = require('express');
const router = express.Router();
const { getAuditLog, resolveDecision } = require('../controllers/auditController');

router.get('/', getAuditLog);
router.get('/all', getAuditLog);
router.patch('/:id/decision', resolveDecision);

module.exports = router;
