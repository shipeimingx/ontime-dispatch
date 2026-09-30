import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
async function boot(dataDir) {
  const child=spawn(process.execPath,['server.mjs'],{cwd:root,env:{...process.env,PORT:'0',ONTIME_DATA_DIR:dataDir},stdio:['ignore','pipe','pipe'],windowsHide:true});
  let output='';
  const url=await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>{child.kill();reject(Error('Server startup timed out.'));},10000);
    child.stdout.on('data',chunk=>{output+=chunk;const m=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(timeout);resolve(m[0]);}});
    child.stderr.on('data',chunk=>{output+=chunk;});
    child.on('error',e=>{clearTimeout(timeout);reject(e);});
    child.on('exit',code=>{clearTimeout(timeout);reject(Error('Server exited '+code+' '+output));});
  });
  return {child,url,stop:()=>new Promise(resolve=>{if(child.exitCode!==null)return resolve();child.once('exit',resolve);child.kill();})};
}

test('HTTP: approval guards, optimistic concurrency, persisted checkpoint and restart resume',async t=>{
  const artifacts=path.join(root,'artifacts');await fs.mkdir(artifacts,{recursive:true});
  const dataDir=await fs.mkdtemp(path.join(artifacts,'api-test-'));
  let server=await boot(dataDir);t.after(async()=>await server.stop());
  let state=await fetch(server.url+'/api/state').then(r=>r.json());
  async function post(action,body={}) {
    const r=await fetch(server.url+'/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:state.state_version,...body})});
    const result=await r.json();if(r.ok)state=result;return {r,result};
  }
  assert.equal((await post('start')).r.status,409);
  assert.equal((await post('plan')).r.status,200);
  assert.equal(state.current_plan.assignments.length,3);
  assert.equal((await post('approve',{plan_id:state.active_plan_id,snapshot_id:state.snapshot_id})).r.status,409);
  assert.equal((await post('approve',{plan_id:state.active_plan_id,snapshot_id:state.snapshot_id,acknowledged_unassigned:['T04']})).r.status,200);
  await post('start');await post('advance',{seconds:180});assert.ok(state.delivered.T01);
  const beforeRestart=structuredClone(state), persisted=JSON.parse(await fs.readFile(path.join(dataDir,'state.json'),'utf8'));assert.deepEqual(persisted.delivered,state.delivered);
  await server.stop();server=await boot(dataDir);state=await fetch(server.url+'/api/state').then(r=>r.json());
  assert.equal(state.run.status,'Paused');assert.deepEqual(state.delivered,beforeRestart.delivered);await post('resume');assert.equal(state.run.status,'Running');
  await post('unavailable',{vehicle_id:'UAV-01'});assert.equal(state.run.status,'Needs replan');assert.equal((await post('start')).r.status,409);
  await post('plan');assert.ok(!state.current_plan.assignments.some(a=>a.task_id==='T01'));
  await post('approve',{plan_id:state.active_plan_id,snapshot_id:state.snapshot_id,acknowledged_unassigned:state.current_plan.unassigned.map(u=>u.task_id)});await post('resume');await post('advance',{seconds:5000});
  assert.equal(state.run.status,'Finished');assert.equal(Object.keys(state.delivered).length,2);
  // Mid-trip rollback at 09:03 delays the AGV: T03 now reaches 09:21, beyond 09:20.
  assert.ok(state.current_plan.unassigned.find(u=>u.task_id==='T03').reason_codes.includes('TIME_WINDOW_UNREACHABLE'));
  assert.match(state.run.result,/2 tasks remain unassigned/);
  const badInput=structuredClone(state.input);badInput.tasks[0].load_kg=-1;assert.equal((await post('input',{input:badInput})).r.status,422);
  const foreign=await fetch(server.url+'/api/pause',{method:'POST',headers:{'Content-Type':'application/json',Origin:'https://foreign.example'},body:'{}'});assert.equal(foreign.status,403);
  const traversal=await fetch(server.url+'/%2e%2e%2fpackage.json');assert.equal(traversal.status,403);
  const version=state.state_version,body=JSON.stringify({expected_version:version,scenario:'normal'});
  const results=await Promise.all([1,2].map(()=>fetch(server.url+'/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body})));
  assert.deepEqual(results.map(r=>r.status).sort(),[200,409]);
  const final=await fetch(server.url+'/api/state').then(r=>r.json());assert.equal(final.archives.length,1);assert.equal(final.input.tasks.length,3);
  const exported=await fetch(server.url+'/api/export').then(r=>r.json());assert.equal(exported.label,'Illustrative data · Simulation only');assert.equal(exported.archives.length,1);
});
