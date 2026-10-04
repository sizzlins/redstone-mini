/* cmc cross-check harness: banked build (JSON from cmc_dump.py) ->
independent second-engine verdict. NOT a replacement for game paste
(cmc is itself a model); sim-green + cmc-green from two independent
implementations >> sim-green alone. Disagreements pinpoint exactly
where to game-test.

Usage: node scratch/cmc_harness.mjs <build.json> [--ticks N] [--vectors a,b,..]
- fresh World per vector (stateless, matches sim_verify semantics).
- bulk load with updates OFF, support-audit every cell (fail loud on
  pops: the 242-stone class, automated), enqueue all redstone cells,
  settle N ticks, read lamps, compare vs expected.
- exit 0 all-green, 1 any mismatch. JSON summary on stdout.
*/
import { readFileSync } from 'node:fs';
import { World } from '../../put gitrepos here/cmc/src/core/world/world.js';
import { installSystems } from '../../put gitrepos here/cmc/src/core/systems.js';
import { BLOCK } from '../../put gitrepos here/cmc/src/core/blocks/blocks.js';
import { checkSupport } from '../../put gitrepos here/cmc/src/core/interact/support.js';
import { lampLit } from '../../put gitrepos here/cmc/src/core/blocks/blocks.js';

const args = process.argv.slice(2);
const doc = JSON.parse(readFileSync(args[0], 'utf8'));
let TICKS = 400;
let only = null;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--ticks') TICKS = parseInt(args[i + 1], 10);
  if (args[i] === '--vectors') only = args[i + 1].split(',').map(Number);
}

// ours-facing (names INPUT side) -> cmc output-dir hfacing idx
const OUTIDX = { north: 2, east: 3, south: 0, west: 1 };
const DIRIDX = { down: 0, up: 1, north: 2, south: 3, west: 4, east: 5 };

function mapBid(bid) {
  const base = bid.split('[')[0];
  const st = bid.includes('[') ? bid.slice(bid.indexOf('[') + 1, -1) : '';
  const kv = {};
  for (const p of st.split(',')) {
    const [k, v] = p.split('=');
    if (k) kv[k.trim()] = (v || '').trim();
  }
  switch (base) {
    case 'minecraft:stone': return [BLOCK.STONE, 0];
    case 'minecraft:cobblestone': return [BLOCK.COBBLESTONE, 0];
    case 'minecraft:glass': return [BLOCK.GLASS, 0];
    case 'minecraft:target':
      // ponytail: cmc has no target block; target is game-proven
      // identical to stone as conductor+support (C3/C4), emission
      // irrelevant (no projectiles). Documented equivalence.
      return [BLOCK.STONE, 0];
    case 'minecraft:redstone_wire': return [BLOCK.REDSTONE_DUST, 0];
    case 'minecraft:repeater': {
      const f = OUTIDX[kv.facing || 'east'];
      const d = Math.max(1, Math.min(4, parseInt(kv.delay || '1', 10))) - 1;
      return [BLOCK.REPEATER, f | (d << 2)];
    }
    case 'minecraft:comparator': {
      const f = OUTIDX[kv.facing || 'east'];
      return [BLOCK.COMPARATOR, f | (kv.mode === 'subtract' ? 4 : 0)];
    }
    case 'minecraft:redstone_torch': // standing torch, attach floor
      return [BLOCK.REDSTONE_TORCH, 0];
    case 'minecraft:redstone_wall_torch': {
      // ponytail: ours facing names the HEAD direction (verified: torch
      // between west cobble + east dust carries facing=east); cmc attach
      // is the DIR toward SUPPORT = opposite. First harness run mapped
      // them equal and popped 11 torches (support audit working as
      // designed -- it caught MY mapping bug, not a build bug).
      const a = { west: 5, east: 4, north: 3, south: 2 }[kv.facing || 'north'];
      return [BLOCK.REDSTONE_TORCH, a];
    }
    case 'minecraft:lever': {
      if (kv.face !== undefined && kv.face !== 'floor')
        throw new Error('wall/ceiling lever not mapped: ' + bid);
      return [BLOCK.LEVER, kv.powered === 'true' ? 8 : 0];
    }
    case 'minecraft:redstone_lamp': return [BLOCK.REDSTONE_LAMP, 0];
    case 'minecraft:stone_slab':
    case 'minecraft:smooth_stone_slab': {
      const top = (kv.type || 'bottom') === 'top';
      return [BLOCK.SLAB, 1 | (top ? 4 : 0)];
    }
    case 'minecraft:cobblestone_slab': {
      const top = (kv.type || 'bottom') === 'top';
      return [BLOCK.SLAB, 3 | (top ? 4 : 0)];
    }
    case 'minecraft:redstone_block': return [BLOCK.REDSTONE_BLOCK, 0];
    default:
      throw new Error('unmapped bid: ' + bid);
  }
}

