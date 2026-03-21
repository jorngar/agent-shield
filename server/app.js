const express = require("express");
const cors = require("cors");

const authRoutes = require("./routes/authRoutes");
const interceptRoutes = require("./routes/interceptRoutes");
const auditRoutes = require("./routes/auditRoutes");
const healthRoutes = require("./routes/healthRoutes");
const sessionRoutes = require("./routes/sessionRoutes");
const researchRoutes = require("./routes/researchRoutes");

const apiIndex = {
  status: "ok",
  service: "agent-shield-backend",
  routes: [
    "GET /health",
    "GET /api",
    "GET /api/health",
    "POST /api/intercept",
    "GET /api/intercept/:id",
    "PUT /api/intercept/:id/decision",
    "POST /api/session/result",
    "GET /api/research/agent-vulnerabilities",
    "POST /api/research/agent-vulnerabilities",
    "POST /api/research/agent-vulnerabilities/refresh",
  ],
};

function createApp() {
  const app = express();

  app.use(cors());
  app.use(express.json({ limit: "2mb" }));
  app.use((req, res, next) => {
    const startedAt = Date.now();
    res.on("finish", () => {
      const durationMs = Date.now() - startedAt;
      console.log(
        `[HTTP] ${req.method} ${req.originalUrl} -> ${res.statusCode} (${durationMs}ms)`,
      );
    });
    next();
  });

  app.get("/", (_req, res) => {
    res.json(apiIndex);
  });

  app.get("/api", (_req, res) => {
    res.json(apiIndex);
  });

  app.use("/auth", authRoutes);
  app.use("/health", healthRoutes);
  app.use("/intercept", interceptRoutes);
  app.use("/audit", auditRoutes);

  app.use("/api/health", healthRoutes);
  app.use("/api/intercept", interceptRoutes);
  app.use("/api/session", sessionRoutes);
  app.use("/api/research", researchRoutes);

  return app;
}

module.exports = { createApp };
