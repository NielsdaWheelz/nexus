#!/usr/bin/env node
/**
 * HTML Readability Helper
 *
 * Uses @mozilla/readability to extract article content from HTML.
 * Reads HTML from stdin, outputs JSON to stdout.
 */

const { Readability } = require('@mozilla/readability');
const { JSDOM } = require('jsdom');

// Read all stdin data
let htmlData = '';

process.stdin.on('data', chunk => {
  htmlData += chunk;
});

process.stdin.on('end', () => {
  try {
    // Create a virtual DOM from the HTML
    const dom = new JSDOM(htmlData, {
      url: 'http://example.com' // Dummy URL for relative link resolution
    });

    // Create Readability instance and extract article
    const reader = new Readability(dom.window.document);
    const article = reader.parse();

    if (!article) {
      // If readability failed, extract plain text
      const text = dom.window.document.body.textContent.trim();
      console.log(JSON.stringify({ text, title: '', byline: '' }));
    } else {
      // Convert article HTML to plain text by extracting text content
      const dom2 = new JSDOM(article.content);
      const text = dom2.window.document.body.textContent.trim();

      console.log(JSON.stringify({
        text,
        title: article.title || '',
        byline: article.byline || ''
      }));
    }
  } catch (error) {
    // Fallback: extract all text
    const dom = new JSDOM(htmlData);
    const text = dom.window.document.body.textContent.trim();
    console.log(JSON.stringify({ text, title: '', byline: '', error: error.message }));
  }
});
