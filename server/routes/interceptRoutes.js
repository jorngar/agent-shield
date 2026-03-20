const express = require('express');
const router = express.Router();
const { intercept } = require('../controllers/interceptController');

router.post('/', intercept);

module.exports = router;
