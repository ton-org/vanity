// @ts-check
import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';

const ignores = {
    ignores: ['node_modules/', 'dist/', 'build/', 'coverage/', 'contracts/', 'addresses.jsonl', 'tests/results.json'],
};

const tsConfigs = tseslint.configs.recommended.map((cfg) => ({
    ...cfg,
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
        ...cfg.languageOptions,
        parserOptions: {
            ...(cfg.languageOptions?.parserOptions ?? {}),
            ecmaVersion: 'latest',
            sourceType: 'module',
        },
    },
}));

const jsConfig = {
    files: ['**/*.js'],
    languageOptions: {
        ecmaVersion: 'latest',
        sourceType: 'commonjs',
        globals: {
            require: 'readonly',
            module: 'readonly',
            __dirname: 'readonly',
            console: 'readonly',
            process: 'readonly',
        },
    },
    rules: {
        ...eslint.configs.recommended.rules,
    },
};

export default [ignores, ...tsConfigs, jsConfig];
