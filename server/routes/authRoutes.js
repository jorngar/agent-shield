const express = require("express");
const router = express.Router();

function createAuthRouteHandler(methodName) {
  return (req, res, next) => {
    let controller;
    try {
      controller = require("../controllers/authController");
    } catch (error) {
      console.error(`[Auth] ${methodName} unavailable`, error);
      return res.status(503).json({ error: "Auth unavailable" });
    }

    const handler = controller?.[methodName];
    if (typeof handler !== "function") {
      console.error(`[Auth] ${methodName} missing from authController`);
      return res.status(503).json({ error: "Auth unavailable" });
    }

    return handler(req, res, next);
  };
}

router.post("/register", createAuthRouteHandler("register"));
router.post("/login", createAuthRouteHandler("login"));

module.exports = router;
