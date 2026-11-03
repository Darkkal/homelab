// Canonical state, not event text or Hatchet labels, authorizes the job.
const roleNames = ['planner', 'worker', 'reviewer'];
const norm = x => typeof x === 'string' ? x.toLowerCase() : '';
const author = item => norm(item?.user?.login);
const head = pull => norm(pull?.head?.sha);
const safe = x => typeof x === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$/.test(x);
const skip = reason => ({ outcome: 'skipped', reason });
const unknown = reason => ({ outcome: 'unknown', reason });
const mentions = (body, account) => {
  if (typeof body !== 'string' || !safe(account)) return false;
  return [...body.matchAll(/(?<![\w.-])@([\w.-]*\w)/g)].some(x => norm(x[1]) === norm(account));
};
const names = list => Array.isArray(list) ? list.map(x => norm(x?.login)).filter(Boolean) : [];

export function validateRoutePolicy(policy) {
  if (!policy || typeof policy !== 'object' || Array.isArray(policy)
      || Object.keys(policy).sort().join(',') !== 'owners,requiredChecks,reviewers,roles'
      || !policy.roles || typeof policy.roles !== 'object'
      || Object.keys(policy.roles).sort().join(',') !== 'planner,reviewer,worker'
      || roleNames.some(role => !safe(policy.roles[role]))
      || new Set(roleNames.map(role => norm(policy.roles[role]))).size !== 3
      || !Array.isArray(policy.owners) || !policy.owners.length
      || !policy.owners.every(safe) || !Array.isArray(policy.reviewers)
      || !policy.reviewers.length || !policy.reviewers.every(safe)
      || !Array.isArray(policy.requiredChecks) || !policy.requiredChecks.length || policy.requiredChecks.length > 64
      || policy.requiredChecks.some(x => typeof x !== 'string' || !x || x.length > 128)
      || new Set(policy.requiredChecks).size !== policy.requiredChecks.length) throw new Error('route_policy');
  return Object.freeze({ roles: Object.freeze({ ...policy.roles }), owners: Object.freeze([...policy.owners]),
    reviewers: Object.freeze([...policy.reviewers]), requiredChecks: Object.freeze([...policy.requiredChecks]) });
}

