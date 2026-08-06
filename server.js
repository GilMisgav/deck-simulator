// ════════════════════════════════════════════════════════════════════
// Deck Room server — static files + persistence API (zero dependencies)
//   GET  /api/ping           → {ok, decks, archived}
//   POST /api/delete-decks   {deck_ids:[…]} → removes them from
//        deck_stats.json + data.js, rebuilds decks.sqlite, archives the
//        removed rows to removed_decks.json (nothing is lost)
//   POST /api/restore-all    → merges the archive back and rebuilds
// Run: node server.js   (or double-click start.command)
// ════════════════════════════════════════════════════════════════════
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const {execFile} = require('child_process');

const ROOT = __dirname;
const PORT = 8642;
const STATS = path.join(ROOT, 'deck_stats.json');
const DATAJS = path.join(ROOT, 'data.js');
const ARCHIVE = path.join(ROOT, 'removed_decks.json');
const MIME = {'.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8',
  '.json':'application/json', '.css':'text/css', '.md':'text/plain; charset=utf-8',
  '.sqlite':'application/octet-stream', '.command':'text/plain'};

const readJSON = f => JSON.parse(fs.readFileSync(f, 'utf8'));
const archiveCount = () => {
  try { return readJSON(ARCHIVE).rows.length; } catch { return 0; }
};
function writeData(data){
  fs.writeFileSync(STATS, JSON.stringify(data));
  fs.writeFileSync(DATAJS, 'window.DECK_DATA=' + JSON.stringify(data) + ';');
}
function rebuildSqlite(cb){
  execFile('python3', ['build_sqlite.py'], {cwd: ROOT}, (err, stdout, stderr) => {
    cb(err ? (stderr || String(err)) : null, stdout);
  });
}
function send(res, code, obj){
  res.writeHead(code, {'Content-Type': 'application/json', 'Cache-Control': 'no-store'});
  res.end(JSON.stringify(obj));
}
function body(req, cb){
  let b = '';
  req.on('data', c => { b += c; if (b.length > 50e6) req.destroy(); });
  req.on('end', () => { try { cb(null, JSON.parse(b || '{}')); } catch (e) { cb(e); } });
}

const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0];

  if (url === '/api/ping'){
    let decks = 0;
    try { decks = readJSON(STATS).rows.length; } catch {}
    return send(res, 200, {ok: true, decks, archived: archiveCount()});
  }

  if (req.method === 'POST' && url === '/api/delete-decks'){
    return body(req, (err, payload) => {
      if (err || !Array.isArray(payload.deck_ids))
        return send(res, 400, {ok: false, error: 'expected {deck_ids:[…]}'});
      const ids = new Set(payload.deck_ids.map(String));
      const data = readJSON(STATS);
      const idIdx = data.fields.indexOf('deck_id');
      const removed = data.rows.filter(r => ids.has(String(r[idIdx])));
      if (!removed.length) return send(res, 200, {ok: true, deleted: 0, remaining: data.rows.length});
      data.rows = data.rows.filter(r => !ids.has(String(r[idIdx])));
      // archive first, so a crash between writes can never lose decks
      let arch;
      try { arch = readJSON(ARCHIVE); } catch { arch = {fields: data.fields, rows: []}; }
      arch.rows.push(...removed);
      fs.writeFileSync(ARCHIVE, JSON.stringify(arch));
      writeData(data);
      rebuildSqlite(sqlErr => send(res, 200, {ok: true, deleted: removed.length,
        remaining: data.rows.length, archived: arch.rows.length,
        sqlite: sqlErr ? 'rebuild failed: ' + sqlErr : 'rebuilt'}));
    });
  }

  if (req.method === 'POST' && url === '/api/add-decks'){
    return body(req, (err, payload) => {
      if (err || !Array.isArray(payload.decks))
        return send(res, 400, {ok: false, error: 'expected {decks:[…]}'});
      const data = readJSON(STATS);
      const idIdx = data.fields.indexOf('deck_id');
      const have = new Set(data.rows.map(r => String(r[idIdx])));
      let added = 0;
      for (const d of payload.decks){
        if (!d || d.deck_id == null || typeof d.cards !== 'string' || d.cards.length !== 52) continue;
        if (have.has(String(d.deck_id))) continue;
        data.rows.push(data.fields.map(f => d[f] === undefined ? null : d[f]));
        have.add(String(d.deck_id)); added++;
      }
      if (!added) return send(res, 200, {ok: true, added: 0, remaining: data.rows.length});
      writeData(data);
      rebuildSqlite(sqlErr => send(res, 200, {ok: true, added, remaining: data.rows.length,
        sqlite: sqlErr ? 'rebuild failed: ' + sqlErr : 'rebuilt'}));
    });
  }

  if (req.method === 'POST' && url === '/api/restore-all'){
    let arch;
    try { arch = readJSON(ARCHIVE); } catch { arch = null; }
    if (!arch || !arch.rows.length) return send(res, 200, {ok: true, restored: 0});
    const data = readJSON(STATS);
    const idIdx = data.fields.indexOf('deck_id');
    const have = new Set(data.rows.map(r => String(r[idIdx])));
    // pad rows archived under an older schema (fewer columns) with nulls
    const back = arch.rows.filter(r => !have.has(String(r[idIdx])))
      .map(r => r.length < data.fields.length
        ? r.concat(Array(data.fields.length - r.length).fill(null)) : r);
    data.rows.push(...back);
    writeData(data);
    fs.writeFileSync(ARCHIVE, JSON.stringify({fields: data.fields, rows: []}));
    return rebuildSqlite(sqlErr => send(res, 200, {ok: true, restored: back.length,
      remaining: data.rows.length, sqlite: sqlErr ? 'rebuild failed: ' + sqlErr : 'rebuilt'}));
  }

  // ── static files ──
  let file = url === '/' ? '/index.html' : url;
  file = path.normalize(file).replace(/^(\.\.[\/\\])+/, '');
  const full = path.join(ROOT, file);
  if (!full.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
  fs.readFile(full, (err, buf) => {
    if (err){ res.writeHead(404); return res.end('not found'); }
    res.writeHead(200, {'Content-Type': MIME[path.extname(full)] || 'application/octet-stream',
      'Cache-Control': 'no-store'});
    res.end(buf);
  });
});

server.listen(PORT, () => console.log(`Deck Room on http://localhost:${PORT} (persistence API enabled)`));