const OY = 20;
const isComp = (bid) => {
  const b = bid.split('[')[0];
  return b === 'minecraft:redstone_wire' || b === 'minecraft:redstone_torch' ||
    b === 'minecraft:redstone_wall_torch' || b === 'minecraft:repeater' ||
    b === 'minecraft:comparator' || b === 'minecraft:redstone_lamp' ||
    b === 'minecraft:lever';
};

function buildWorld(leverset) {
  const w = new World({ seed: 1 });
  installSystems(w);
  let minx = 1e9, maxx = -1e9, minz = 1e9, maxz = -1e9;
  for (const [x, y, z] of doc.blocks.map((b) => [b[0], b[1], b[2]])) {
    if (x < minx) minx = x;
    if (x > maxx) maxx = x;
    if (z < minz) minz = z;
    if (z > maxz) maxz = z;
  }
  for (let cx = Math.floor((minx - 2) / 16); cx <= Math.floor((maxx + 2) / 16); cx++)
    for (let cz = Math.floor((minz - 2) / 16); cz <= Math.floor((maxz + 2) / 16); cz++)
      w.loadChunk(cx, cz);
  // solids first (support present before components arrive), updates OFF.
  const solids = [], rest = [];
  for (const b of doc.blocks) (isComp(b[3]) ? rest : solids).push(b);
  for (const [x, y, z, bid] of [...solids, ...rest]) {
    const [id, meta] = mapBid(bid);
    let m = meta;
    if (bid.startsWith('minecraft:lever')) {
      // ponytail: pin levers follow the vector; genome (constant) levers
      // keep their bid state. Overwriting constants OFF once silently
      // unpowered every _const_io-style motif (caught on first NOT run).
      const nm = leverset ? leverset[x + ',' + z] : undefined;
      if (nm !== undefined) m = (m & ~8) | (nm.v ? 8 : 0);
    }
    w.setBlock(x, y + OY, z, id, m, 13);
  }
  return w;
}

function audit(w) {
  // explicit support audit (placement used flag 13 = no auto checks):
  // every non-air cell must be allowed to stay. Pops = support bugs.
  let placed = 0, popped = 0;
  const bad = [];
  for (const [x, y, z] of doc.blocks.map((b) => [b[0], b[1], b[2]])) {
    placed++;
    if (!checkSupport(w, x, y + OY, z)) {
      popped++;
      if (bad.length < 10) bad.push([x, y, z]);
    }
  }
  return { placed, popped, bad };
}

function settle(w) {
  for (const [x, y, z, bid] of doc.blocks) {
    if (isComp(bid)) w.enqueueUpdate(x, y + OY, z);
  }
  for (let i = 0; i < TICKS; i++) w.tick();
}

function readLamps(w, lampCells) {
  const out = {};
  for (const [coord, name] of lampCells) {
    const [x, z] = coord.split(',').map(Number);
    // lamp y: find the lamp block at this (x,z) (pins are y=1 in builds)
    let lit = false;
    for (const [bx, by, bz, bid] of doc.blocks) {
      if (bx === x && bz === z && bid.split('[')[0] === 'minecraft:redstone_lamp') {
        lit = !!lampLit(w.getBlockMeta(bx, by + OY, bz));
        break;
      }
    }
    out[name] = lit;
  }
  return out;
}

const lampCells = doc.lamps;
const leverCells = doc.levers;
// audit once on a dedicated world
{
  const wa = buildWorld(null);
  const a = audit(wa);
  if (a.popped > 0) {
    console.log(JSON.stringify({ ok: false, stage: 'support',
      popped: a.popped, examples: a.bad }));
    process.exit(1);
  }
}
const results = [];
let idx = 0;
for (const vec of doc.vectors) {
  if (only && !only.includes(idx)) { idx++; continue; }
  const leverset = {};
  for (const [coord, name] of leverCells) leverset[coord] = { v: !!vec[name] };
  const w = buildWorld(leverset);
  settle(w);
  const got = readLamps(w, lampCells);
  const want = doc.expected[doc.vectors.indexOf(vec)];
  const bad = Object.keys(want).filter((k) => !!got[k] !== !!want[k]);
  results.push({ vec, got, want, ok: bad.length === 0, bad });
  idx++;
}
const fails = results.filter((r) => !r.ok);
console.log(JSON.stringify({ ok: fails.length === 0, n: results.length,
  fails: fails.slice(0, 8), ticks: TICKS,
  sampled: !!doc.sampled }, null, 1));
process.exit(fails.length === 0 ? 0 : 1);
