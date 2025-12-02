import { spawn, spawnSync } from 'child_process';
import { mkdtempSync, copyFileSync, readFileSync, existsSync, rmSync, writeFileSync } from 'fs';
import * as path from 'path';
import { tmpdir } from 'os';

jest.setTimeout(600_000); // up to ~10 minutes for all cases

type BenchResult = {
    name: string;
    hits: number;
    seconds: number;
    rate: number;
    timedOut: boolean;
};

type BenchEntry = {
    title: string;
    timestamp: number;
    cases: BenchResult[];
};

type ResultsMap = Record<string, BenchEntry[]>;

const OWNER = 'EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c';
const DEFAULT_DEVICE = 'Unknown device';
const RESULT_FILE = path.resolve(__dirname, 'results.json');

// CLI flags: --add "Title", --replace "Title"
let addTitle: string | null = null;
let replaceTitle: string | null = null;
let benchDevices: string | null = null; // forwarded to generator --devices
(() => {
    const argv = process.argv;
    for (let i = 0; i < argv.length; i++) {
        if (argv[i] === '--add') {
            const val = argv[i + 1];
            addTitle = val && !val.startsWith('-') ? val : '(current)';
            if (val && !val.startsWith('-')) i++;
        }
        if (argv[i] === '--replace') {
            const val = argv[i + 1];
            replaceTitle = val && !val.startsWith('-') ? val : '(current)';
            if (val && !val.startsWith('-')) i++;
        }
        if (argv[i] === '--devices' && i + 1 < argv.length) benchDevices = argv[i + 1];
    }
})();
type BenchCase = {
    name: string;
    start?: string;
    end?: string;
    caseSensitive: boolean;
};

const parseDeviceIds = (raw: string | null): number[] | null => {
    if (!raw) return null;
    const ids = raw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((p) => Number.parseInt(p, 10))
        .filter((n) => !Number.isNaN(n) && n >= 0);
    if (!ids.length) return null;
    return ids;
};

const benchDeviceIds = parseDeviceIds(benchDevices);

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

const detectDevices = (): string[] => {
    const script = `
import pyopencl as cl
names = []
for p in cl.get_platforms():
    for d in p.get_devices():
        names.append(d.name)
for n in names:
    print(n)
`;
    try {
        const res = spawnSync(PYTHON.exe, [...PYTHON.args, '-c', script], { encoding: 'utf8' });
        if (res.status !== 0) return [];
        return res.stdout
            .split(/\\r?\\n/)
            .map((l) => l.trim())
            .filter((l) => l);
    } catch {
        return [];
    }
};

const chooseBenchCases = (names: string[]): BenchCase[] => {
    const defaults: BenchCase[] = [
        { name: 'start 5 cs', start: 'WERTY', caseSensitive: true },
        { name: 'start 5 ci', start: 'WeRtY', caseSensitive: false },
        { name: 'end 4 cs', end: 'WERT', caseSensitive: true },
        { name: 'end 4 ci', end: 'WeRt', caseSensitive: false },
    ];
    const lower = names.join(' ').toLowerCase();
    const isRTX3Plus = /rtx\s*(3|4|5)\d{2,3}/i.test(lower);
    if (!isRTX3Plus) return defaults;
    return [
        { name: 'start 6 cs', start: 'WERTYU', caseSensitive: true },
        { name: 'start 6 ci', start: 'WeRtYu', caseSensitive: false },
        { name: 'end 5 cs', end: 'WERTY', caseSensitive: true },
        { name: 'end 5 ci', end: 'WeRtY', caseSensitive: false },
    ];
};

const normalizeDeviceName = (name: string) =>
    name
        .replace(/[\u0000-\u001f\u007f]/g, '')
        .replace(/\s+/g, ' ')
        .trim();

const detectedDevicesAll = detectDevices().map(normalizeDeviceName).filter(Boolean);
const selectedDevices = benchDeviceIds
    ? benchDeviceIds
          .map((i) => detectedDevicesAll[i])
          .filter((n): n is string => typeof n === 'string' && n.length > 0)
    : detectedDevicesAll;

const benchCases: BenchCase[] = (() => {
    const selected = chooseBenchCases(selectedDevices.length ? selectedDevices : [DEFAULT_DEVICE]);
    if (selected.length) return selected;
    return [
        { name: 'start 5 cs', start: 'WERTY', caseSensitive: true },
        { name: 'start 5 ci', start: 'WeRtY', caseSensitive: false },
        { name: 'end 4 cs', end: 'WERT', caseSensitive: true },
        { name: 'end 4 ci', end: 'WeRt', caseSensitive: false },
    ];
})();
const deviceNames = new Set<string>();

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
    if (res.status === 0 && res.stdout.trim() === '1') return true;
    console.warn('Skipping benchmarks: no GPU detected via pyopencl (python interpreter or OpenCL missing)');
    return false;
}

