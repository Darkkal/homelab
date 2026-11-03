import { resolveIntent, submitIntents } from './forgejo-runtime.mjs';
import { triggerPattern, validateMappingPolicy } from './forgejo-mapping.mjs';

const name = role => `codex-forgejo-${role}`;
const permissionTask = 'forgejo-canonical-permission';
const label = value => ({ value, required: true, comparator: 0 });

// The selected control worker owns its own permission credential. Other
// instances may ask for a bounded decision but never receive that credential.
export function workflows({ hatchet, role, instance, config, reader, runRole, accepting }) {
  const mapping = validateMappingPolicy(config.mapping);
  const control = instance === config.controlInstance;
  const getEvent = async id => (await hatchet.api.v1EventGet(hatchet.tenantId, id, { timeout: 10000 })).data;
  const withPermission = ctx => ({ ...reader, actor: async (repo, actor, intent) => {
    try {
      const outputs = await ctx.runChild(permissionTask, { repo, actor, intent }, {
        desiredWorkerLabels: { forgejo_control: label(config.controlInstance) },
      });
      if (!outputs || Object.keys(outputs).length !== 1 || !Object.hasOwn(outputs, permissionTask)) return { outcome: 'unknown' };
      const result = outputs[permissionTask];
      const bound = result?.binding;
      if (bound?.repo !== repo || bound?.actor !== actor || bound?.intent?.kind !== intent.kind
          || bound?.intent?.action !== intent.action || bound?.intent?.number !== intent.number
          || bound?.intent?.head !== intent.head) return { outcome: 'unknown' };
      return result;
    } catch { return { outcome: 'unknown' }; }
  } });
  if (control) {
    const auth = hatchet.task({ name: permissionTask, retries: 0, scheduleTimeout: '30s', executionTimeout: '30s',
      fn: async input => {
        const { repo, actor, intent } = input ?? {};
        if (!accepting() || typeof repo !== 'string' || typeof actor !== 'string'
            || !mapping.repositories.includes(repo.toLowerCase()) || !mapping.actors.includes(actor.toLowerCase())
            || !intent || !Number.isSafeInteger(intent.number) || intent.number < 1
            || typeof intent.kind !== 'string' || typeof intent.action !== 'string' || typeof intent.head !== 'string') {
          return { outcome: 'unknown' };
        }
        try {
          const repository = await reader.repository(repo);
          const access = await reader.actor(repo, actor);
          if (!Number.isSafeInteger(repository?.id) || repository.id < 1
              || repository.full_name?.toLowerCase() !== repo.toLowerCase()
              || !Number.isSafeInteger(access?.user?.id) || access.user.id < 1
              || access.user.login?.toLowerCase() !== actor.toLowerCase()
              || typeof access.permission !== 'string') return { outcome: 'unknown' };
          const mode = access.permission.toLowerCase();
          if (!['owner', 'admin', 'write', 'read', 'none'].includes(mode)) return { outcome: 'unknown' };
          return { outcome: ['owner', 'admin', 'write'].includes(mode) ? 'allowed' : 'denied',
            actorId: access.user.id, repositoryId: repository.id, binding: { repo, actor, intent } };
        } catch { return { outcome: 'unknown' }; }
      },
    });
    const sources = mapping.families.map(family => hatchet.task({
      name: `forgejo-${family}`, onEvents: [triggerPattern(family)], retries: 0,
      executionTimeout: '60s', scheduleTimeout: '5m',
      fn: async (_input, ctx) => {
        if (!accepting()) return { outcome: 'refused' };
        // This non-effectful parent waits for the helper on the same one-slot
        // control worker; release its slot before waiting to avoid deadlock.
        await ctx.releaseSlot();
        const eventKey = ctx.triggeringEventKey();
        const eventId = ctx.triggeringEventId();
        const decision = await resolveIntent({ eventKey, eventId, workflowId: ctx.workflowRunId(),
          config, reader: withPermission(ctx), getEvent });
        if (decision.outcome !== 'ready') return decision;
        return await submitIntents(decision, async (target, intent) => {
          const workKey = `${intent.intent.repositoryId}#${intent.intent.number}`;
          const ref = await ctx.runNoWaitChild(name(target), { text: 'controlled by the routed executor' }, {
            additionalMetadata: { event_key: eventKey, event_id: eventId, delivery_id: intent.deliveryId,
              role: target, work_key: workKey, head: intent.intent.head || '',
              actor_id: String(intent.intent.actorId), repository_id: String(intent.intent.repositoryId) },
            desiredWorkerLabels: { role: label(target), forgejo_execution: label('enabled') },
          });
          return { runId: await ref.runId };
        });
      },
    }));
    return [auth, ...sources];
  }
  const routed = hatchet.task({ name: name(role), retries: 0, scheduleTimeout: '5m',
    executionTimeout: `${config.timeoutSeconds + 60}s`,
    concurrency: { name: 'forgejo-work-item', isTenantScoped: true, maxRuns: 1,
      limitStrategy: 3, expression: 'additional_metadata.work_key' },
    idempotency: { strategy: 'ttl', ttlMs: config.dedupeSeconds * 1000,
      expression: "additional_metadata.delivery_id + ':' + additional_metadata.role" },
    fn: async (_input, ctx) => {
      if (!accepting()) return { outcome: 'refused' };
      const meta = ctx.additionalMetadata();
      const current = await resolveIntent({ eventKey: meta.event_key, eventId: meta.event_id,
        workflowId: ctx.workflowRunId(), config, reader: withPermission(ctx), getEvent });
      if (current.outcome !== 'ready') return current;
      const workKey = `${current.intent.repositoryId}#${current.intent.number}`;
      if (!current.roles.includes(role) || meta.role !== role || meta.delivery_id !== current.deliveryId
          || meta.work_key !== workKey || meta.actor_id !== String(current.intent.actorId)
          || meta.repository_id !== String(current.intent.repositoryId)
          || (meta.head || '') !== (current.intent.head || '')) return { outcome: 'stale' };
      const fresh = await withPermission(ctx).actor(current.intent.repository, current.intent.actor, {
        kind: current.intent.kind, action: current.intent.action, number: current.intent.number, head: current.intent.head || '',
      });
      if (fresh.outcome === 'denied') return { outcome: 'rejected' };
      if (fresh.outcome !== 'allowed' || fresh.actorId !== current.intent.actorId
          || fresh.repositoryId !== current.intent.repositoryId) return { outcome: 'unknown' };
      const subject = `${current.intent.repository}#${current.intent.number}`;
      const identifiers = JSON.stringify({ kind: current.intent.kind, action: current.intent.action,
        actor: current.intent.actor, head: current.intent.head, commentId: current.intent.commentId,
        runId: current.intent.runId, reviewId: current.intent.reviewId });
      const message = `Handle ${subject} as the ${role} role. Canonical event identifiers: ${identifiers}. Re-read current repository state and follow your existing role policy before any effect.`;
      return await runRole({ text: message }, ctx);
    },
  });
  return [routed];
}
