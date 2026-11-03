import { decodeEvent } from './forgejo-events.mjs';
import { parseTriggerKey, validateMappingPolicy } from './forgejo-mapping.mjs';
import { decide, validateRoutePolicy } from './forgejo-policy.mjs';

// The returned event must be a persisted Hatchet event from the selected webhook.
// A submitted event with the same key cannot impersonate the native hook.
export async function resolveIntent({ input, eventKey, eventId, workflowId, config, reader, getEvent }) {
  const key = parseTriggerKey(eventKey);
  if (!key || typeof eventId !== 'string' || typeof workflowId !== 'string') return { outcome: 'rejected' };
  const mapping = validateMappingPolicy(config.mapping);
  const routing = validateRoutePolicy(config.routing);
  if (!mapping.families.includes(key.family)) return { outcome: 'rejected' };
  let receipt;
  try { receipt = await getEvent(eventId); } catch { return { outcome: 'unknown', reason: 'receipt_unavailable' }; }
  if (!receipt || receipt.triggeringWebhookName !== config.webhookName || receipt.key !== eventKey
      || receipt.metadata?.id !== eventId || !receipt.payload || receipt.payloadsRestricted) {
    return { outcome: 'unknown', reason: 'receipt_unverified' };
  }
  // Operate on the native persisted body, not a separately supplied task input.
  const decoded = decodeEvent(key.family, receipt.payload);
  if (decoded.outcome !== 'candidate') return decoded;
  const event = decoded.event;
  if (!mapping.repositories.includes(event.repository.toLowerCase())
      || !mapping.actors.includes(event.actor.toLowerCase())) return { outcome: 'rejected' };
  const decision = await decide(event, routing, reader);
  if (decision.outcome !== 'ready') return decision;
  return { ...decision, deliveryId: key.deliveryId, eventId, workflowId };
}

// Each role is a fixed workflow, not an input-selected executable/profile.
// A lost submission response is unknown; never retry it automatically.
export async function submitIntents(intent, submit) {
  const receipts = [];
  for (const role of intent.roles) {
    if (!['planner', 'worker', 'reviewer'].includes(role)) return { outcome: 'rejected' };
    try {
      const result = await submit(role, intent);
      if (!result || typeof result.runId !== 'string' || !result.runId) return { outcome: 'unknown', receipts };
      receipts.push({ role, outcome: 'queued', runId: result.runId });
    } catch (error) {
      if (['DedupeViolationErr', 'IdempotencyCollisionError'].includes(error?.name)) {
        receipts.push({ role, outcome: 'duplicate' });
        continue;
      }
      return { outcome: 'unknown', receipts };
    }
  }
  return { outcome: receipts.every(r => r.outcome === 'duplicate') ? 'duplicate' : 'queued', receipts };
}
