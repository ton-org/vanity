const fs = require('fs');
const path = require('path');

const resultFile = path.resolve(__dirname, 'results.json');

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

if (!fs.existsSync(resultFile)) {
    console.log('No benchmark results found.');
    process.exit(0);
}

try {
    const entries = JSON.parse(fs.readFileSync(resultFile, 'utf8'));
    if (!Array.isArray(entries) || entries.length === 0) {
        console.log('No benchmark results found.');
        process.exit(0);
    }

    const util = require('util');
    const raw = (s) => ({ [util.inspect.custom]: () => s });

    const categories = ['start ci', 'start cs', 'end ci', 'end cs'];

    const rows = entries.map((entry, idx) => {
        const prev = idx > 0 ? entries[idx - 1] : null;
        const dt = new Date(entry.timestamp * 1000);
        const iso = dt.toISOString().slice(0, 10); // YYYY-MM-DD
        const [y, m, d] = iso.split('-');
        const dateStr = `${d}.${m}.${y.slice(2)}`; // DD.MM.YY

        const row = {
            run: raw(entry.title),
            date: raw(dateStr),
        };

        const best = {
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
            if (best[cat] === null || norm > best[cat]) best[cat] = norm;
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

        for (const cat of categories) {
            const val = best[cat];
            if (val === null) {
                row[cat] = raw('-');
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
            row[cat] = raw(`${val.toFixed(4)}${delta}`);
        }

        return row;
    });

    console.table(rows);
} catch (err) {
    console.error('Failed to read benchmark results:', err.message);
    process.exit(1);
}
