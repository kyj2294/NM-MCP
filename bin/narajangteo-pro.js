#!/usr/bin/env node
/**
 * npx narajangteo-pro 진입점.
 * uvx가 있으면 uvx로, 없으면 python -m 으로 실행한다.
 */
const { spawn, spawnSync } = require('child_process');

const args = process.argv.slice(2);

function hasCommand(cmd) {
  const result = spawnSync(cmd, ['--version'], { stdio: 'ignore' });
  return result.status === 0;
}

let proc;
if (hasCommand('uvx')) {
  proc = spawn('uvx', ['narajangteo-pro', ...args], { stdio: 'inherit', env: process.env });
} else if (hasCommand('python3')) {
  proc = spawn('python3', ['-m', 'narajangteo_pro', ...args], { stdio: 'inherit', env: process.env });
} else {
  proc = spawn('python', ['-m', 'narajangteo_pro', ...args], { stdio: 'inherit', env: process.env });
}

proc.on('error', (err) => {
  console.error('[narajangteo-pro] 실행 실패:', err.message);
  console.error('uvx 또는 Python이 설치되어 있어야 합니다.');
  process.exit(1);
});

proc.on('exit', (code) => process.exit(code ?? 0));