async function runBenchCase(testCase: BenchCase, timeoutMs: number): Promise<BenchResult> {
    const tmp = mkdtempSync(path.join(tmpdir(), 'vanity-bench-'));
    const genPath = path.join(tmp, 'generator.py');
    const kernelPath = path.join(tmp, 'kernel.cl');
    copyFileSync(path.resolve('src/generator.py'), genPath);
    copyFileSync(path.resolve('src/kernel.cl'), kernelPath);

    const args = [genPath, '--owner', OWNER];
    if (benchDevices) {
        args.push('--devices', benchDevices);
    }
    if (testCase.start) args.push('--start', testCase.start);
    if (testCase.end) args.push('--end', testCase.end);
    if (testCase.caseSensitive) args.push('--case-sensitive');
    // intentionally NOT passing --only-one; we will time-limit instead

    let timedOut = false;
    const child = spawn(PYTHON.exe, [...PYTHON.args, ...args], {
        cwd: tmp,
        stdio: ['ignore', 'pipe', 'pipe'],
    });

    const parseDevices = (chunk: Buffer | string) => {
        const text = chunk.toString();
        for (const line of text.split(/\r?\n/)) {
            const m = line.match(/Using device:\s*(.+)/i);
            if (m && m[1]) {
                const cleaned = normalizeDeviceName(m[1].replace(/^\[\d+\]\s*/, ''));
                deviceNames.add(cleaned || DEFAULT_DEVICE);
            }
        }
    };

    child.stdout?.on('data', parseDevices);
    child.stderr?.on('data', parseDevices);

    const killer = setTimeout(() => {
        timedOut = true;
        child.kill('SIGINT');
        setTimeout(() => child.kill('SIGKILL'), 2000);
    }, timeoutMs);

    await new Promise<void>((resolve) => {
        child.on('close', () => resolve());
        child.on('error', () => resolve());
    });

    clearTimeout(killer);

    let hits = 0;
    let seconds = 0;
    if (existsSync(path.join(tmp, 'addresses.jsonl'))) {
        const lines = readFileSync(path.join(tmp, 'addresses.jsonl'), 'utf8').trim().split(/\r?\n/).filter(Boolean);
        hits = lines.length;
        if (lines.length >= 2) {
            const first = JSON.parse(lines[0]);
            const last = JSON.parse(lines[lines.length - 1]);
            seconds = Math.max(0, last.timestamp - first.timestamp);
        }
    }

    rmSync(tmp, { recursive: true, force: true });

    const rate = seconds > 0 && hits > 1 ? (hits - 1) / seconds : 0;

    return { name: testCase.name, hits, seconds, rate, timedOut };
}

const gpuOk = gpuAvailable();

