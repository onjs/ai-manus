import type { AgentSSEEvent } from '../types/event'

function parseStreamEventId(eventId?: string): [number, number] | null {
  if (!eventId) return null
  const match = /^(\d+)-(\d+)$/.exec(eventId)
  if (!match) return null
  return [Number(match[1]), Number(match[2])]
}

function eventPriority(event: AgentSSEEvent['event']): number {
  if (event === 'step') return 0
  if (event === 'tool') return 1
  if (event === 'message') return 2
  if (event === 'plan') return 3
  if (event === 'title') return 4
  if (event === 'error') return 5
  if (event === 'wait') return 6
  if (event === 'done') return 7
  return 8
}

export function sortSessionEvents(events: AgentSSEEvent[]): AgentSSEEvent[] {
  return [...events].sort((a, b) => {
    const at = Number(a.data?.timestamp || 0)
    const bt = Number(b.data?.timestamp || 0)
    if (at !== bt) return at - bt

    const ap = parseStreamEventId(a.data?.event_id)
    const bp = parseStreamEventId(b.data?.event_id)
    if (ap && bp) {
      if (ap[0] !== bp[0]) return ap[0] - bp[0]
      if (ap[1] !== bp[1]) return ap[1] - bp[1]
    }

    return eventPriority(a.event) - eventPriority(b.event)
  })
}
