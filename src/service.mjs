import { createHash, randomUUID } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { fixture } from './fixtures.mjs';
import { generateCandidate, validateInput, verifyCandidate } from './planner.mjs';

export class ServiceError extends Error {
  constructor(message, status = 409, details = []) { super(message); this.status = status; this.details = details; }
}
export const id = prefix => `${prefix}-${randomUUID().slice(0,8)}`;
export function freshState(partial = true) {
  return { schema_version: 1, input: fixture(partial), input_revision: 1, runtime_revision: 0, clock_s: 0, delivered: {}, task_states: {}, ready_s: {}, plans: [], approvals: [], active_plan_id: null, active_approval_id: null, run: null, events: [], exceptions: [], archives: [], state_version: 1, planning_failure: null };
}
export function snapshot(s) {
  const payload = { input: s.input, input_revision: s.input_revision, runtime_revision: s.runtime_revision, clock_s: s.clock_s, delivered: s.delivered, ready_s: s.ready_s };
  return 'S-' + createHash('sha256').update(JSON.stringify(payload)).digest('hex').slice(0,16);
}
export function checkpoint(s) { return { clock_s: s.clock_s, delivered_ids: Object.keys(s.delivered), ready_s: structuredClone(s.ready_s) }; }
export function activePlan(s) { return s.plans.find(p => p.plan_id === s.active_plan_id) || null; }
export function activeApproval(s) { return s.approvals.find(a => a.approval_id === s.active_approval_id) || null; }
function event(s, type, message, fields = {}) { s.events.push({ event_id: id('E'), event_type: type, event_time: s.clock_s, message, run_id: s.run?.run_id || null, ...fields }); }

function invalidate(s, reason, before = null, after = null) {
  const old = activePlan(s);
  for (const p of s.plans) if (p.status === 'Suggested') p.status = 'Stale';
  const a = activeApproval(s); if (a) a.status = 'Invalidated';
  s.active_approval_id = null;
  const hadRun = s.run && !['Finished', 'Ended'].includes(s.run.status);
  const affected = [];
  if (hadRun) {
    s.run.status = 'Needs replan';
    for (const x of old?.assignments || []) if (!s.delivered[x.task_id]) {
      s.task_states[x.task_id] = 'Interrupted'; affected.push(x.task_id);
    }
    s.run.pending_events = [];
    s.runtime_revision++;
  }
  const ex = { event_id: id('X'), time_s: s.clock_s, reason, before, after, old_plan_id: old?.plan_id || null, affected_task_ids: affected, delivered_ids: Object.keys(s.delivered), rollback: Boolean(hadRun), resolved: false };
  s.exceptions.push(ex);
  event(s, 'input_changed', reason, { before, after, affected_ids: affected, rollback: ex.rollback });
}

export function saveInput(s, input) {
  const errors = validateInput(input); if (errors.length) throw new ServiceError('Input validation failed.', 422, errors);
  for (const taskID of Object.keys(s.delivered)) {
    const previous = s.input.tasks.find(t => t.id === taskID), next = input.tasks.find(t => t.id === taskID);
    if (!isDeepStrictEqual(previous, next)) throw new ServiceError('Delivered tasks are locked. Create a new task for another delivery.');
  }
  if (isDeepStrictEqual(input, s.input)) return;
  const before = structuredClone(s.input); s.input = structuredClone(input); s.input_revision++;
  invalidate(s, 'Planning inputs changed; the previous approval is invalid.', before, input);
}

// A delayed planner may only install results for the exact captured snapshot.
export function installCandidate(s, candidate, snapshotID, sourceInput, sourceCheckpoint) {
  const checks = verifyCandidate(sourceInput, sourceCheckpoint, candidate);
  if (!checks.ok) throw new ServiceError('Calculation failed. Candidate validation failed.', 422, checks.errors);
  const current = snapshot(s) === snapshotID;
  const plan = { ...structuredClone(candidate), checks, plan_id: id('P'), snapshot_id: snapshotID, input_revision: s.input_revision, status: current ? 'Suggested' : 'Stale', created_at: new Date().toISOString(), input_snapshot: structuredClone(sourceInput), checkpoint: structuredClone(sourceCheckpoint) };
  s.plans.push(plan);
  if (!current) return plan;
  const a = activeApproval(s); if (a) a.status = 'Invalidated';
  s.active_approval_id = null;
  for (const p of s.plans) if (p !== plan && p.status === 'Suggested') p.status = 'Stale';
  s.active_plan_id = plan.plan_id;
  s.planning_failure = null;
  for (const t of s.input.tasks) if (!s.delivered[t.id]) s.task_states[t.id] = plan.assignments.some(x => x.task_id === t.id) ? 'Assigned' : 'Unassigned';
  event(s, 'plan_calculated', `${plan.plan_id}: ${plan.assignments.length} assigned, ${plan.unassigned.length} unassigned.`);
  return plan;
}

