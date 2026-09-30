export const REASONS = {
  NO_AVAILABLE_VEHICLE: ['No eligible vehicle is available.', 'Review eligibility or availability.'],
  PAYLOAD_EXCEEDED: ['Load exceeds available payload.', 'Change load or resources.'],
  NO_ROUTE: ['No allowed route is available.', 'Review travel data.'],
  TIME_WINDOW_UNREACHABLE: ['No checked assignment meets the arrival window.', 'Review window or resources.'],
  RETURN_BUDGET_EXCEEDED: ['Trip exceeds the return budget.', 'Review route or vehicle.'],
  SHIFT_LIMIT_EXCEEDED: ['Return would exceed the shift limit.', 'Review schedule.'],
  SEARCH_NO_ASSIGNMENT: ['Search did not find an assignment.', 'Retry or revise inputs.']
};

export function validateInput(input) {
  const errors = [];
  const add = (field, message) => errors.push({ field, message });
  if (!input || input.rule_profile_id !== 'demo-v1') add('rule_profile_id', 'Unknown rule profile. Use demo-v1.');
  if (!Array.isArray(input?.tasks) || input.tasks.length > 200) add('tasks', 'Provide an array of at most 200 tasks.');
  if (!Array.isArray(input?.vehicles) || input.vehicles.length > 30) add('vehicles', 'Provide an array of at most 30 vehicles.');
  const ids = new Set();
  for (const [i, t] of (Array.isArray(input?.tasks) ? input.tasks : []).entries()) {
    const p = `tasks.${i}`;
    if (!t || typeof t.id !== 'string' || !/^[A-Za-z0-9_-]{1,40}$/.test(t.id) || ids.has(t.id)) add(`${p}.id`, 'Use a unique task ID (letters, numbers, underscore or hyphen).');
    ids.add(t?.id);
    if (!t || typeof t.station !== 'string' || !/^[A-Za-z0-9_-]{1,40}$/.test(t.station)) add(`${p}.station`, 'Enter a station ID.');
    if (!Number.isFinite(t?.load_kg) || t.load_kg <= 0) add(`${p}.load_kg`, 'Enter a load greater than 0 kg.');
    for (const f of ['window_start_s', 'window_end_s', 'service_s']) if (!Number.isSafeInteger(t?.[f]) || t[f] < 0 || t[f] > 86400) add(`${p}.${f}`, 'Use integer seconds within the simulation day.');
    if (t?.window_start_s > t?.window_end_s) add(`${p}.window_end_s`, 'End time must not precede start time.');
    if (!Array.isArray(t?.eligible_types) || !t.eligible_types.length || t.eligible_types.some(x => !['UAV', 'AGV'].includes(x))) add(`${p}.eligible_types`, 'Choose UAV, AGV or both.');
    if (t && Array.isArray(t.eligible_types) && !t.eligible_types.some(type => Object.hasOwn(input?.distances_m?.[type] || {}, t.station))) add(`${p}.station`, 'Travel time is missing for this station.');
  }
  ids.clear();
  for (const [i, v] of (Array.isArray(input?.vehicles) ? input.vehicles : []).entries()) {
    const p = `vehicles.${i}`;
    if (!v || typeof v.id !== 'string' || !/^[A-Za-z0-9_-]{1,40}$/.test(v.id) || ids.has(v.id)) add(`${p}.id`, 'Use a unique vehicle ID.');
    ids.add(v?.id);
    if (!['UAV', 'AGV'].includes(v?.type)) add(`${p}.type`, 'Choose UAV or AGV.');
    if (typeof v?.available !== 'boolean') add(`${p}.available`, 'Availability must be true or false.');
    for (const f of ['capacity_kg', 'speed_m_s']) if (!Number.isFinite(v?.[f]) || v[f] <= 0) add(`${p}.${f}`, 'Enter a positive value.');
    for (const f of ['trip_limit_s', 'shift_end_s', 'turnaround_s']) if (!Number.isSafeInteger(v?.[f]) || v[f] < (f === 'trip_limit_s' ? 1 : 0) || v[f] > 86400) add(`${p}.${f}`, 'Enter valid integer seconds.');
  }
  if (!input?.distances_m || typeof input.distances_m !== 'object' || Array.isArray(input.distances_m)) add('distances_m', 'Provide type-specific distance data.');
  for (const type of ['UAV', 'AGV']) for (const [station, distance] of Object.entries(input?.distances_m?.[type] || {})) {
    if (distance !== null && (!Number.isFinite(distance) || distance < 0)) add(`distances_m.${type}.${station}`, 'Distance must be nonnegative metres, or null for no route.');
  }
  return errors;
}

