import { spawnSync } from 'child_process';
import { Address, Cell, contractAddress, StateInit } from '@ton/core';
import { mkdtempSync, copyFileSync, readFileSync, existsSync, rmSync } from 'fs';
import * as path from 'path';
import { tmpdir } from 'os';

jest.setTimeout(600_000); // GPU compilation/execution can be slow on CI boxes

type Flags = 'default' | 'nb' | 'testnet' | 'both';

type Scenario = {
    name: string;
    start?: string;
    end?: string;
    flags: Flags;
    caseSensitive: boolean;
    masterchain: boolean;
};

const OWNER = 'EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c';
const FLAG_SETS: Flags[] = ['default', 'nb', 'testnet', 'both'];
const MASTERCHAIN_VARIANTS = [false, true];
type PythonCmd = { exe: string; args: string[] };

const resolvePython = (): PythonCmd => {
    const candidates =
        process.platform === 'win32'
            ? ['py', 'py -3', 'python3', 'python']
            : ['python3', 'python'];
    for (const cmd of candidates) {
        const [exe, ...args] = cmd.split(' ');
        try {
            const res = spawnSync(exe, [...args, '-c', 'print("ok")'], { encoding: 'utf8' });
            if (!res.error && res.status === 0 && res.stdout.trim() === 'ok') {
                return { exe, args };
            }
        } catch {
            /* ignore */
        }
    }
    throw new Error('No usable python interpreter found (tried py, py -3, python3, python)');
};

const PYTHON = resolvePython();

function gpuAvailable(): boolean {
    const probe = `
try:
    import pyopencl as cl
    devs = []
    for p in cl.get_platforms():
        try:
            devs.extend(p.get_devices())
        except Exception:
            pass
    print("1" if devs else "0")
except Exception:
    print("0")
`;
    const res = spawnSync(PYTHON.exe, [...PYTHON.args, '-c', probe], { cwd: 'src', encoding: 'utf8' });
    return res.status === 0 && res.stdout.trim() === '1';
}

type PyInfo = { start_digit_base: number };

function getStartInfo(s: Scenario): PyInfo {
    if (!s.start) return { start_digit_base: 3 }; // default friendly addr offset

    const nonBounce = ['nb', 'both'].includes(s.flags);
    const testnet = ['testnet', 'both'].includes(s.flags);
    const caseSensitive = s.caseSensitive;

    const owner = OWNER;
    const script = `
import base64, json, sys, types
sys.modules['pyopencl'] = types.SimpleNamespace()
from generator import CliConfig, build_kernel_config
owner = "${owner}"
owner_raw = base64.urlsafe_b64decode(owner + "==")
cli = CliConfig(
    owner=owner,
    start=${JSON.stringify(s.start)},
    end=${s.end !== undefined ? JSON.stringify(s.end) : 'None'},
    masterchain=${s.masterchain ? 'True' : 'False'},
    non_bounceable=${nonBounce ? 'True' : 'False'},
    testnet=${testnet ? 'True' : 'False'},
    case_sensitive=${caseSensitive ? 'True' : 'False'},
    only_one=True,
)
cfg, sdb = build_kernel_config(cli, owner_raw)
print(json.dumps({"start_digit_base": sdb}))
`;

    const res = spawnSync(PYTHON.exe, [...PYTHON.args, '-c', script], { cwd: 'src', encoding: 'utf8' });
    if (res.status !== 0) {
        throw new Error(res.stderr || res.stdout || `python exited ${res.status}`);
    }
    return JSON.parse(res.stdout.trim()) as PyInfo;
}

function runGeneratorGpu(s: Scenario) {
    const tmp = mkdtempSync(path.join(tmpdir(), 'vanity-gpu-'));
    const genPath = path.join(tmp, 'generator.py');
    const kernelPath = path.join(tmp, 'kernel.cl');
    copyFileSync(path.resolve('src/generator.py'), genPath);
    copyFileSync(path.resolve('src/kernel.cl'), kernelPath);

    const args = [genPath, '--owner', OWNER, '--only-one'];
    if (s.start) args.push('--start', s.start);
    if (s.end) args.push('--end', s.end);
    if (s.caseSensitive) args.push('--case-sensitive');
    if (['nb', 'both'].includes(s.flags)) args.push('-n');
    if (['testnet', 'both'].includes(s.flags)) args.push('-t');
    if (s.masterchain) args.push('--masterchain');

    const res = spawnSync(PYTHON.exe, [...PYTHON.args, ...args], { cwd: tmp, encoding: 'utf8', timeout: 240_000 });
    try {
        if (res.status !== 0) {
            throw new Error(res.stderr || res.stdout || `generator.py failed (${res.status})`);
        }

        const foundFile = path.join(tmp, 'addresses.jsonl');
        if (!existsSync(foundFile)) throw new Error('addresses.jsonl not created');
        const last = readFileSync(foundFile, 'utf8').trim().split(/\r?\n/).filter(Boolean).pop();
        if (!last) throw new Error('addresses.jsonl empty');
        return JSON.parse(last);
    } finally {
        try {
            rmSync(tmp, { recursive: true, force: true });
        } catch {
            /* ignore cleanup errors */
        }
    }
}

function startPattern(len: number, ci: boolean): string {
    const letters = ci ? 'AbCdEfGhIjK' : 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    let out = '';
    while (out.length < len) out += letters;
    return out.slice(0, len);
}

function endPattern(len: number, ci: boolean): string {
    const letters = ci ? 'QrStUvWxYz' : 'zyxwvutsrqponmlkjihgfedcba';
    return letters.slice(0, len);
}

