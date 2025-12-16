#!/usr/bin/env node
/**
 * Extracts JavaScript from embedded HTML templates in Python files for linting.
 * This allows ESLint to analyze inline JavaScript in warpie-control.py.
 */

const fs = require('fs');
const path = require('path');

const PYTHON_FILE = path.join(__dirname, '../bin/warpie-control.py');
const OUTPUT_DIR = path.join(__dirname, '../.extracted-js');

// Create output directory
if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// Read Python file
const content = fs.readFileSync(PYTHON_FILE, 'utf8');

// Find <script> blocks - matches <script>...</script> content
const scriptRegex = /<script>([\s\S]*?)<\/script>/gi;
let match;
let fileIndex = 0;

while ((match = scriptRegex.exec(content)) !== null) {
    let jsContent = match[1];

    // Handle Python f-string double braces {{ }} -> single braces { }
    jsContent = jsContent.replace(/\{\{/g, '{').replace(/\}\}/g, '}');

    // Handle template variables like {status} - wrap in comments for linting
    jsContent = jsContent.replace(/\{([a-z_]+)\}/gi, '/* TEMPLATE_VAR: $1 */');

    // Write extracted JS to file
    const outputFile = path.join(OUTPUT_DIR, `extracted-${fileIndex}.js`);

    // Add header comment
    const header = `/* eslint-disable no-undef */\n/* Extracted from warpie-control.py for linting */\n\n`;
    fs.writeFileSync(outputFile, header + jsContent);

    console.log(`Extracted JavaScript to ${outputFile}`);
    fileIndex++;
}

if (fileIndex === 0) {
    console.log('No JavaScript found to extract.');
} else {
    console.log(`\nExtracted ${fileIndex} JavaScript block(s) for linting.`);
}
