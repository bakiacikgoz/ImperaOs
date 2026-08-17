import fs from 'node:fs';
import path from 'node:path';

const dist = path.resolve(process.cwd(), 'dist');
const assets = path.join(dist, 'assets');
const names = fs.readdirSync(assets);
const codeChunks = names.filter((name) => /^CodeArtifactEditor-.*\.js$/.test(name));
if (codeChunks.length !== 1) throw new Error(`Expected one lazy code editor chunk, found ${codeChunks.length}.`);

const html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8');
if (html.includes(codeChunks[0])) throw new Error('Code editor chunk is eagerly linked from index.html.');

for (const worker of ['editor', 'json', 'css', 'html', 'ts']) {
  if (!names.some((name) => new RegExp(`^${worker}\\.worker-.*\\.js$`).test(name))) {
    throw new Error(`Missing local Monaco ${worker} worker asset.`);
  }
}

const forbiddenLanguages = [
  'abap', 'apex', 'clojure', 'dart', 'elixir', 'fsharp', 'graphql', 'julia', 'kotlin',
  'lua', 'mysql', 'pascal', 'perl', 'php', 'ruby', 'scala', 'solidity', 'swift', 'vb', 'wgsl',
];
for (const language of forbiddenLanguages) {
  if (names.some((name) => new RegExp(`^${language}-.*\\.js$`).test(name))) {
    throw new Error(`Unsupported Monaco language chunk was emitted: ${language}.`);
  }
}

for (const name of names.filter((candidate) => candidate.endsWith('.js'))) {
  const source = fs.readFileSync(path.join(assets, name), 'utf8');
  // Monaco's TypeScript worker embeds lib.es5.d.ts as data, which contains the
  // declaration text below. It is not executable JavaScript.
  const executableSource = source.replaceAll('declare function eval(x: string): any;', '');
  if (/\b(?:eval|Function)\s*\(/.test(executableSource)) {
    throw new Error(`CSP-unsafe dynamic code construction found in ${name}.`);
  }
}

process.stdout.write(JSON.stringify({
  codeChunk: codeChunks[0],
  codeChunkBytes: fs.statSync(path.join(assets, codeChunks[0])).size,
  localWorkers: ['editor', 'json', 'css', 'html', 'ts'],
  eager: false,
  unsafeEval: false,
}) + '\n');