export function plan(s, planner = generateCandidate) {
  if (s.run && ['Running', 'Paused'].includes(s.run.status)) throw new ServiceError('Change inputs or finish the current run before replanning.');
  const snap = snapshot(s), input = structuredClone(s.input), cp = checkpoint(s);
  try {
    const candidate = planner(input, cp);
    return installCandidate(s, candidate, snap, input, cp);
  } catch (error) {
    const a = activeApproval(s); if (a) a.status = 'Invalidated';
    s.active_approval_id = null;
    for (const p of s.plans) if (p.status === 'Suggested') p.status = 'Stale';
    s.planning_failure = { code: 'CALCULATION_ERROR', message: 'Calculation failed. No new plan was created.', detail: String(error.message), snapshot_id: snap };
    event(s, 'calculation_failed', s.planning_failure.message);
    return null;
  }
}

export function approve(s, body) {
  const p = activePlan(s);
  if (!p || p.plan_id !== body.plan_id || p.snapshot_id !== body.snapshot_id || p.snapshot_id !== snapshot(s) || p.status !== 'Suggested') throw new ServiceError('Plan is out of date. Recalculate before approval.');
  if (!p.assignments.length) throw new ServiceError('No assigned tasks to approve.');
  if (!verifyCandidate(s.input, checkpoint(s), p).ok) throw new ServiceError('Independent validation failed. Recalculate.');
  if (p.unassigned.length && (body.acknowledged_unassigned?.length !== p.unassigned.length || p.unassigned.some(u => !body.acknowledged_unassigned.includes(u.task_id)))) throw new ServiceError('Acknowledge the unassigned tasks to continue.');
  const existing = activeApproval(s); if (existing?.plan_id === p.plan_id && existing.status === 'Approved') return existing;
  const a = { approval_id: id('A'), plan_id: p.plan_id, snapshot_id: p.snapshot_id, approved_task_ids: p.assignments.map(a => a.task_id), acknowledged_unassigned: p.unassigned.map(u => u.task_id), actor_label: String(body.actor_label || 'Demo dispatcher').slice(0,80), recorded_sim_time: s.clock_s, status: 'Approved' };
  s.approvals.push(a); s.active_approval_id = a.approval_id;
  event(s, 'approved', `Approved ${a.approved_task_ids.join(', ')} for simulation.`, { approval_id: a.approval_id });
  return a;
}

function authorize(s) {
  const a = activeApproval(s), p = activePlan(s);
  if (!a || a.status !== 'Approved' || !p || a.plan_id !== p.plan_id) throw new ServiceError('Approval is no longer valid. Review a new plan before resuming.');
  const sameRun = s.run?.approval_id === a.approval_id && ['Running','Paused','Finished'].includes(s.run.status);
  if (!sameRun && a.snapshot_id !== snapshot(s)) throw new ServiceError('The approved snapshot is out of date.');
  return { a, p };
}

export function start(s) {
  const { a, p } = authorize(s);
  if (s.run?.approval_id === a.approval_id && s.run.status === 'Running') return;
  if (s.run?.approval_id === a.approval_id && s.run.status === 'Finished') return;
  if (s.run?.approval_id === a.approval_id && s.run.status === 'Paused') { s.run.status = 'Running'; event(s,'resumed','Simulation resumed.'); return; }
  if (a.snapshot_id !== snapshot(s)) throw new ServiceError('The approved snapshot is out of date.');
  const events = p.assignments.flatMap(x => [
    { type: 'departure', at: x.depart_s, assignment: x, rank: 0 },
    { type: 'arrival', at: x.arrival_s, assignment: x, rank: 1 },
    { type: 'service_completed', at: x.service_end_s, assignment: x, rank: 2 },
    { type: 'returned', at: x.return_s, assignment: x, rank: 3 }
  ]).sort((a,b) => a.at - b.at || a.rank - b.rank || a.assignment.task_id.localeCompare(b.assignment.task_id));
  s.run = { run_id: s.run?.status === 'Needs replan' ? s.run.run_id : id('R'), plan_id: p.plan_id, approval_id: a.approval_id, status: 'Running', pending_events: events, result: null };
  for (const x of p.assignments) if (!s.delivered[x.task_id]) s.task_states[x.task_id] = 'Waiting';
  for (const ex of s.exceptions) ex.resolved = true;
  event(s, 'started', `Simulation using approved plan ${p.plan_id}.`);
}

