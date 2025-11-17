import { Address, beginCell, Cell, Contract, contractAddress, ContractProvider, Sender, SendMode } from '@ton/core';

export type VanityConfig = {};

export function vanityConfigToCell(config: VanityConfig): Cell {
    return beginCell().endCell();
}

export class Vanity implements Contract {
    constructor(readonly address: Address, readonly init?: { code: Cell; data: Cell }) {}

    static createFromAddress(address: Address) {
        return new Vanity(address);
    }

    static createFromConfig(config: VanityConfig, code: Cell, workchain = 0) {
        const data = vanityConfigToCell(config);
        const init = { code, data };
        return new Vanity(contractAddress(workchain, init), init);
    }

    async sendDeploy(provider: ContractProvider, via: Sender, value: bigint) {
        await provider.internal(via, {
            value,
            sendMode: SendMode.PAY_GAS_SEPARATELY,
            body: beginCell().endCell(),
        });
    }
}
