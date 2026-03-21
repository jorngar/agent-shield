const express = require("express");
const cors = require("cors");

const authRoutes = require("./routes/authRoutes");
const interceptRoutes = require("./routes/interceptRoutes");
const auditRoutes = require("./routes/auditRoutes");
const healthRoutes = require("./routes/healthRoutes");
const sessionRoutes = require("./routes/sessionRoutes");
const researchRoutes = require("./routes/researchRoutes");

function createApp() {
  const app = express();

  app.use(cors());
  app.use(express.json({ limit: "2mb" }));

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
