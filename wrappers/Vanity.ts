import { Address, beginCell, Cell, Contract, ContractProvider, Sender, SendMode, StateInit } from '@ton/core';

export type VanityConfig = {
    owner: Address;
    salt: Buffer;
    fixedPrefixLength: number | undefined;
    special: number | undefined;
};

type VanityExtra = {
    sendDeployVanity: (provider: ContractProvider, via: Sender, value: bigint) => Promise<void>;
};

export type ContractWithVanity<T extends Contract = Contract> = T & VanityExtra;

export class Vanity implements Contract {
    constructor(
        readonly address: Address,
        readonly init?: StateInit,
    ) {}

    static createFromLine(line: string) {
        type VanityInitJson = {
            code: string;
            data?: string;
            fixedPrefixLength?: number;
            special?: { tick: boolean; tock: boolean } | null;
        };
        type VanityLineJson = { address: string; init: VanityInitJson };

        const obj = JSON.parse(line) as VanityLineJson;
        const address = Address.parse(obj.address);

        const init: StateInit = {
            code: Cell.fromBase64(obj.init.code),
            splitDepth: obj.init.fixedPrefixLength ?? undefined,
        };
        if (obj.init.data) {
            init.data = Cell.fromBase64(obj.init.data);
        }
        if (obj.init.special) {
            init.special = {
                tick: !!obj.init.special.tick,
                tock: !!obj.init.special.tock,
            };
        }

        return new Vanity(address, init);
    }

    installContract<T extends Contract>(contract: T): ContractWithVanity<T> {
        // eslint-disable-next-line @typescript-eslint/no-this-alias
        const self = this;

        const extra: VanityExtra = {
            async sendDeployVanity(provider: ContractProvider, via: Sender, value: bigint) {
                await provider.internal(via, {
                    value,
                    sendMode: SendMode.PAY_GAS_SEPARATELY,
                    body: beginCell()
                        .storeRef(contract.init?.code ?? Cell.EMPTY)
                        .storeRef(contract.init?.data ?? Cell.EMPTY)
                        .endCell(),
                });
            },
        };

        const proxy = new Proxy(contract as T & VanityExtra, {
            get(target, prop, receiver) {
                if (prop === 'init') {
                    return self.init;
                }
                if (prop === 'address') {
                    return self.address;
                }
                if (prop === 'sendDeployVanity') {
                    return extra.sendDeployVanity;
                }
                return Reflect.get(target, prop, receiver);
            },
        });

        return proxy as ContractWithVanity<T>;
    }
}
