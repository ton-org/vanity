import { toNano } from '@ton/core';
import { Example } from '../wrappers/Example';
import { compile, NetworkProvider } from '@ton/blueprint';

export async function run(provider: NetworkProvider) {
    const example = provider.open(
        Example.createFromConfig(
            {
                id: Math.floor(Math.random() * 10000),
                counter: 0,
            },
            await compile('Example'),
        ),
    );

    await example.sendDeploy(provider.sender(), toNano('0.05'));

    await provider.waitForDeploy(example.address);

    console.log('ID', await example.getID());
}
