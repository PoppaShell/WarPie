/** @type {import('jest').Config} */
module.exports = {
    testEnvironment: 'jsdom',
    testMatch: ['**/tests/javascript/**/*.test.js'],
    verbose: true,
    collectCoverageFrom: [
        '.extracted-js/**/*.js',
    ],
    coverageDirectory: 'coverage/javascript',
    moduleFileExtensions: ['js'],
};
