const { defineConfig } = require("eslint/config");
const globals = require("globals");
const js = require("@eslint/js");

module.exports = defineConfig([
    {
        files: ["**/*.js", "**/*.mjs"],
        ignores: ["eslint.config.js"],
        ...js.configs.recommended,

        languageOptions: {
            ecmaVersion: "latest",
            sourceType: "module",
            parserOptions: {},
            globals: {
                ...globals.browser,
            },
        },

        rules: {
            "no-unused-vars": ["error", {
                args: "all",
                argsIgnorePattern: "^_",
            }],
            indent: ["error", 4],
            "linebreak-style": ["error", "unix"],
            quotes: ["error", "double"],
            semi: ["error", "always"],
        },
    },
    {
        files: ["eslint.config.js", "**/*.cjs"],
        languageOptions: {
            sourceType: "script",
            globals: {
                ...globals.node,
            },
        },
    }
]);
