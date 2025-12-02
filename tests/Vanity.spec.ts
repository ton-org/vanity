import { Blockchain, internal, SandboxContract, TreasuryContract } from '@ton/sandbox';
import { Address, beginCell, Cell, StateInit, toNano } from '@ton/core';
import '@ton/test-utils';
import { AccountStateActive } from '@ton/core/dist/types/AccountState';

describe('Vanity deployment override', () => {
    let blockchain: Blockchain;
    let deployer: SandboxContract<TreasuryContract>;

    beforeEach(async () => {
        blockchain = await Blockchain.create();
        deployer = await blockchain.treasury('deployer');
    });

    it('deploys with provided code and data refs', async () => {
        const init: StateInit = {
            code: Cell.fromBase64(
                'te6ccgEBAQEAUAAAnPJL-JKNCGACNDUWAzY8JUivnwDkKemMr2kqZKRxDW3Z8lTZ-vnjprzHBfLjIdTUMO1U-wTbMAAAAAAAAAAAjsiXvXZGMNjv0czeGgjgIA==',
            ),
            special: { tick: false, tock: false },
            splitDepth: 8,
        };
        const address = Address.parse('EQA12345ZyDu4wj__XWgqhVX7kLXieIog24xAQOxlE7hf1yz');

        const overrideCode = beginCell().storeUint(0xcafe, 16).endCell();
        const overrideData = beginCell().storeUint(0xbeef, 16).endCell();

        const deployResult = await blockchain.sendMessage(
            internal({
                from: deployer.address,
                to: address,
                stateInit: init,
                body: beginCell().storeRef(overrideCode).storeRef(overrideData).endCell(),
                value: toNano('0.05'),
            }),
        );

        expect(deployResult.transactions).toHaveTransaction({
            to: address,
            deploy: true,
            success: true,
        });

        const state = (await blockchain.getContract(address)).accountState;
        expect(state?.type).toBe('active');
        expect((state as AccountStateActive).state.code).toEqualCell(overrideCode);
        expect((state as AccountStateActive).state.data).toEqualCell(overrideData);
    });
});
