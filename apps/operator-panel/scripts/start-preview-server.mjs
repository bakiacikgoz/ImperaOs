import { spawn } from 'node:child_process';
import path from 'node:path';

function run(args) {
  const command = process.platform === 'win32' ? process.execPath : 'corepack';
  const commandArgs = process.platform === 'win32'
    ? [path.join(path.dirname(process.execPath), 'node_modules', 'corepack', 'dist', 'corepack.js'), 'pnpm', ...args]
    : ['pnpm', ...args];
  return spawn(command, commandArgs, {
    env: {
      ...process.env,
      VITE_OPERATOR_PANEL_PREVIEW: '1',
    },
    shell: false,
    stdio: 'inherit',
  });
}

// A committed Vite mode keeps browser-preview authority deterministic. Process
// environment alone is not enough when a package-manager child rebuilds the app.
const build = run(['build', '--', '--mode', 'e2e']);

build.on('exit', (buildCode, buildSignal) => {
  if (buildSignal) {
    process.kill(process.pid, buildSignal);
    return;
  }
  if (buildCode !== 0) {
    process.exit(buildCode ?? 1);
    return;
  }

  const child = run(['preview', '--host', '127.0.0.1', '--port', '5173']);
  child.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 0);
  });
});
