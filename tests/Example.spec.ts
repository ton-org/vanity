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
            '{"address":"EQD12345QQ0WDEDtlc2hzBX4ME0Dg3WKP0t24f2-bjPCLBZI","init":{"code":"te6ccgEBAQEAUAAAnPJL-JKNCGACNDUWAzY8JUivnwDkKemMr2kqZKRxDW3Z8lTZ-vnjprzHBfLjIdTUMO1U-wTbMAAAAAAAAAAAtLfjazTeo4i83Aq6iVeb1g==","fixedPrefixLength":8,"special":{"tick":false,"tock":false}},"config":{"owner":"EQBGhqLAZseEqRXz4ByFPTGV7SVMlI4hrbs-Sps_Xzx01x8G","start":"12345","end":null,"masterchain":false,"non_bounceable":false,"testnet":false,"case_sensitive":true,"only_one":false},"timestamp":1764681137.069358}';
        const vanity = blockchain.openContract(Vanity.createFromLine(found));

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

    it('should increase counter', async () => {
        const increaseTimes = 3;
        for (let i = 0; i < increaseTimes; i++) {
            console.log(`increase ${i + 1}/${increaseTimes}`);

            const increaser = await blockchain.treasury('increaser' + i);

            const counterBefore = await example.getCounter();

            console.log('counter before increasing', counterBefore);

            const increaseBy = Math.floor(Math.random() * 100);

            console.log('increasing by', increaseBy);

            const increaseResult = await example.sendIncrease(increaser.getSender(), {
                increaseBy,
                value: toNano('0.05'),
            });

            expect(increaseResult.transactions).toHaveTransaction({
                from: increaser.address,
                to: example.address,
                success: true,
            });

            const counterAfter = await example.getCounter();

            console.log('counter after increasing', counterAfter);

            expect(counterAfter).toBe(counterBefore + increaseBy);
        }
    });

    it('should reset counter', async () => {
        const increaser = await blockchain.treasury('increaser');

        expect(await example.getCounter()).toBe(0);

        const increaseBy = 5;
        await example.sendIncrease(increaser.getSender(), {
            increaseBy,
            value: toNano('0.05'),
        });

        expect(await example.getCounter()).toBe(increaseBy);

        await example.sendReset(increaser.getSender(), {
            value: toNano('0.05'),
        });

        expect(await example.getCounter()).toBe(0);
    });
});
