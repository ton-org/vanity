import { Blockchain, SandboxContract, TreasuryContract } from '@ton/sandbox';
import { Cell, toNano } from '@ton/core';
import { Vanity } from '../wrappers/Vanity';
import '@ton/test-utils';
import { compile } from '@ton/blueprint';

describe('Vanity', () => {
    let code: Cell;

    beforeAll(async () => {
        code = await compile('Vanity');
    });

    let blockchain: Blockchain;
    let deployer: SandboxContract<TreasuryContract>;
    let vanity: SandboxContract<Vanity>;

    beforeEach(async () => {
        blockchain = await Blockchain.create();

        vanity = blockchain.openContract(Vanity.createFromConfig({}, code));

        deployer = await blockchain.treasury('deployer');

        const deployResult = await vanity.sendDeploy(deployer.getSender(), toNano('0.05'));

        expect(deployResult.transactions).toHaveTransaction({
            from: deployer.address,
            to: vanity.address,
            deploy: true,
            success: true,
        });
    });

    it('should deploy', async () => {
        // the check is done inside beforeEach
        // blockchain and vanity are ready to use
    });
});