function checkCandidate(input, task, vehicle, ready, tripNumber) {
  const reasons = [];
  if (!vehicle.available || !task.eligible_types.includes(vehicle.type)) reasons.push('NO_AVAILABLE_VEHICLE');
  if (task.load_kg > vehicle.capacity_kg) reasons.push('PAYLOAD_EXCEEDED');
  const distance = input.distances_m[vehicle.type]?.[task.station];
  const evidence = { vehicle_id: vehicle.id, available: vehicle.available, eligible: task.eligible_types.includes(vehicle.type), load_kg: task.load_kg, capacity_kg: vehicle.capacity_kg, distance_m: distance ?? null, ready_s: ready };
  if (!Number.isFinite(distance)) reasons.push('NO_ROUTE');
  let assignment = null;
  if (Number.isFinite(distance)) {
    const travel = Math.ceil(distance / vehicle.speed_m_s);
    const depart = Math.max(ready, task.window_start_s - travel);
    const arrival = depart + travel;
    const end = arrival + task.service_s;
    const ret = end + travel;
    if (arrival > task.window_end_s) reasons.push('TIME_WINDOW_UNREACHABLE');
    if (ret - depart > vehicle.trip_limit_s) reasons.push('RETURN_BUDGET_EXCEEDED');
    if (ret > vehicle.shift_end_s) reasons.push('SHIFT_LIMIT_EXCEEDED');
    Object.assign(evidence, { checked_arrival_s: arrival, window_end_s: task.window_end_s, trip_duration_s: ret - depart, trip_limit_s: vehicle.trip_limit_s, checked_return_s: ret, shift_end_s: vehicle.shift_end_s });
    assignment = { task_id: task.id, vehicle_id: vehicle.id, trip_id: `${vehicle.id}/Trip${tripNumber}`, depart_s: depart, travel_s: travel, arrival_s: arrival, service_start_s: arrival, service_end_s: end, return_s: ret, trip_duration_s: ret - depart, distance_m: distance * 2, load_kg: task.load_kg, window_check: 'Within window', payload_check: true, trip_check: true, shift_check: true };
  }
  return { assignment, reasons, evidence };
}

// New deterministic demo planner: earliest deadline first, earliest feasible arrival.
// This is not the unavailable 2025 heuristic/GA implementation.
export function generateCandidate(input, checkpoint = {}) {
  const errors = validateInput(input);
  if (errors.length) throw new Error(errors.map(x => x.message).join(' '));
  const delivered = new Set(checkpoint.delivered_ids || []);
  const ready = new Map(input.vehicles.map(v => [v.id, Math.max(checkpoint.clock_s || 0, checkpoint.ready_s?.[v.id] || 0)]));
  const trips = new Map(input.vehicles.map(v => [v.id, 0]));
  const assignments = [], unassigned = [];
  for (const task of input.tasks.filter(t => !delivered.has(t.id)).sort((a,b) => a.window_end_s - b.window_end_s || a.id.localeCompare(b.id))) {
    const checked = input.vehicles.map(v => checkCandidate(input, task, v, ready.get(v.id), trips.get(v.id) + 1));
    const feasible = checked.filter(c => c.assignment && !c.reasons.length).sort((a,b) => a.assignment.arrival_s - b.assignment.arrival_s || a.assignment.return_s - b.assignment.return_s || a.assignment.vehicle_id.localeCompare(b.assignment.vehicle_id));
    if (feasible.length) {
      const a = feasible[0].assignment, v = input.vehicles.find(v => v.id === a.vehicle_id);
      assignments.push(a); ready.set(v.id, a.return_s + v.turnaround_s); trips.set(v.id, trips.get(v.id) + 1);
    } else {
      const eligible = checked.filter(c => c.evidence.eligible && c.evidence.available);
      const carry = eligible.filter(c => c.evidence.load_kg <= c.evidence.capacity_kg);
      let codes = !eligible.length ? ['NO_AVAILABLE_VEHICLE'] : !carry.length ? ['PAYLOAD_EXCEEDED'] : [...new Set(carry.flatMap(c => c.reasons))];
      const order = Object.keys(REASONS); codes.sort((a,b) => order.indexOf(a) - order.indexOf(b));
      if (!codes.length) codes = ['SEARCH_NO_ASSIGNMENT'];
      unassigned.push({ task_id: task.id, reason_codes: codes, explanation: REASONS[codes[0]][0], next_actions: codes.map(c => REASONS[c][1]), evidence: checked.map(c => ({ ...c.evidence, reason_codes: c.reasons })) });
    }
  }
  const candidate = { assignments, unassigned, coverage: assignments.length ? (unassigned.length ? 'Partial' : 'Complete') : 'No feasible assignment found', calculation_status: 'Calculated', method: 'demo-edf-earliest-arrival', rule_profile_id: 'demo-v1' };
  candidate.checks = verifyCandidate(input, checkpoint, candidate);
  if (!candidate.checks.ok) throw new Error('Independent validation failed: ' + candidate.checks.errors.join('; '));
  return candidate;
}

