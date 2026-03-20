import express from 'express'
import cors from 'cors'
import { randomUUID } from 'crypto'

const app = express()
const PORT = process.env.PORT || 3000

// Simple in-memory store (good enough for local/dev).
// If you restart the server, pending intercepts will be lost.
const intercepts = new Map()
const sessions = new Map()

app.use(cors())
app.use(express.json())

app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    intercepts: intercepts.size,
    sessions: sessions.size,
  })
})

app.post('/api/intercept', (req, res) => {
  const { session_id, agent, action_type, content, risk } = req.body || {}

  if (!session_id || !agent || !action_type || !content || !risk) {
    return res.status(400).json({ error: 'Missing required fields' })
  }

  const intercept_id = randomUUID()
  const now = new Date()

  // For safety + UX, auto-approve low risk without waiting for a human.
  const autoApprove = risk?.risk_level === 'low'
  const decision = autoApprove ? 'approve' : null

  intercepts.set(intercept_id, {
    intercept_id,
    session_id,
    agent,
    action_type,
    content,
    risk,
    decision,
    status: autoApprove ? 'decided' : 'pending',
    created_at: now.toISOString(),
    updated_at: now.toISOString(),
  })

  return res.json({ intercept_id, status: autoApprove ? 'decided' : 'pending', timestamp: now.toISOString() })
})

app.get('/api/intercept/:intercept_id', (req, res) => {
  const { intercept_id } = req.params
  const entry = intercepts.get(intercept_id)
  if (!entry) return res.status(404).json({ error: 'Intercept not found' })

  if (!entry.decision) {
    return res.json({ intercept_id, decision: null, status: 'pending' })
  }

  return res.json({
    intercept_id,
    decision: entry.decision,
    status: 'decided',
    risk: {
      risk_level: entry.risk?.risk_level,
      risk_score: entry.risk?.risk_score,
      category: entry.risk?.category,
    },
  })
})

app.put('/api/intercept/:intercept_id/decision', (req, res) => {
  const { intercept_id } = req.params
  const { decision } = req.body || {}

  if (!['approve', 'deny'].includes(decision)) {
    return res.status(400).json({ error: 'decision must be approve or deny' })
  }

  const entry = intercepts.get(intercept_id)
  if (!entry) return res.status(404).json({ error: 'Intercept not found' })

  entry.decision = decision
  entry.status = 'decided'
  entry.updated_at = new Date().toISOString()
  intercepts.set(intercept_id, entry)

  return res.json({ intercept_id, decision, status: 'decided' })
})

app.post('/api/session/result', (req, res) => {
  const { session_id, status, intercepts: sessionIntercepts } = req.body || {}
  if (!session_id || !status) return res.status(400).json({ error: 'Missing session_id/status' })

  sessions.set(session_id, {
    session_id,
    status,
    intercepts: sessionIntercepts || [],
    updated_at: new Date().toISOString(),
  })

  return res.json({ ok: true, session_id })
})

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`)
})
