import { Address, beginCell, Cell, Contract, contractAddress, StateInit } from '@ton/core';

export type VanityConfig = {
    owner: Address;
    salt: Buffer;
    fixedPrefixLength: number | undefined;
    special: number | undefined;
};

export class Vanity implements Contract {
    constructor(
        readonly address: Address,
        readonly init?: StateInit,
    ) {}

    static createFromAddress(address: Address) {
        return new Vanity(address);
    }

    static createFromConfig(config: VanityConfig, workchain = 0) {
        const code = buildCodeCell(config);
        const init: StateInit = { code, data: null };
        return new Vanity(contractAddress(workchain, init), init);
    }

    static createFromJsonl(address: Address, init: StateInit) {
        return new Vanity(address, init);
    }
}

const CONST1 = 1065632427291681n; // 50 bits
const CONST2 = 457587318777827214152676959512820176586892797206855680n; // 179 bits

function buildCodeCell(config: VanityConfig): Cell {
    const { owner, salt } = config;
    if (salt.length !== 16) {
        throw new Error('Salt must be exactly 16 bytes');
    }

    const builder = beginCell();
    builder.storeUint(CONST1, 50);
    builder.storeAddress(owner); // tag, anycast, workchain, addr hash
    builder.storeUint(CONST2, 179);
    builder.storeBuffer(salt);

    return builder.endCell();
}