// Reader exceptions and insufficient canonical evidence stop without dispatch.
export async function decide(event, rawPolicy, reader) {
  const policy = validateRoutePolicy(rawPolicy);
  const { repository: repo, number, actor, kind } = event;
  if (!safe(actor) || !Number.isSafeInteger(number) || number < 1) return skip('invalid_identity');
  try {
    const item = kind === 'issue' || kind === 'comment'
      ? await reader.issue(repo, number) : await reader.pull(repo, number);
    if (item?.number !== number || item?.state !== 'open') return skip('closed_or_mismatch');
    const isPull = kind !== 'issue' && kind !== 'comment' || kind === 'comment' && !!item.pull_request;
    const pull = isPull && kind === 'comment' ? await reader.pull(repo, number) : item;
    if (isPull && (pull?.number !== number || pull.state !== 'open' || pull.draft !== false
        || !/^[a-f0-9]{40,64}$/.test(head(pull)))) return skip('draft_or_head_unknown');
    if ((kind === 'pull' || kind === 'action') && event.head !== head(pull)) return skip('stale_head');
    const permission = await reader.actor(repo, actor, { kind, action: event.action, number, head: isPull ? head(pull) : '' });
    if (permission?.outcome === 'denied') return skip('actor_not_authorized');
    if (permission?.outcome !== 'allowed' || !Number.isSafeInteger(permission.actorId)
        || permission.actorId < 1 || !Number.isSafeInteger(permission.repositoryId) || permission.repositoryId < 1)
      return unknown('permission_unavailable');
    if (permission.actorId !== event.actorId || permission.repositoryId !== event.repositoryId) return unknown('identity_mismatch');
    let targets = [];
    let reviewId = null;
    if (kind === 'review') {
      if (!author(item) || author(item) === norm(actor)) return skip('review_not_independent');
      const reviews = await reader.reviews(repo, number);
      if (!Array.isArray(reviews) || reviews.length >= 50) return unknown('reviews_incomplete');
      if (reviews.some(r => !r || !Number.isSafeInteger(r.id) || typeof r.state !== 'string'
          || !['APPROVED', 'REQUEST_CHANGES', 'COMMENT', 'PENDING', 'REQUEST_REVIEW'].includes(r.state)
          || typeof r.official !== 'boolean' || typeof r.dismissed !== 'boolean' || typeof r.stale !== 'boolean')) return unknown('review_state_unknown');
      const candidates = reviews.filter(r => r.official && !r.dismissed && !r.stale
        && author(r) === norm(actor) && r.state === event.decision
        && (r.body ?? '') === event.content && norm(r.commit_id) === head(item));
      if (candidates.length !== 1 || !policy.reviewers.some(x => norm(x) === norm(actor))) return skip('review_untrusted_or_ambiguous');
      if (reviews.some(r => r.dismissed && author(r) === norm(actor) && r.id >= candidates[0].id)) return skip('review_dismissed');
      // An effective decision must be the most recent decisive trusted review;
      // require complete, sortable timestamps and current-head identities.
      const decisions = reviews.filter(r => r.official && !r.dismissed && !r.stale
        && ['APPROVED', 'REQUEST_CHANGES'].includes(r.state)
        && policy.reviewers.some(x => norm(x) === author(r)) && norm(r.commit_id) === head(item));
      if (decisions.some(r => typeof r.submitted_at !== 'string' || !Number.isFinite(Date.parse(r.submitted_at)))) return unknown('review_order_unknown');
      decisions.sort((a, b) => Date.parse(b.submitted_at) - Date.parse(a.submitted_at));
      if (decisions.length > 1 && decisions[0].submitted_at === decisions[1].submitted_at) return unknown('review_order_ambiguous');
      if (decisions[0]?.id !== candidates[0].id) return skip('review_superseded');
      reviewId = candidates[0].id;
      targets = [event.decision === 'REQUEST_CHANGES' ? 'worker' : 'reviewer'];
    } else if (kind === 'action') {
      if (event.failure) targets = ['worker'];
      else {
        const status = await reader.status(repo, head(item));
        if (norm(status?.sha) !== head(item) || status?.state !== 'success'
            || !Array.isArray(status.statuses) || status.statuses.length === 0) return skip('ci_not_successful');
        for (const context of policy.requiredChecks) {
          const matching = status.statuses.filter(result => result.context === context);
          if (matching.length !== 1 || matching[0].status !== 'success') return skip('required_check_not_successful');
        }
        targets = ['reviewer'];
      }
    } else {
      let body = item.body;
      if (kind === 'comment') {
        const comment = await reader.comment(repo, event.commentId);
        if (comment?.id !== event.commentId || author(comment) !== norm(actor)
            || typeof comment.body !== 'string' || comment.body !== event.text
            || typeof item.html_url !== 'string'
            || ![comment.issue_url, comment.pull_request_url].includes(item.html_url)) return skip('comment_stale');
        body = comment.body;
      }
      if (typeof body !== 'string') return unknown('body_unknown');
      if (kind !== 'comment' && ['opened', 'edited'].includes(event.action) && body !== event.text) return skip('body_stale');
      const structural = event.action === 'edited' || kind === 'comment' ? []
        : event.action === 'review_requested' ? names(item.requested_reviewers)
        : [...names(item.assignees), ...(kind === 'pull' && event.action === 'opened' ? names(item.requested_reviewers) : [])];
      if (event.action === 'review_requested') {
        if (!names(item.requested_reviewers).includes(norm(event.requestedReviewer))) return skip('request_stale');
        structural.splice(0, structural.length, norm(event.requestedReviewer));
      }
      const useMentions = kind === 'comment' || event.action === 'opened' || event.action === 'edited';
      targets = roleNames.filter(role => structural.includes(norm(policy.roles[role])) || (useMentions && mentions(body, policy.roles[role])));
      if (!targets.length && kind === 'comment' && policy.owners.some(x => norm(x) === norm(actor))) targets = ['planner'];
    }
    targets = targets.filter(role => (kind === 'action' && event.failure || norm(policy.roles[role]) !== norm(actor))
      && (role !== 'reviewer' || (author(item) && author(item) !== norm(policy.roles.reviewer))));
    if (!targets.length) return skip('no_eligible_target');
    return { outcome: 'ready', roles: Object.freeze(targets),
      intent: Object.freeze({ repository: repo, repositoryId: permission.repositoryId, actorId: permission.actorId,
        number, head: isPull ? head(pull) : null, kind, actor, action: event.action,
        commentId: event.commentId ?? null, runId: event.runId ?? null, reviewId }) };
  } catch { return unknown('canonical_read_failed'); }
}
