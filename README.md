# TON Vanity

## Quickstart

Just clone the repository and run `src/generator.py`:

```bash
git clone https://github.com/ton-org/vanity
cd vanity
python3 src/generator.py --owner UQBKgXCNLPexWhs2L79kiARR1phGH1LwXxRbNsCFF9doczSI --end ABCDEF
```

You will see logs like this:

```text
Using device: Apple M2 Max
Found 1, 789.96M iters/s
Found 1, 817.28M iters/s
Found 1, 824.88M iters/s
Found 2, 829.53M iters/s
Found 3, 831.91M iters/s
Found 3, 833.50M iters/s
Found 6, 834.50M iters/s
```

You can stop it at any moment, and all the found addresses will be stored in `addresses.jsonl` file.

## Benchmarks

Generated from `tests/results.json` via `python3 scripts/chart.py`. Data comes from `npm run benchmark:print`.

![Benchmark speedups](tests/benchmarks.png)
