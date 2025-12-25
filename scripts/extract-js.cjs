#!/usr/bin/env node
/**
 * Extracts JavaScript from embedded HTML templates for linting.
 * This allows ESLint to analyze inline JavaScript in Flask templates.
 * Also copies web/static/warpie.js for standalone linting.
 */

const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = path.join(__dirname, '../.extracted-js');
const STATIC_JS = path.join(__dirname, '../web/static/warpie.js');
const TEMPLATES_DIR = path.join(__dirname, '../web/templates');

// Create output directory
if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

let fileIndex = 0;

// Copy static JavaScript file for linting
if (fs.existsSync(STATIC_JS)) {
    const content = fs.readFileSync(STATIC_JS, 'utf8');
    const outputFile = path.join(OUTPUT_DIR, 'warpie.js');
    const header = `/* eslint-disable no-undef */\n/* web/static/warpie.js */\n\n`;
    fs.writeFileSync(outputFile, header + content);
    console.log(`Copied ${STATIC_JS} to ${outputFile}`);
    fileIndex++;
}

// Extract JavaScript from Jinja2 templates
function extractFromTemplates(dir) {
    if (!fs.existsSync(dir)) return;

    const files = fs.readdirSync(dir, { withFileTypes: true });
    for (const file of files) {
        const fullPath = path.join(dir, file.name);
        if (file.isDirectory()) {
            extractFromTemplates(fullPath);
        } else if (file.name.endsWith('.html')) {
            const content = fs.readFileSync(fullPath, 'utf8');

            // Find <script> blocks
            const scriptRegex = /<script>([\s\S]*?)<\/script>/gi;
            let match;
            let scriptIndex = 0;

            while ((match = scriptRegex.exec(content)) !== null) {
                let jsContent = match[1].trim();
                if (!jsContent) continue;

                // Handle Jinja2 double braces {{ }} -> single braces { }
                jsContent = jsContent.replace(/\{\{/g, '{').replace(/\}\}/g, '}');

                // Handle template variables like {{ status }} - wrap in comments
                jsContent = jsContent.replace(/\{%.*?%\}/g, '/* JINJA_BLOCK */');
                jsContent = jsContent.replace(/\{\s*([a-z_]+)\s*\}/gi, '/* TEMPLATE_VAR: $1 */');

                const baseName = path.basename(file.name, '.html');
                const outputFile = path.join(OUTPUT_DIR, `${baseName}-${scriptIndex}.js`);
                const header = `/* eslint-disable no-undef */\n/* Extracted from ${file.name} */\n\n`;
                fs.writeFileSync(outputFile, header + jsContent);
                console.log(`Extracted JavaScript to ${outputFile}`);
                scriptIndex++;
                fileIndex++;
            }
        }
    }
}

extractFromTemplates(TEMPLATES_DIR);

if (fileIndex === 0) {
    console.log('No JavaScript found to extract.');
} else {
    console.log(`\nExtracted/copied ${fileIndex} JavaScript file(s) for linting.`);
}