export function advance(s, seconds) {
  authorize(s);
  if (s.run?.status !== 'Running') throw new ServiceError('Start or resume simulation before advancing time.');
  if (!Number.isSafeInteger(seconds) || seconds < 0 || seconds > 86400) throw new ServiceError('Use a nonnegative integer step in seconds.',422);
  const target = s.clock_s + seconds;
  while (s.run.pending_events.length && s.run.pending_events[0].at <= target) {
    const e = s.run.pending_events.shift(), x = e.assignment;
    s.clock_s = e.at;
    const vehicle = s.input.vehicles.find(v => v.id === x.vehicle_id);
    if (e.type === 'departure') s.task_states[x.task_id] = 'Travelling';
    if (e.type === 'arrival') {
      s.task_states[x.task_id] = 'Serving';
      s.run.arrivals ||= {}; s.run.arrivals[x.task_id] = e.at;
    }
    if (e.type === 'service_completed') {
      s.task_states[x.task_id] = 'Delivered';
      s.delivered[x.task_id] = { task_id: x.task_id, arrival_s: x.arrival_s, service_end_s: e.at, vehicle_id: x.vehicle_id, plan_id: s.run.plan_id, run_id: s.run.run_id, task_snapshot: structuredClone(s.input.tasks.find(t => t.id === x.task_id)) };
    }
    if (e.type === 'returned') s.ready_s[x.vehicle_id] = e.at + vehicle.turnaround_s;
    s.runtime_revision++;
    event(s, e.type, `${x.task_id} · ${x.vehicle_id} · ${e.type.replaceAll('_',' ')}`, { task_id: x.task_id, vehicle_id: x.vehicle_id, trip_id: x.trip_id });
  }
  if (!s.run.pending_events.length) {
    s.run.status = 'Finished';
    const remaining = s.input.tasks.length - Object.keys(s.delivered).length;
    s.run.result = remaining ? `Assigned tasks completed; ${remaining} task${remaining === 1 ? ' remains' : 's remain'} unassigned.` : 'All tasks completed in simulation.';
    event(s, 'finished', s.run.result);
  } else if (s.clock_s !== target) { s.clock_s = target; s.runtime_revision++; }
}

export function unavailable(s, vehicleID) {
  const v = s.input.vehicles.find(v => v.id === vehicleID);
  if (!v) throw new ServiceError('Unknown vehicle.',422);
  if (!v.available) return;
  v.available = false; s.input_revision++;
  invalidate(s, `${vehicleID} became unavailable.`, { vehicle_id: v.id, availability: 'Available' }, { vehicle_id: v.id, availability: 'Unavailable' });
  event(s, 'device_unavailable', `${vehicleID} unavailable; new plan requires approval.`, { vehicle_id: v.id });
}

export function applyAction(s, action, body = {}) {
  if (action === 'input') saveInput(s, body.input);
  else if (action === 'plan') plan(s);
  else if (action === 'approve') approve(s, body);
  else if (action === 'start' || action === 'resume') start(s);
  else if (action === 'advance') advance(s, body.seconds);
  else if (action === 'pause') { authorize(s); if (s.run?.status === 'Running') { s.run.status = 'Paused'; event(s,'paused','Simulation paused; approval remains valid.'); } }
  else if (action === 'unavailable') unavailable(s, body.vehicle_id);
  else if (action === 'keep-unassigned') {
    const p = activePlan(s);
    if (!p || p.status === 'Stale') throw new ServiceError('Calculate a current plan before keeping unassigned tasks.');
    event(s, 'tasks_deferred', `Kept unassigned tasks for review: ${p.unassigned.map(u => u.task_id).join(', ') || 'None'}.`, { task_ids: p.unassigned.map(u => u.task_id) });
  }
  else if (action === 'end') {
    if (!s.run || ['Finished','Ended'].includes(s.run.status)) throw new ServiceError('No unfinished simulation to end.');
    s.run.status = 'Ended'; s.run.pending_events = []; s.run.result = 'Simulation ended with unfinished tasks.';
    const a = activeApproval(s); if (a) a.status = 'Invalidated'; s.active_approval_id = null;
    const p = activePlan(s); if (p) p.status = 'Stale';
    for (const t of s.input.tasks) if (!s.delivered[t.id] && s.task_states[t.id] !== 'Unassigned') s.task_states[t.id] = 'Interrupted';
    event(s,'ended',s.run.result);
  }
  else if (action === 'reset') {
    const archive = { archive_id: id('H'), archived_at: new Date().toISOString(), input: s.input, input_revision: s.input_revision, plans: s.plans, approvals: s.approvals, delivered: s.delivered, run: s.run, events: s.events, exceptions: s.exceptions };
    const archives = [...s.archives, archive], revision = s.input_revision + 1, version = s.state_version;
    Object.assign(s, freshState(body.scenario !== 'normal'), { archives, input_revision: revision, state_version: version });
  }
  else throw new ServiceError('Unknown action.',404);
  s.state_version++;
  return s;
}

export function viewState(s) {
  const p = activePlan(s), a = activeApproval(s);
  return { ...s, snapshot_id: snapshot(s), current_plan: p, current_approval: a, input_errors: validateInput(s.input), can_start: Boolean(a?.status === 'Approved' && p && (a.snapshot_id === snapshot(s) || (s.run?.approval_id === a.approval_id && ['Running','Paused'].includes(s.run.status)))) };
}
