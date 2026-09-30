import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { freshState, viewState, applyAction, ServiceError } from './src/service.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
const dataDir = process.env.ONTIME_DATA_DIR || path.join(root, 'data');
await fs.mkdir(dataDir, { recursive: true });
const statePath = path.join(dataDir, 'state.json');
let state;
try { state = JSON.parse(await fs.readFile(statePath,'utf8')); }
catch (e) { if (e.code !== 'ENOENT') throw e; state = freshState(); }
// A process restart retains the checkpoint and requires an explicit resume.
if (state.run?.status === 'Running') state.run.status = 'Paused';
let queue = Promise.resolve();
async function persist(value) {
  const temp = statePath + '.tmp';
  await fs.writeFile(temp, JSON.stringify(value,null,2));
  await fs.rename(temp, statePath);
}
await persist(state);
const types = { '.html':'text/html; charset=utf-8', '.css':'text/css; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.svg':'image/svg+xml', '.json':'application/json' };
const server = http.createServer(async(req,res) => {
  const send = (code, data) => { res.writeHead(code, { 'Content-Type':'application/json; charset=utf-8', 'Cache-Control':'no-store' }); res.end(JSON.stringify(data)); };
  try {
    const url = new URL(req.url,'http://localhost');
    if (url.pathname === '/api/health') return send(200,{ status:'ok', profile:'demo-v1', simulation_only:true });
    if (req.method === 'GET' && url.pathname === '/api/state') return send(200,viewState(state));
    if (req.method === 'GET' && url.pathname === '/api/export') {
      res.setHeader('Content-Disposition','attachment; filename="ontime-dispatch-audit.json"');
      return send(200,{ exported_at:new Date().toISOString(), label:'Illustrative data · Simulation only', ...viewState(state) });
    }
    if (req.method === 'POST' && url.pathname.startsWith('/api/')) {
      const origin = req.headers.origin;
      if (origin && origin !== `http://${req.headers.host}`) throw new ServiceError('Cross-origin mutations are not allowed.',403);
      if (!req.headers['content-type']?.startsWith('application/json')) throw new ServiceError('Use application/json.',415);
      let raw = '';
      for await (const chunk of req) { raw += chunk; if (raw.length > 1_000_000) throw new ServiceError('Input is too large.',413); }
      let body; try { body = JSON.parse(raw || '{}'); } catch { throw new ServiceError('Invalid JSON.',400); }
      const execute = async () => {
        if (body.expected_version !== state.state_version) throw new ServiceError('State changed in another action. Refresh and review before retrying.');
        const next = structuredClone(state);
        applyAction(next, url.pathname.slice(5), body);
        await persist(next); state = next;
        return viewState(state);
      };
      const result = queue.then(execute); queue = result.catch(() => {});
      return send(200, await result);
    }
    if (req.method !== 'GET') return send(405,{ error:'Method not allowed.' });
    const asset = url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname).slice(1);
    const absolute = path.resolve(root,'public',asset), publicRoot = path.join(root,'public') + path.sep;
    if (!absolute.startsWith(publicRoot)) return send(403,{ error:'Forbidden.' });
    const bytes = await fs.readFile(absolute);
    res.writeHead(200,{ 'Content-Type':types[path.extname(absolute)] || 'application/octet-stream', 'Cache-Control':'no-cache', 'X-Content-Type-Options':'nosniff', 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'" }); res.end(bytes);
  } catch(e) { send(e.status || (e.code === 'ENOENT' ? 404 : 500),{ error:e.status ? e.message : (e.code === 'ENOENT' ? 'Not found.' : 'Service operation failed.'), details:e.details || [] }); if (!e.status && e.code !== 'ENOENT') console.error(e); }
});
server.listen(Number(process.env.PORT || 4317),'127.0.0.1',() => console.log(`OnTime Dispatch running at http://127.0.0.1:${server.address().port}`));
