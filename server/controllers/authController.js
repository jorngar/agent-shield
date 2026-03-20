const bcrypt = require("bcryptjs");
const db = require("../configs/db");
const { generateToken } = require("../helpers/auth");

exports.register = (req, res) => {
  const { username, password } = req.body;

  if (!username || !password) {
    return res.status(400).json({ error: "Missing username or password" });
  }

  const existing = db.prepare("SELECT id FROM users WHERE username = ?").get(username);
  if (existing) {
    return res.status(409).json({ error: "Username already exists" });
  }

  const hashed = bcrypt.hashSync(password, 10);
  const result = db.prepare("INSERT INTO users (username, password) VALUES (?, ?)").run(username, hashed);

  const user = { id: result.lastInsertRowid, username, role: "user" };
  const token = generateToken(user);

  res.status(201).json({ user: { id: user.id, username, role: user.role }, token });
};

exports.login = (req, res) => {
  const { username, password } = req.body;

  if (!username || !password) {
    return res.status(400).json({ error: "Missing username or password" });
  }

  const user = db.prepare("SELECT * FROM users WHERE username = ?").get(username);
  if (!user || !bcrypt.compareSync(password, user.password)) {
    return res.status(401).json({ error: "Invalid credentials" });
  }

  const token = generateToken(user);

  res.json({ user: { id: user.id, username: user.username, role: user.role }, token });
};
