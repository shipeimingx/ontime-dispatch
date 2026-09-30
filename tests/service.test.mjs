import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from '../src/fixtures.mjs';
import { generateCandidate, verifyCandidate, validateInput } from '../src/planner.mjs';
import { freshState, plan, approve, start, advance, saveInput, unavailable, snapshot, checkpoint, installCandidate, applyAction } from '../src/service.mjs';

const approveCurrent = s => approve(s,{plan_id:s.active_plan_id,snapshot_id:snapshot(s),acknowledged_unassigned:s.plans.at(-1).unassigned.map(u=>u.task_id)});
const computedTimes = p => p.assignments.map(a=>[a.task_id,a.vehicle_id,a.depart_s,a.arrival_s,a.service_end_s,a.return_s]);

test('A01/A12: fixture arithmetic, inclusive boundaries and complete return',()=>{
  const s=freshState(false),p=plan(s);
  assert.deepEqual(computedTimes(p),[['T01','UAV-01',0,120,180,300],['T02','AGV-01',0,240,360,600],['T03','AGV-01',720,1080,1200,1560]]);
  assert.equal(s.active_approval_id,null);assert.equal(s.run,null);
  approveCurrent(s);assert.equal(s.run,null);start(s);
  advance(s,1200);assert.equal(Object.keys(s.delivered).length,3);assert.equal(s.run.status,'Running');
  advance(s,360);assert.equal(s.run.status,'Finished');assert.equal(s.run.result,'All tasks completed in simulation.');
  const input=fixture(false);input.tasks=[{...input.tasks[0],window_start_s:120,window_end_s:120}];
  const edge=generateCandidate(input);assert.equal(edge.assignments[0].arrival_s,120);assert.equal(edge.assignments[0].service_end_s,180);
});
test('A02/A11: partial approval requires acknowledgement; unassigned never becomes delivered',()=>{
  const s=freshState(),p=plan(s);assert.equal(p.coverage,'Partial');assert.equal(p.unassigned[0].task_id,'T04');assert.deepEqual(p.unassigned[0].reason_codes,['PAYLOAD_EXCEEDED']);assert.equal(p.unassigned[0].arrival_s,undefined);
  assert.throws(()=>approve(s,{plan_id:p.plan_id,snapshot_id:p.snapshot_id}),/Acknowledge/);
  approveCurrent(s);start(s);advance(s,2000);
  assert.equal(s.run.result,'Assigned tasks completed; 1 task remains unassigned.');assert.equal(s.delivered.T04,undefined);assert.equal(s.task_states.T04,'Unassigned');
});
test('A03: saved input invalidates approval and stale starts are rejected',()=>{
  const s=freshState(false);plan(s);approveCurrent(s);const a=s.approvals.at(-1);
  const equivalent=structuredClone(s.input);equivalent.tasks[0]=Object.fromEntries(Object.entries(equivalent.tasks[0]).reverse());saveInput(s,equivalent);assert.equal(s.input_revision,1);assert.equal(a.status,'Approved');
  const input=structuredClone(s.input);input.tasks[0].window_end_s=350;saveInput(s,input);
  assert.equal(s.input_revision,2);assert.equal(a.status,'Invalidated');assert.equal(s.active_approval_id,null);assert.equal(s.plans[0].status,'Stale');assert.throws(()=>start(s),/Approval/);
});
test('A04: delayed results remain history when snapshot changes',()=>{
  const s=freshState(false),snap=snapshot(s),input=structuredClone(s.input),cp=checkpoint(s),candidate=generateCandidate(input,cp);
  const changed=structuredClone(input);changed.tasks[0].load_kg=1.2;saveInput(s,changed);
  const result=installCandidate(s,candidate,snap,input,cp);assert.equal(result.status,'Stale');assert.equal(s.active_plan_id,null);assert.equal(s.active_approval_id,null);
});
test('A05: unavailable UAV preserves T01, recalculates ETA, requires new approval',()=>{
  const s=freshState();plan(s);approveCurrent(s);start(s);unavailable(s,'UAV-01');
  assert.equal(s.run.status,'Needs replan');assert.equal(s.clock_s,0);assert.throws(()=>start(s),/Approval/);
  const p=plan(s);assert.deepEqual(p.assignments.map(a=>a.task_id),['T02','T03']);
  const u=p.unassigned.find(u=>u.task_id==='T01');assert.equal(u.reason_codes[0],'TIME_WINDOW_UNREACHABLE');assert.equal(u.evidence.find(e=>e.vehicle_id==='AGV-01').checked_arrival_s,360);assert.equal(u.arrival_s,undefined);
  assert.throws(()=>start(s),/Approval/);approveCurrent(s);start(s);advance(s,2000);assert.equal(Object.keys(s.delivered).length,2);
});
test('A06: shrinking T02 arrival window to 09:03 rejects old 09:04 ETA',()=>{
  const s=freshState();plan(s);approveCurrent(s);const input=structuredClone(s.input);input.tasks[1].window_end_s=180;saveInput(s,input);const p=plan(s);
  assert.ok(p.unassigned.find(u=>u.task_id==='T02').reason_codes.includes('TIME_WINDOW_UNREACHABLE'));assert.ok(!p.assignments.some(a=>a.task_id==='T02'));
});
test('A07: all unavailable or all overloaded terminate with visible reasons and no approval',()=>{
  for(const mode of ['unavailable','overload']){const s=freshState();if(mode==='unavailable')s.input.vehicles.forEach(v=>v.available=false);else s.input.tasks.forEach(t=>t.load_kg=100);
    const p=plan(s);assert.equal(p.assignments.length,0);assert.equal(p.unassigned.length,4);assert.throws(()=>approveCurrent(s),/No assigned/);
  }
});
test('A08: invalid candidate cannot be installed or approved',()=>{
  const s=freshState(false),cp=checkpoint(s),p=generateCandidate(s.input,cp);p.assignments[0].return_s=0;
  assert.equal(verifyCandidate(s.input,cp,p).ok,false);assert.throws(()=>installCandidate(s,p,snapshot(s),s.input,cp),/Calculation failed/);assert.equal(s.plans.length,0);
  assert.equal(verifyCandidate(s.input,cp,{assignments:[]}).ok,false);
  const missing=generateCandidate(s.input,cp);delete missing.assignments[0].trip_id;assert.equal(verifyCandidate(s.input,cp,missing).ok,false);
  plan(s);approveCurrent(s);plan(s,()=>{throw new Error('Adapter did not return mandatory fields.');});
  assert.equal(s.planning_failure.code,'CALCULATION_ERROR');assert.equal(s.active_approval_id,null);assert.throws(()=>start(s),/Approval/);
});
test('A09: ordinary pause/resume preserves authorization after runtime events',()=>{
  const s=freshState(false);plan(s);approveCurrent(s);start(s);advance(s,120);const approvalID=s.active_approval_id;
  applyAction(s,'pause');assert.equal(s.run.status,'Paused');assert.equal(s.active_approval_id,approvalID);applyAction(s,'resume');assert.equal(s.run.status,'Running');advance(s,2000);assert.equal(s.run.status,'Finished');
});
test('A10: delivered history survives mid-trip rollback and is never redispatched',()=>{
  const s=freshState(false);plan(s);approveCurrent(s);start(s);advance(s,180);const history=structuredClone(s.delivered.T01);unavailable(s,'UAV-01');
  assert.equal(s.clock_s,180);assert.equal(s.exceptions.at(-1).rollback,true);assert.equal(s.task_states.T02,'Interrupted');
  const p=plan(s);assert.ok(!p.assignments.some(a=>a.task_id==='T01'));assert.ok(p.assignments.every(a=>a.depart_s>=180));
  const changed=structuredClone(s.input);changed.tasks[0].load_kg=1.1;assert.throws(()=>saveInput(s,changed),/locked/);
  approveCurrent(s);start(s);advance(s,2000);assert.deepEqual(s.delivered.T01,history);assert.equal(s.events.filter(e=>e.task_id==='T01'&&e.event_type==='service_completed').length,1);
});
test('payload, return budget, shift and routes are independently enforced',()=>{
  const input=fixture(false);input.tasks=[input.tasks[0]];input.vehicles=[input.vehicles[0]];
  input.vehicles[0].trip_limit_s=299;assert.equal(generateCandidate(input).unassigned[0].reason_codes[0],'RETURN_BUDGET_EXCEEDED');
  input.vehicles[0].trip_limit_s=600;input.vehicles[0].shift_end_s=299;assert.ok(generateCandidate(input).unassigned[0].reason_codes.includes('SHIFT_LIMIT_EXCEEDED'));
  input.distances_m.UAV.A=null;assert.ok(generateCandidate(input).unassigned[0].reason_codes.includes('NO_ROUTE'));
  input.tasks[0].load_kg=-1;assert.ok(validateInput(input).some(e=>e.field.endsWith('load_kg')));
});
test('early arrival is delayed at depot, serial turnaround accumulates, empty tasks terminate',()=>{
  const input=fixture(false);input.tasks=[{...input.tasks[0],window_start_s:600,window_end_s:800}];const p=generateCandidate(input);assert.equal(p.assignments[0].arrival_s,600);assert.equal(p.assignments[0].depart_s,480);
  const normal=generateCandidate(fixture(false));assert.equal(normal.assignments[2].depart_s,normal.assignments[1].return_s+120);
  input.tasks=[];assert.equal(generateCandidate(input).assignments.length,0);
});
test('approve/start repeated actions are idempotent; reset archives without losing audit',()=>{
  const s=freshState(false);plan(s);approveCurrent(s);approveCurrent(s);assert.equal(s.approvals.length,1);start(s);const runID=s.run.run_id;start(s);assert.equal(s.run.run_id,runID);assert.equal(s.events.filter(e=>e.event_type==='started').length,1);
  advance(s,2000);const eventCount=s.events.length;applyAction(s,'reset',{scenario:'partial'});assert.equal(s.archives.length,1);assert.equal(s.archives[0].events.length,eventCount);assert.equal(s.input.tasks.length,4);assert.equal(s.clock_s,0);
});
