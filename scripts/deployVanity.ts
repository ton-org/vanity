import { toNano } from '@ton/core';
import { Vanity } from '../wrappers/Vanity';
import { compile, NetworkProvider } from '@ton/blueprint';

export async function run(provider: NetworkProvider) {
    const vanity = provider.open(Vanity.createFromConfig({}, await compile('Vanity')));

    await vanity.sendDeploy(provider.sender(), toNano('0.05'));

    await provider.waitForDeploy(vanity.address);

    // run methods on `vanity`
}
