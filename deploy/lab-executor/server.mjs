#!/usr/bin/env bash
// Lab executor stub — receives approved action payloads from the gateway
// outbox worker (POST /execute) and records them. Replace with the real
// restricted executor in field deployments. Never executes anything itself.
import http from 'node:http';
import { createHash } from 'node:crypto';

const PORT = Number(process.env.EXECUTOR_PORT ?? 8082);
const TOKEN = process.env.EXECUTOR_TOKEN ?? '';
const seen = new Map(); // action fingerprint -> receipt

const server = http.createServer((req, res) => {
  if (req.url === '/healthz') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, receipts: seen.size }));
    return;
  }
  if (req.url !== '/execute' || req.method !== 'POST') {
    res.writeHead(404);
    res.end();
    return;
  }
  if (TOKEN && req.headers.authorization !== `Bearer ${TOKEN}`) {
    res.writeHead(401);
    res.end(JSON.stringify({ error: 'unauthorized' }));
    return;
  }
  let body = '';
  req.on('data', (c) => (body += c));
  req.on('end', () => {
    let parsed;
    try {
      parsed = JSON.parse(body);
    } catch {
      res.writeHead(400);
      res.end(JSON.stringify({ error: 'invalid json' }));
      return;
    }
    const fp = createHash('sha256').update(body).digest('hex').slice(0, 16);
    const dup = seen.has(fp);
    if (!dup) {
      seen.set(fp, { at: new Date().toISOString(), bytes: body.length });
      console.log(`[executor] recorded action fp=${fp} bytes=${body.length}`);
    }
    res.writeHead(dup ? 200 : 202, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ accepted: true, duplicate: dup, fingerprint: fp }));
  });
});

server.listen(PORT, () => console.log(`lab-executor on :${PORT}`));