// Matrix: start lengths 1..4, all flag sets, both case modes
const startScenarios: Scenario[] = [];
for (let len = 1; len <= 4; len++) {
    for (const flags of FLAG_SETS) {
        for (const mc of MASTERCHAIN_VARIANTS) {
            startScenarios.push({
                name: `start len ${len} ${flags} cs${mc ? ' mc' : ''}`,
                start: startPattern(len, false),
                flags,
                caseSensitive: true,
                masterchain: mc,
            });
            startScenarios.push({
                name: `start len ${len} ${flags} ci${mc ? ' mc' : ''}`,
                start: startPattern(len, true),
                flags,
                caseSensitive: false,
                masterchain: mc,
            });
        }
    }
}

// Matrix: end lengths 1..2, all flag sets, both case modes
const endScenarios: Scenario[] = [];
for (let len = 1; len <= 2; len++) {
    for (const flags of FLAG_SETS) {
        for (const mc of MASTERCHAIN_VARIANTS) {
            endScenarios.push({
                name: `end len ${len} ${flags} cs${mc ? ' mc' : ''}`,
                end: endPattern(len, false),
                flags,
                caseSensitive: true,
                masterchain: mc,
            });
            endScenarios.push({
                name: `end len ${len} ${flags} ci${mc ? ' mc' : ''}`,
                end: endPattern(len, true),
                flags,
                caseSensitive: false,
                masterchain: mc,
            });
        }
    }
}

// Combined start+end matrix: end fixed at 2 chars, start lengths 1..4
const comboScenarios: Scenario[] = [];
for (let len = 1; len <= 4; len++) {
    for (const flags of FLAG_SETS) {
        for (const mc of MASTERCHAIN_VARIANTS) {
            comboScenarios.push({
                name: `combo len ${len} ${flags} cs${mc ? ' mc' : ''}`,
                start: startPattern(len, false),
                end: endPattern(2, false),
                flags,
                caseSensitive: true,
                masterchain: mc,
            });
            comboScenarios.push({
                name: `combo len ${len} ${flags} ci${mc ? ' mc' : ''}`,
                start: startPattern(len, true),
                end: endPattern(2, true),
                flags,
                caseSensitive: false,
                masterchain: mc,
            });
        }
    }
}

const scenarios: Scenario[] = [...startScenarios, ...endScenarios, ...comboScenarios];

const gpuOk = gpuAvailable();

(gpuOk ? describe : describe.skip)('generator.py GPU matrix', () => {
    const owner = Address.parseFriendly(OWNER).address;

    it.each(scenarios)('$name', (scenario) => {
        const info = getStartInfo(scenario);
        const hit = runGeneratorGpu(scenario);

        const addr = hit.address as string;
        expect(addr).toHaveLength(48);

        const parsed = Address.parseFriendly(addr);
        const expectedWc = scenario.masterchain ? -1 : owner.workChain;
        expect(parsed.address.workChain).toBe(expectedWc);
        const shouldBounce = !['nb', 'both'].includes(scenario.flags);
        expect(parsed.isBounceable).toBe(shouldBounce);
        const shouldTest = ['testnet', 'both'].includes(scenario.flags);
        expect(parsed.isTestOnly).toBe(shouldTest);

        if (scenario.start) {
            const offset = info.start_digit_base;
            const slice = addr.substring(offset, offset + scenario.start.length);
            if (scenario.caseSensitive) {
                expect(slice).toBe(scenario.start);
            } else {
                expect(slice.toLowerCase()).toBe(scenario.start.toLowerCase());
            }
        }

        if (scenario.end) {
            const slice = addr.substring(addr.length - scenario.end.length);
            if (scenario.caseSensitive) {
                expect(slice).toBe(scenario.end);
            } else {
                expect(slice.toLowerCase()).toBe(scenario.end.toLowerCase());
            }
        }

        // Rebuild StateInit and recompute contract address, compare to reported.
        type HitInit = {
            code: string;
            fixedPrefixLength?: number;
            special?: { tick: boolean; tock: boolean } | null;
        };
        type HitConfig = {
            bounceable?: boolean;
            testnet?: boolean;
            workchain?: number;
        };

        const init = hit.init as HitInit;
        const cfg = hit.config as HitConfig;
        const codeCell = Cell.fromBase64(init.code);

        const stateInit: StateInit & { special?: { tick: boolean; tock: boolean } } = {
            code: codeCell,
        };
        if (init.fixedPrefixLength && init.fixedPrefixLength > 0) {
            stateInit.splitDepth = init.fixedPrefixLength;
        }
        if (init.special) {
            stateInit.special = {
                tick: !!init.special.tick,
                tock: !!init.special.tock,
            };
        }

        const ca = contractAddress(cfg?.workchain ?? parsed.address.workChain, stateInit);

        // Apply the free-bit rewrite on the first fixedPrefixLength bits (if any) to mirror generator behavior.
        const rewriteBits = (src: Buffer, ref: Buffer, bits: number) => {
            const out = Buffer.from(src);
            for (let i = 0; i < bits; i++) {
                const byte = i >> 3;
                const bitInByte = 7 - (i & 7);
                const mask = 1 << bitInByte;
                const bit = ref[byte] & mask ? mask : 0;
                out[byte] = (out[byte] & ~mask) | bit;
            }
            return out;
        };

        let rewrittenHash = Buffer.from(ca.hash);
        const fplBits = (init.fixedPrefixLength ?? 0) as number;
        if (fplBits > 0) {
            rewrittenHash = rewriteBits(rewrittenHash, parsed.address.hash, fplBits);
        }

        const caRewritten = new Address(ca.workChain, rewrittenHash);

        const rendered = caRewritten.toString({
            urlSafe: true,
            bounceable: cfg?.bounceable ?? parsed.isBounceable,
            testOnly: cfg?.testnet ?? parsed.isTestOnly,
        });

        expect(rendered).toBe(addr);
    });
});
