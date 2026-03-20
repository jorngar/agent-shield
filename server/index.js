require("dotenv").config();
const express = require("express");
const interceptRoutes = require("./routes/interceptRoutes");
const auditRoutes = require("./routes/auditRoutes");
const healthRoutes = require("./routes/healthRoutes");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

app.use("/intercept", interceptRoutes);
app.use("/audit", auditRoutes);
app.use("/health", healthRoutes);

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`http://localhost:${PORT}/health`);
});
