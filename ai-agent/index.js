class LocalAgent {
  constructor(options = {}) {
    this.endpoint = options.endpoint || 'http://localhost:11434'
    this.model = options.model || 'llama2'
  }

  async chat(messages) {
    const response = await fetch(`${this.endpoint}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.model,
        messages,
        stream: false
      })
    })
    return response.json()
  }

  async *chatStream(messages) {
    const response = await fetch(`${this.endpoint}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.model,
        messages,
        stream: true
      })
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value)
      const lines = chunk.split('\n').filter(Boolean)
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6))
          if (data.message?.content) yield data.message.content
        }
      }
    }
  }
}

export default LocalAgent
