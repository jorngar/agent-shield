const express = require('express');
const router = express.Router();
const { intercept, getStatus } = require('../controllers/interceptController');

router.post('/', intercept);
router.get('/:id', getStatus);

module.exports = router;
