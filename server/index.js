require("dotenv").config();
const express = require("express");
// const authenticate = require("./middlewares/authenticate");
const authRoutes = require("./routes/authRoutes");
const interceptRoutes = require("./routes/interceptRoutes");
const auditRoutes = require("./routes/auditRoutes");
const healthRoutes = require("./routes/healthRoutes");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

// Public routes
app.use("/auth", authRoutes);
app.use("/health", healthRoutes);
app.use("/intercept", interceptRoutes);

// Protected routes (dashboard)
app.use("/audit", auditRoutes);

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`http://localhost:${PORT}/health`);
});
