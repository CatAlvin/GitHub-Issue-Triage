const {test} = require('node:test');
const assert = require('node:assert/strict');
const {render} = require('../web/markdown.js');

test('renders document structure and fenced code', () => {
  const html = render('# Guide\n\nRead **carefully** and `run()`.\n\n- One\n- Two\n\n```js\nconst a = 1 < 2;\n```');
  assert.match(html, /<h3>Guide<\/h3>/);
  assert.match(html, /<strong>carefully<\/strong>/);
  assert.match(html, /<ul><li>One<\/li><li>Two<\/li><\/ul>/);
  assert.match(html, /<pre><code>const a = 1 &lt; 2;<\/code><\/pre>/);
});
test('escapes source HTML and rejects executable link schemes', () => {
  const html = render('<img src=x onerror=alert(1)>\n\n[bad](javascript:alert) [data](data:text/html,test)\n\n[guide](https://example.com/?q=%22)');
  assert.ok(!html.includes('<img'));
  assert.ok(!html.includes('href="javascript:'));
  assert.ok(!html.includes('href="data:'));
  assert.match(html, /rel="noopener noreferrer"/);
});
