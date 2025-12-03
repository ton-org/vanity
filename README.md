# TON Vanity

A blazingly fast vanity address generator for TON Blockchain. Built with OpenCL and powered by numerous TON-specific optimizations. Check out the [Benchmarks](#benchmarks) and [Optimizations](#optimizations) sections for more details.

## Quickstart

Clone the repository and run `src/generator.py`:

```bash
git clone https://github.com/ton-org/vanity
cd vanity
python3 src/generator.py --owner EQBGhqLAZseEqRXz4ByFPTGV7SVMlI4hrbs-Sps_Xzx01x8G --end ABCDEF
```

You will see output like this:

```text
Using device: [0] Apple M2 Max
Found 1, 789.96M iters/s
Found 1, 817.28M iters/s
Found 1, 824.88M iters/s
Found 2, 829.53M iters/s
Found 3, 831.91M iters/s
Found 3, 833.50M iters/s
Found 6, 834.50M iters/s
```

You can stop the generator at any time. All discovered addresses are saved to the `addresses.jsonl` file.

The output file contains lines in the following format:

```json
{
    "address": "EQBSCgaA2cK7x-vKrERl84nikhPm1AbBdujoa6RlLRABCDEf",
    "init": {
        "code": "te6ccgEBAQEAUAAAnPJL-JKNCGACNDUWAzY8JUivnwDkKemMr2kqZKRxDW3Z8lTZ-vnjprzHBfLjIdTUMO1U-wTbMAAAAAAAAAAAmEQScKFrbwHa97YAdBCNCQ==",
        "fixedPrefixLength": 8,
        "special": null
    },
    "config": {
        "owner": "EQBGhqLAZseEqRXz4ByFPTGV7SVMlI4hrbs-Sps_Xzx01x8G",
        "start": null,
        "end": "ABCDEF",
        "masterchain": false,
        "non_bounceable": false,
        "testnet": false,
        "case_sensitive": false,
        "only_one": false
    },
    "timestamp": 1764743367.707375
}
```

Here is what each field represents:

- `address`: The resulting vanity address. Always use this value directly from the output to ensure the fixed prefix length is properly accounted for.
- `init`: A `StateInit`-like object for deployment. The `code` field is a Base64-encoded BoC, and `fixedPrefixLength` is the proper name for the legacy `splitDepth` parameter from the [@ton/core](https://github.com/ton-org/ton-core) library.
- `config`: The configuration settings used to generate this address.
- `timestamp`: The Unix timestamp (in seconds) when this address was generated.

You can use this output to deploy any smart contract to your vanity address. Make sure to include [wrappers/Vanity.ts](wrappers/Vanity.ts) in your project directory. Here is an example for sandbox tests:

```ts
import { Blockchain, SandboxContract, TreasuryContract } from '@ton/sandbox';
import { Cell, toNano } from '@ton/core';
import { Example } from '../wrappers/Example';
import '@ton/test-utils';
import { compile } from '@ton/blueprint';
import { ContractWithVanity, Vanity } from '../wrappers/Vanity';

describe('Example', () => {
    let code: Cell;

    beforeAll(async () => {
        code = await compile('Example');
    });

    let blockchain: Blockchain;
    let deployer: SandboxContract<TreasuryContract>;
    let example: SandboxContract<ContractWithVanity<Example>>;

    beforeEach(async () => {
        blockchain = await Blockchain.create();

        const found =
            '{"address":"EQBSCgaA2cK7x-vKrERl84nikhPm1AbBdujoa6RlLRABCDEf","init":{"code":"te6ccgEBAQEAUAAAnPJL-JKNCGACNDUWAzY8JUivnwDkKemMr2kqZKRxDW3Z8lTZ-vnjprzHBfLjIdTUMO1U-wTbMAAAAAAAAAAAmEQScKFrbwHa97YAdBCNCQ==","fixedPrefixLength":8,"special":null},"config":{"owner":"EQBGhqLAZseEqRXz4ByFPTGV7SVMlI4hrbs-Sps_Xzx01x8G","start":null,"end":"ABCDEF","masterchain":false,"non_bounceable":false,"testnet":false,"case_sensitive":false,"only_one":false},"timestamp":1764743367.707375}';
        const vanity = Vanity.createFromLine(found);

        example = blockchain.openContract(
            vanity.installContract(
                Example.createFromConfig(
                    {
                        id: 0,
                        counter: 0,
                    },
                    code,
                ),
            ),
        );

        deployer = await blockchain.treasury('deployer');

        const deployResult = await example.sendDeployVanity(deployer.getSender(), toNano('0.05'));

        expect(deployResult.transactions).toHaveTransaction({
            from: deployer.address,
            to: example.address,
            deploy: true,
            success: true,
        });
    });

    it('should deploy', async () => {
        // the check is done inside beforeEach
        // blockchain and example are ready to use
    });
});
```

## Benchmarks

Generated from [tests/results.json](tests/results.json) using [scripts/chart.py](scripts/chart.py). The data is collected via `npm run benchmark:print`.

![Benchmark speedups](tests/benchmarks.png)

## Prior art

Before TON Vanity, the de facto standard for vanity addresses of arbitrary contracts on TON was [ton-community/vanity-contract](https://github.com/ton-community/vanity-contract).

It introduced the now-common pattern:

- mine a `salt` off-chain with a GPU tool until the `StateInit` produces a desired prefix or suffix
- deploy a generic vanity contract bound to an `owner` address
- have that contract install the final code and data in a single deploy transaction

TON Vanity keeps the same usage pattern and deployment flow but replaces both the miner and the on-chain contract with a new implementation focused on throughput and TON-specific optimizations, while also improving CLI design, TypeScript integration, and overall UX. In our benchmarks mirroring common use cases, this results in speedups of up to multiple orders of magnitude over [ton-community/vanity-contract](https://github.com/ton-community/vanity-contract), depending on the pattern and hardware used.
See [Benchmarks](#benchmarks) for details.

## Optimizations

**A detailed write-up covering all optimizations and the development process will be published soon.**

The key optimizations include:

- Using `fixed_prefix_length` for first 8 bits of prefix
- A low-level smart contract implementation that places the salt in the `code` cell, allowing `StateInit` hashes to be computed with just 2 blocks of SHA-256 per address
- Iterable `special` and `fixed_prefix_length` parameters in `StateInit` that enable recomputing just 1 block of SHA-256 per address for most iterations

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.
