import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const api = path.join(root, 'apps/api');
const python = path.join(
  api,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
if (!existsSync(python)) {
  console.error('Backend environment is missing. Run pnpm setup:python first.');
  process.exit(1);
}
const tasks = {
  dev: [
    '-m',
    'uvicorn',
    'customer_intelligence.main:app',
    '--reload',
    '--host',
    '127.0.0.1',
    '--port',
    '8000',
  ],
  lint: ['-m', 'ruff', 'check', 'src'],
  format: ['-m', 'ruff', 'format', 'src'],
  'check-types': ['-m', 'mypy', 'src/customer_intelligence'],
  build: ['-m', 'build', '--outdir', 'dist'],
};
const name = process.argv[2];
if (!tasks[name]) throw new Error(`Unknown Python task: ${name}`);
const child = spawn(python, [...tasks[name], ...process.argv.slice(3)], {
  cwd: api,
  stdio: 'inherit',
  env: process.env,
});
for (const signal of ['SIGINT', 'SIGTERM'])
  process.on(signal, () => child.kill(signal));
child.on('error', (error) => {
  console.error(error.message);
  process.exit(1);
});
child.on('exit', (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0));
});
