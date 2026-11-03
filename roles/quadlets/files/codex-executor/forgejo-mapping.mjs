// Build a native Hatchet event-key expression from protected operator policy.
// This module does not create or update a webhook.
const familyActions = Object.freeze({
  issues: ['opened', 'assigned', 'edited'],
  issue_comment: ['created', 'edited'],
  pull_request: ['opened', 'assigned', 'review_requested', 'edited'],
  pull_request_approved: ['reviewed'],
  pull_request_rejected: ['reviewed'],
  action_run_failure: ['failure'],
  action_run_success: ['success'],
});
const familyPattern = /^[a-z][a-z_]*$/;
const repositoryPattern = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}\/[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$/;
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const keyPrefix = 'forgejo-work-v1';
const ignoredKey = 'forgejo-ignored-v1';
const quote = value => JSON.stringify(value);

// Fail closed on ambiguous or malformed policy, including case-fold collisions.
export function validateMappingPolicy(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).sort().join(',') !== 'actors,families,repositories') throw new Error('mapping_policy');
  const { actors, families, repositories } = value;
  if (!Array.isArray(families) || !families.length || families.length > Object.keys(familyActions).length
      || families.some(x => typeof x !== 'string' || !Object.hasOwn(familyActions, x))
      || new Set(families).size !== families.length) throw new Error('mapping_families');
  if (!Array.isArray(repositories) || !repositories.length || repositories.length > 128
      || repositories.some(x => typeof x !== 'string' || !repositoryPattern.test(x)
        || x.split('/').some(part => part === '.' || part === '..'))
      || new Set(repositories.map(x => x.toLowerCase())).size !== repositories.length) throw new Error('mapping_repositories');
  if (!Array.isArray(actors) || !actors.length || actors.length > 128
      || actors.some(x => typeof x !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$/.test(x))
      || new Set(actors.map(x => x.toLowerCase())).size !== actors.length) throw new Error('mapping_actors');
  return Object.freeze({ actors: Object.freeze(actors.map(x => x.toLowerCase())), families: Object.freeze([...families]),
    repositories: Object.freeze(repositories.map(x => x.toLowerCase())) });
}

// Family is kept in the trigger prefix and the delivery ID in the suffix. The
// UUID is correlation data only; it does not authenticate the sender or a job.
export function parseTriggerKey(key) {
  if (typeof key !== 'string') return null;
  const parts = key.split(':');
  if (parts.length !== 3 || parts[0] !== keyPrefix || !familyPattern.test(parts[1])
      || !Object.hasOwn(familyActions, parts[1]) || !uuidPattern.test(parts[2])) return null;
  return Object.freeze({ family: parts[1], deliveryId: parts[2] });
}

export function triggerPattern(family) {
  if (!Object.hasOwn(familyActions, family)) throw new Error('mapping_family');
  return `${keyPrefix}:${family}:*`;
}

// Expressions run after native HMAC validation. A successful non-matching key
// still creates a native event; operators must reserve the ignored key namespace
// and ensure no broader application workflow trigger subscribes to it.
export function eventKeyExpression(policy) {
  const { families } = validateMappingPolicy(policy);
  const familyCases = families.map(family => {
    const repo = family.startsWith('action_run_') ? 'input.run.repository.full_name' : 'input.repository.full_name';
    const access = family.startsWith('action_run_')
      ? "has(input.run) && has(input.run.repository) && has(input.run.repository.full_name)"
      : "has(input.repository) && has(input.repository.full_name)";
    const admitted = `${access} && type(${repo}) == string && ${repo}.lowerAscii() in input.__forgejo_policy_repositories`;
    const actions = JSON.stringify(familyActions[family]);
    const actor = family.startsWith('action_run_') ? 'input.run.trigger_user.login' : 'input.sender.login';
    const actorAccess = family.startsWith('action_run_')
      ? 'has(input.run.trigger_user) && has(input.run.trigger_user.login)'
      : 'has(input.sender) && has(input.sender.login)';
    let extra;
    if (family.startsWith('action_run_')) {
      const statuses = family === 'action_run_failure' ? ['failure', 'cancelled', 'skipped'] : ['success'];
      extra = ` && has(input.run.event) && input.run.event == 'pull_request' && has(input.run.status) && input.run.status in ${JSON.stringify(statuses)}`;
    } else {
      const subject = family === 'issues' || family === 'issue_comment' ? 'input.issue' : 'input.pull_request';
      extra = ` && has(${subject}) && has(${subject}.state) && ${subject}.state == 'open'`;
      if (family === 'pull_request') extra += ` && has(${subject}.draft) && ${subject}.draft == false`;
      if (family === 'issues' || family === 'pull_request') extra += " && (input.action != 'edited' || (has(input.changes) && has(input.changes.body)))";
    }
    return `(headers['x-forgejo-event'] == ${quote(family)} && ${admitted} && has(input.action) && type(input.action) == string && input.action in ${actions} && ${actorAccess} && type(${actor}) == string && ${actor}.lowerAscii() in input.__forgejo_policy_actors${extra})`;
  }).join(' || ');
  return `('content-type' in headers && headers['content-type'].split(';')[0].trim().lowerAscii() == 'application/json' && 'x-forgejo-delivery' in headers && headers['x-forgejo-delivery'].matches('^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') && 'x-forgejo-signature' in headers && headers['x-forgejo-signature'].matches('^[0-9a-fA-F]{64}$') && 'x-forgejo-event' in headers && (${familyCases})) ? ${quote(keyPrefix + ':')} + headers['x-forgejo-event'] + ':' + headers['x-forgejo-delivery'] : ${quote(ignoredKey)}`;
}

// Native static payload overwrites same-named webhook body keys before CEL.
// Treat this object as protected configuration; do not log or print it.
export function staticPayload(policy) {
  const { actors, repositories } = validateMappingPolicy(policy);
  return { __forgejo_policy_actors: [...actors], __forgejo_policy_repositories: [...repositories] };
}
