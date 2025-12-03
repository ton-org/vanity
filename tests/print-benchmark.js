const fs = require('fs');
const path = require('path');

const RESULT_FILE = path.resolve(__dirname, 'results.json');
const DEFAULT_DEVICE_LABEL = 'Unknown device';
const CATEGORIES = ['start ci', 'start cs', 'end ci', 'end cs'];

const prob = (length, ci) => {
    const p = ci ? 2 / 64 : 1 / 64;
    return Math.pow(p, length);
};

const parseLength = (name) => {
    const m = name.match(/(\d+)/);
    return m ? parseInt(m[1], 10) : null;
};

const categorize = (name) => {
    const lower = name.toLowerCase();
    const ci = lower.includes('ci');
    if (lower.includes('start')) return ci ? 'start ci' : 'start cs';
    if (lower.includes('end')) return ci ? 'end ci' : 'end cs';
    return null;
};

const normalizeRate = (rate, length, ci) => {
    if (!length) return rate;
    const refProb = prob(5, ci);
    const curProb = prob(length, ci);
    return rate * (refProb / curProb);
};
const raw = (s) => ({ [Symbol.for('nodejs.util.inspect.custom')]: () => s });

const argv = process.argv;
let deviceFilter = null;
for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--device' && i + 1 < argv.length) {
        deviceFilter = argv[i + 1].toLowerCase();
    }
}

const readResultsMap = () => {
    if (!fs.existsSync(RESULT_FILE)) {
        return {};
    }
    try {
        const data = JSON.parse(fs.readFileSync(RESULT_FILE, 'utf8'));
        if (Array.isArray(data)) {
            return { [DEFAULT_DEVICE_LABEL]: data };
        }
        if (data && typeof data === 'object') {
            return data;
        }
    } catch {
        return {};
    }
    return {};
};

const renderPivot = (label, entries) => {
    if (!entries.length) return;
    const rows = [];

    const colLabels = {
        'start ci': 'start 5 ci',
        'start cs': 'start 5 cs',
        'end ci': 'end 5 ci',
        'end cs': 'end 5 cs',
    };

    for (let i = 0; i < entries.length; i++) {
        const entry = entries[i];
        const prev = i > 0 ? entries[i - 1] : null;

        const dt = new Date(entry.timestamp * 1000);
        const iso = dt.toISOString().slice(0, 10); // YYYY-MM-DD
        const [y, m, d] = iso.split('-');
        const dateStr = `${d}.${m}.${y.slice(2)}`; // DD.MM.YY

        const row = {
            run: raw(String(entry.title)),
            date: raw(dateStr),
        };

        const best = {
            'start ci': null,
            'start cs': null,
            'end ci': null,
            'end cs': null,
        };
        const bestLen = {
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
            if (best[cat] === null || norm > best[cat]) {
                best[cat] = norm;
                bestLen[cat] = len;
            }
        }

        const prevBest = {
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
                if (prevBest[cat] === null || norm > prevBest[cat]) prevBest[cat] = norm;
            }
        }

        for (const cat of CATEGORIES) {
            const key = colLabels[cat];
            const val = best[cat];
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
                delta = pct >= 0 ? ` \x1b[32m${valStr}\x1b[0m` : ` \x1b[31m${valStr}\x1b[0m`;
            }
            row[key] = raw(`${val.toFixed(4)}${delta}`);
        }

        rows.push(row);
    }

    console.log(`\nDevice: ${label}`);
    console.table(rows);
};

const map = readResultsMap();
const entries = Object.entries(map).filter(([label]) =>
    deviceFilter ? label.toLowerCase().includes(deviceFilter) : true,
);

if (!entries.length) {
    console.log('No benchmark results found.');
    process.exit(0);
}

for (const [label, arr] of entries) {
    renderPivot(label, arr);
}
