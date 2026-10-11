import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const bin = process.platform === 'win32' ? 'Scripts' : 'bin';
const tooling = path.join(root, '.tooling');
const python = path.join(
  tooling,
  bin,
  process.platform === 'win32' ? 'python.exe' : 'python',
);
const uv = path.join(
  tooling,
  bin,
  process.platform === 'win32' ? 'uv.exe' : 'uv',
);
function run(command, args) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
if (!existsSync(python))
  run(process.platform === 'win32' ? 'python' : 'python3', [
    '-m',
    'venv',
    tooling,
  ]);
run(python, ['-m', 'pip', 'install', 'uv==0.13.0']);
run(uv, ['sync', '--project', 'apps/api', '--frozen']);
console.log('Backend dependencies installed in apps/api/.venv.');
