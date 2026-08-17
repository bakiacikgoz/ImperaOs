import fs from 'node:fs';
import path from 'node:path';

const dist = path.resolve(process.cwd(), 'dist');
const assets = path.join(dist, 'assets');
const names = fs.readdirSync(assets);
const flowChunks = names.filter((name) => /^FlowArtifactEditor-.*\.js$/.test(name));
const flowStyles = names.filter((name) => /^FlowArtifactEditor-.*\.css$/.test(name));
if (flowChunks.length !== 1) throw new Error(`Expected one lazy flow editor chunk, found ${flowChunks.length}.`);
if (flowStyles.length !== 1) throw new Error(`Expected one lazy flow editor stylesheet, found ${flowStyles.length}.`);

const html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8');
if (html.includes(flowChunks[0]) || html.includes(flowStyles[0])) {
  throw new Error('Flow editor assets are eagerly linked from index.html.');
}
const entryMatch = html.match(/src="\/assets\/(index-[^"]+\.js)"/);
if (!entryMatch) throw new Error('Production entry chunk was not found.');
const entry = fs.readFileSync(path.join(assets, entryMatch[1]), 'utf8');
if (entry.includes('react-flow__renderer')) throw new Error('React Flow leaked into the eager entry chunk.');

const bytes = fs.statSync(path.join(assets, flowChunks[0])).size;
if (bytes > 500_000) throw new Error(`Lazy flow editor chunk exceeds 500 KiB: ${bytes}.`);
process.stdout.write(JSON.stringify({
  flowChunk: flowChunks[0],
  flowChunkBytes: bytes,
  eager: false,
}) + '\n');
