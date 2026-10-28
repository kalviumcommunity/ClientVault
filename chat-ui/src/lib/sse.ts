/**
 * Minimal server-sent-events reader for fetch() response bodies.
 *
 * Buffers across network chunks so an event split between two reads is never
 * parsed half-way, joins multi-line `data:` fields, and rejects anything that
 * is not a JSON object with a string `type`.
 */
export interface StreamEvent {
  type: string
  [key: string]: unknown
}

export class MalformedStreamError extends Error {
  constructor() {
    super('The server sent a malformed stream event.')
    this.name = 'MalformedStreamError'
  }
}

function parseBlock(block: string): StreamEvent | null {
  const data = block
    .split('\n')
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).replace(/^ /, ''))
    .join('\n')
  if (!data) return null // comment / keep-alive
  let event: unknown
  try {
    event = JSON.parse(data)
  } catch {
    throw new MalformedStreamError()
  }
  if (!event || typeof event !== 'object' || typeof (event as StreamEvent).type !== 'string') {
    throw new MalformedStreamError()
  }
  return event as StreamEvent
}

export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { value, done } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n?/g, '\n')
      let sep: number
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const event = parseBlock(buffer.slice(0, sep))
        buffer = buffer.slice(sep + 2)
        if (event) yield event
      }
      if (done) {
        const tail = buffer.trim() ? parseBlock(buffer) : null
        if (tail) yield tail
        return
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}