(gpuOk ? describe : describe.skip)('vanity benchmark (~20s per case)', () => {
    const readResultsMap = (): ResultsMap => {
        if (!existsSync(RESULT_FILE)) {
            return {};
        }

        try {
            const data = JSON.parse(readFileSync(RESULT_FILE, 'utf8'));
            if (data && typeof data === 'object' && !Array.isArray(data)) {
                return data as ResultsMap;
            }
        } catch {
            // fall through
        }
        return {};
    };

    const writeResultsMap = (map: ResultsMap) => {
        writeFileSync(RESULT_FILE, JSON.stringify(map, null, 2));
    };

    const results: BenchResult[] = [];

    const color = {
        green: (s: string) => `\x1b[32m${s}\x1b[0m`,
        red: (s: string) => `\x1b[31m${s}\x1b[0m`,
        yellow: (s: string) => `\x1b[33m${s}\x1b[0m`,
        dim: (s: string) => `\x1b[2m${s}\x1b[0m`,
    };
    const raw = (s: string) => ({ [Symbol.for('nodejs.util.inspect.custom')]: () => s });

    const prob = (length: number, ci: boolean) => {
        const p = ci ? 2 / 64 : 1 / 64;
        return Math.pow(p, length);
    };

    type Cat = 'start ci' | 'start cs' | 'end ci' | 'end cs';
    const categories: Cat[] = ['start ci', 'start cs', 'end ci', 'end cs'];

    const parseLength = (name: string): number | null => {
        const m = name.match(/(\d+)/);
        return m ? parseInt(m[1], 10) : null;
    };

    const categorize = (name: string): Cat | null => {
        const lower = name.toLowerCase();
        const ci = lower.includes('ci');
        if (lower.includes('start')) return ci ? 'start ci' : 'start cs';
        if (lower.includes('end')) return ci ? 'end ci' : 'end cs';
        return null;
    };

    const normalizeRate = (rate: number, length: number | null, ci: boolean) => {
        if (!length) return rate;
        const refProb = prob(5, ci);
        const curProb = prob(length, ci);
        return rate * (refProb / curProb);
    };

    function renderPivot(entries: BenchEntry[], deviceLabel: string) {
        if (!entries.length) return;
        console.log(`\nDevice: ${deviceLabel}`);
        const rows: Record<string, unknown>[] = [];

        const colLabels: Record<Cat, string> = {
            'start ci': 'start 5 ci',
            'start cs': 'start 5 cs',
            'end ci': 'end 5 ci',
            'end cs': 'end 5 cs',
        };

        for (let i = 0; i < entries.length; i++) {
            const entry = entries[i];
            const prev = i > 0 ? entries[i - 1] : null;

        const dt = new Date(entry.timestamp * 1000);
        const iso = dt.toISOString().slice(0, 10);
        const [y, m, d] = iso.split('-');
        const dateStr = `${d}.${m}.${y.slice(2)}`; // DD.MM.YY

            const row: Record<string, unknown> = {
                run: raw(String(entry.title)),
                date: raw(dateStr),
            };

            // aggregate best normalized rates per category
            const bestVal: Record<Cat, number | null> = {
                'start ci': null,
                'start cs': null,
                'end ci': null,
                'end cs': null,
            };
            const bestLen: Record<Cat, number | null> = {
                'start ci': null,
                'start cs': null,
                'end ci': null,
                'end cs': null,
            };

            for (const c of entry.cases) {
                const cat = categorize(c.name);
                if (!cat) continue;
                const len = parseLength(c.name);
                const ci = cat.endsWith('ci');
                const norm = normalizeRate(c.rate, len, ci);
                if (bestVal[cat] === null || norm > (bestVal[cat] as number)) {
                    bestVal[cat] = norm;
                    bestLen[cat] = len;
                }
            }

            const prevBest: Record<Cat, number | null> = {
                'start ci': null,
                'start cs': null,
                'end ci': null,
                'end cs': null,
            };
            if (prev) {
                for (const c of prev.cases) {
                    const cat = categorize(c.name);
                    if (!cat) continue;
                    const len = parseLength(c.name);
                    const ci = cat.endsWith('ci');
                    const norm = normalizeRate(c.rate, len, ci);
                    if (prevBest[cat] === null || norm > (prevBest[cat] as number)) {
                        prevBest[cat] = norm;
                    }
                }
            }

            for (const cat of categories) {
                const key = colLabels[cat];
                const val = bestVal[cat];
                if (val === null) {
                    row[key] = raw('-');
                    continue;
                }
                const prevVal = prevBest[cat];
                let delta = '';
                if (prevVal !== null && prevVal > 0) {
                    const pct = ((val - prevVal) / prevVal) * 100;
                    const arrow = pct >= 0 ? '▲' : '▼';
                    const valStr = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}% ${arrow}`;
                    delta = pct >= 0 ? color.green(` ${valStr}`) : color.red(` ${valStr}`);
                }
                row[key] = raw(`${val.toFixed(4)}${delta}`);
            }
            rows.push(row);
        }
        console.table(rows);
    }

    afterAll(() => {
        if (!results.length) return;
        const effectiveDevices =
            deviceNames.size > 0
                ? [...deviceNames]
                : selectedDevices.length
                  ? selectedDevices
                  : detectedDevicesAll.length
                    ? detectedDevicesAll
                    : [DEFAULT_DEVICE];
        const resolvedDeviceName =
            effectiveDevices.length === 1 ? effectiveDevices[0] : effectiveDevices.join(' + ');

        const resultsMap = readResultsMap();
        const priorEntries: BenchEntry[] = resultsMap[resolvedDeviceName] ?? [];
        const baseline = priorEntries.length ? priorEntries[priorEntries.length - 1] : null;
        console.log(`Benchmark device: ${resolvedDeviceName}${priorEntries.length ? ' (baseline loaded)' : ''}`);

        const currentEntry: BenchEntry = {
            title: addTitle || replaceTitle || '(current)',
            timestamp: Date.now() / 1000,
            cases: results,
        };

        const toShow = baseline ? [baseline, currentEntry] : [currentEntry];
        renderPivot(toShow, resolvedDeviceName);

        // Regression check vs last entry
        const regressions: string[] = [];
        if (baseline) {
            for (const r of results) {
                const prev = baseline.cases.find((c) => c.name === r.name);
                if (!prev || prev.rate <= 0 || r.rate <= 0) continue;
                const threshold = prev.rate * 0.975; // allow up to 2.5% slower
                if (r.rate < threshold) {
                    regressions.push(
                        `${r.name}: ${r.rate.toFixed(2)} < ${threshold.toFixed(2)} (prev ${prev.rate.toFixed(2)})`,
                    );
                }
            }
        }
        if (regressions.length) {
            throw new Error(`Benchmark regressions: ${regressions.join('; ')}`);
        }

        // Persist results if requested
        if (addTitle || replaceTitle) {
            const entry: BenchEntry = {
                title: (addTitle || replaceTitle)!,
                timestamp: Date.now() / 1000,
                cases: results,
            };
            let out = priorEntries;
            if (replaceTitle && priorEntries.length) {
                out = [...priorEntries.slice(0, -1), entry];
            } else {
                out = [...priorEntries, entry];
            }
            resultsMap[resolvedDeviceName] = out;
            writeResultsMap(resultsMap);
        }
    });

    it.each(benchCases)('$name', async (bc) => {
        const res = await runBenchCase(bc, 20_000);
        results.push(res);
        // At least one hit is expected for these short patterns on a GPU; if not, still keep the benchmark but flag it.
        expect(res.hits).toBeGreaterThan(0);
    });
});
