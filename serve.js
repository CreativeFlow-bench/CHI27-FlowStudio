#!/usr/bin/env node
const http = require('http');
const fs = require('fs');
const path = require('path');

const DIR = process.argv[2] || __dirname;
const PORT = parseInt(process.argv[3]) || 8765;

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript',
  '.ts': 'application/javascript',
  '.tsx': 'application/javascript',
  '.jsx': 'application/javascript',
  '.css': 'text/css',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.json': 'application/json',
  '.glb': 'model/gltf-binary',
  '.gltf': 'model/gltf+json',
  '.env': 'text/plain',
  '.txt': 'text/plain',
  '.md': 'text/markdown',
};

const server = http.createServer((req, res) => {
  let urlPath = req.url.split('?')[0];
  if (urlPath === '/') urlPath = '/index.html';
  const filePath = path.join(DIR, urlPath);
  const ext = path.extname(filePath).toLowerCase();
  const contentType = mime[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, {'Content-Type': 'text/plain; charset=utf-8'});
      res.end(`404 Not Found: ${urlPath}`);
    } else {
      res.writeHead(200, {'Content-Type': contentType});
      res.end(data);
    }
  });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`FlowStudio Static Server`);
  console.log(`  Root: ${DIR}`);
  console.log(`  URL:  http://127.0.0.1:${PORT}`);
  console.log(`  Press Ctrl+C to stop`);
});

// Keep alive
server._keepAlive = setInterval(() => {}, 30000);
process.on('SIGTERM', () => { clearInterval(server._keepAlive); server.close(); process.exit(0); });
process.on('SIGINT',  () => { clearInterval(server._keepAlive); server.close(); process.exit(0); });