// Independent reconstruction from inputs; no reliance on planner check booleans.
export function verifyCandidate(input, checkpoint, candidate) {
  const errors = [], delivered = new Set(checkpoint.delivered_ids || []), seen = new Set();
  if (!candidate || !Array.isArray(candidate.assignments) || !Array.isArray(candidate.unassigned)) return { ok: false, errors: ['Missing assignment or unassigned arrays.'], checked_tasks: 0, validator: 'independent-demo-v1' };
  const pending = input.tasks.filter(t => !delivered.has(t.id));
  const ready = new Map(input.vehicles.map(v => [v.id, Math.max(checkpoint.clock_s || 0, checkpoint.ready_s?.[v.id] || 0)]));
  const tripCounts = new Map(input.vehicles.map(v => [v.id, 0]));
  for (const a of [...candidate.assignments].sort((a,b) => a.depart_s - b.depart_s)) {
    const t = pending.find(t => t.id === a.task_id), v = input.vehicles.find(v => v.id === a.vehicle_id);
    if (!t || !v || seen.has(a.task_id)) { errors.push('Unknown, duplicate or delivered task.'); continue; }
    seen.add(a.task_id);
    const tripNumber = tripCounts.get(v.id) + 1; tripCounts.set(v.id, tripNumber);
    if (a.trip_id !== `${v.id}/Trip${tripNumber}` || a.window_check !== 'Within window' || a.payload_check !== true || a.trip_check !== true || a.shift_check !== true) errors.push(`${t.id}: missing or inconsistent assignment check fields.`);
    const d = input.distances_m[v.type]?.[t.station];
    const travel = Number.isFinite(d) ? Math.ceil(d / v.speed_m_s) : NaN;
    const dep = Math.max(ready.get(v.id), t.window_start_s - travel), arr = dep + travel, end = arr + t.service_s, ret = end + travel;
    if (!v.available || !t.eligible_types.includes(v.type) || t.load_kg > v.capacity_kg || !Number.isFinite(travel) || arr > t.window_end_s || ret - dep > v.trip_limit_s || ret > v.shift_end_s) errors.push(`${t.id}: resource or time constraint failed.`);
    for (const [f, value] of Object.entries({ depart_s: dep, travel_s: travel, arrival_s: arr, service_start_s: arr, service_end_s: end, return_s: ret, trip_duration_s: ret - dep, distance_m: d * 2, load_kg: t.load_kg })) if (a[f] !== value) errors.push(`${t.id}: ${f} does not match independent calculation.`);
    ready.set(v.id, ret + v.turnaround_s);
  }
  for (const u of candidate.unassigned) {
    if (!pending.some(t => t.id === u.task_id) || seen.has(u.task_id) || !Array.isArray(u.reason_codes) || !u.reason_codes.length || u.reason_codes.some(c => !Object.hasOwn(REASONS,c)) || !Array.isArray(u.evidence) || typeof u.explanation !== 'string' || !Array.isArray(u.next_actions)) errors.push('Invalid unassigned task record.');
    seen.add(u.task_id);
  }
  if (pending.some(t => !seen.has(t.id))) errors.push('Task missing from plan.');
  return { ok: errors.length === 0, errors, checked_tasks: pending.length, validator: 'independent-demo-v1' };
}
