// Parse only the fields used to identify and revalidate work. Webhook content is
// untrusted and is never used as an instruction, URL, role or execution policy.
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = value => typeof value === 'string';
const login = value => text(value) && /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$/.test(value);
const number = value => Number.isSafeInteger(value) && value > 0;
const url = value => {
  if (!text(value) || value.length > 2048 || value.trim() !== value || /[\r\n\t]/.test(value)) return false;
  try { const parsed = new URL(value); return ['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password; }
  catch { return false; }
};
const sha = value => text(value) && /^[a-f0-9]{40,64}$/i.test(value);
const repo = value => text(value) && /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}\/[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$/.test(value);
const assignees = value => value === null || (Array.isArray(value) && value.every(x => object(x) && login(x.login)));
const record = (value, field) => { if (!object(value)) throw new Error(field); return value; };
const required = (condition, field) => { if (!condition) throw new Error(field); };

function subject(payload, key, requireTopNumber = true) {
  const item = record(payload[key], 'subject');
  required(number(item.number), 'number');
  if (requireTopNumber) required(payload.number === item.number, 'number_mismatch');
  required(item.state === 'open' || item.state === 'closed', 'state');
  return item;
}
function ordinary(payload, family) {
  const isComment = family === 'issue_comment';
  const isPull = family === 'pull_request';
  const item = subject(payload, isPull ? 'pull_request' : 'issue', !isComment);
  const actions = isComment ? ['created', 'edited'] : isPull
    ? ['opened', 'assigned', 'review_requested', 'edited'] : ['opened', 'assigned', 'edited'];
  required(actions.includes(payload.action), 'action');
  required(login(payload.sender?.login), 'sender');
  if (isComment) {
    const comment = record(payload.comment, 'comment');
    required(number(comment.id) && text(comment.body) && url(comment.html_url)
      && text(item.title) && url(item.html_url), 'comment_shape');
    return { kind: 'comment', number: item.number, commentId: comment.id,
      actor: payload.sender.login, text: comment.body, state: item.state };
  }
  required(text(item.body) && text(item.title) && url(item.html_url) && assignees(item.assignees), 'subject_shape');
  if (payload.action === 'edited') {
    const changes = record(payload.changes, 'changes');
    if (!Object.hasOwn(changes, 'body')) return null;
    required(object(changes.body) && text(changes.body.from), 'body_change');
  }
  if (!isPull) return { kind: 'issue', number: item.number, actor: payload.sender.login,
    state: item.state, text: item.body, assignees: item.assignees ?? [] };
  required(typeof item.draft === 'boolean' && object(item.head) && sha(item.head.sha)
    && assignees(item.requested_reviewers), 'pull_shape');
  if (payload.action === 'review_requested') required(login(payload.requested_reviewer?.login), 'reviewer');
  return { kind: 'pull', number: item.number, actor: payload.sender.login, state: item.state,
    draft: item.draft, head: item.head.sha.toLowerCase(), text: item.body,
    assignees: item.assignees ?? [], reviewers: item.requested_reviewers ?? [],
    requestedReviewer: payload.requested_reviewer?.login ?? null };
}
function review(payload, family) {
  const item = subject(payload, 'pull_request');
  const review = record(payload.review, 'review');
  const allowed = family === 'pull_request_approved'
    ? ['pull_request_approved', 'pull_request_review_approved']
    : ['pull_request_rejected', 'pull_request_review_rejected'];
  required(payload.action === 'reviewed' && Object.hasOwn(review, 'type')
    && (review.type === null || allowed.includes(review.type)) && text(review.content)
    && login(payload.sender?.login), 'review_shape');
  return { kind: 'review', number: item.number, actor: payload.sender.login,
    state: item.state, decision: family === 'pull_request_approved' ? 'APPROVED' : 'REQUEST_CHANGES',
    content: review.content };
}
function action(payload, family, repository) {
  const run = record(payload.run, 'run');
  const failure = family === 'action_run_failure';
  required(payload.action === (failure ? 'failure' : 'success')
    && (failure ? ['failure', 'cancelled', 'skipped'] : ['success']).includes(run.status)
    && number(run.id) && sha(run.commit_sha) && text(run.workflow_id) && run.workflow_id.length > 0
    && text(run.title) && run.title.length > 0 && url(run.html_url) && login(run.trigger_user?.login), 'run_shape');
  required(text(run.event) && (run.event === '' || run.event.trim().length > 0), 'run_event');
  if (run.event !== 'pull_request') return null;
  required(text(run.event_payload) && run.event_payload.length > 0, 'event_payload');
  let nested; try { nested = JSON.parse(run.event_payload); } catch { throw new Error('event_payload'); }
  record(nested, 'event_payload');
  const pull = record(nested.pull_request, 'nested_pull');
  required(number(pull.number) && (!Object.hasOwn(nested, 'number') || nested.number === pull.number), 'nested_number');
  if (Object.hasOwn(nested, 'repository')) {
    required(object(nested.repository) && repo(nested.repository.full_name)
      && nested.repository.full_name.toLowerCase() === repository.toLowerCase(), 'nested_repository');
  }
  return { kind: 'action', number: pull.number, actor: run.trigger_user.login,
    runId: run.id, head: run.commit_sha.toLowerCase(), failure };
}

export function decodeEvent(family, payload) {
  try {
    record(payload, 'payload');
    const actionFamily = family === 'action_run_failure' || family === 'action_run_success';
    const repoObject = actionFamily ? payload.run?.repository : payload.repository;
    const actorObject = actionFamily ? payload.run?.trigger_user : payload.sender;
    const repository = repoObject?.full_name;
    required(repo(repository) && number(repoObject?.id) && number(actorObject?.id), 'repository_or_actor');
    let item;
    if (['issues', 'issue_comment', 'pull_request'].includes(family)) item = ordinary(payload, family);
    else if (['pull_request_approved', 'pull_request_rejected'].includes(family)) item = review(payload, family);
    else if (actionFamily) item = action(payload, family, repository);
    else return { outcome: 'rejected' };
    if (item === null) return { outcome: 'skipped' };
    return { outcome: 'candidate', event: Object.freeze({ ...item, repository, repositoryId: repoObject.id, actorId: actorObject.id, action: payload.action, family }) };
  } catch { return { outcome: 'rejected' }; }
}
