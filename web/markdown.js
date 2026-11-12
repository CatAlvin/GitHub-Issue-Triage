"use strict";
const WorkbenchMarkdown = (() => {
  const escape = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  function inline(text) {
    const pattern = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|\[([^\]\n]+)\]\(([^\s)]+)\)/g;
    let output = "", start = 0;
    for (const match of text.matchAll(pattern)) {
      output += escape(text.slice(start, match.index));
      if (match[1]) output += "<code>" + escape(match[1]) + "</code>";
      else if (match[2]) output += "<strong>" + escape(match[2]) + "</strong>";
      else {
        let url;
        try { const parsed = new URL(match[4]); if (["http:", "https:"].includes(parsed.protocol)) url = parsed.href; } catch {}
        output += url ? '<a href="' + escape(url) + '" target="_blank" rel="noopener noreferrer">' + escape(match[3]) + '</a>' : escape(match[3]);
      }
      start = match.index + match[0].length;
    }
    return output + escape(text.slice(start));
  }
  function render(value) {
    const output = [], paragraph = [], code = [];
    let fenced = false, list = "";
    const flush = () => { if (paragraph.length) { output.push("<p>" + inline(paragraph.join(" ")) + "</p>"); paragraph.length = 0; } };
    const endList = () => { if (list) { output.push("</" + list + ">"); list = ""; } };
    for (const line of String(value).replace(/\r/g, "").split("\n")) {
      if (/^\s*```/.test(line)) {
        flush(); endList();
        if (fenced) { output.push("<pre><code>" + escape(code.join("\n")) + "</code></pre>"); code.length = 0; }
        fenced = !fenced; continue;
      }
      if (fenced) { code.push(line); continue; }
      if (!line.trim()) { flush(); endList(); continue; }
      const heading = line.match(/^#{1,6}\s+(.+)$/);
      const item = line.match(/^\s*(?:([-*+])|\d+\.)\s+(.+)$/);
      if (heading) { flush(); endList(); output.push("<h3>" + inline(heading[1]) + "</h3>"); }
      else if (item) {
        flush(); const type = item[1] ? "ul" : "ol";
        if (list !== type) { endList(); list = type; output.push("<" + list + ">"); }
        output.push("<li>" + inline(item[2]) + "</li>");
      } else { endList(); paragraph.push(line); }
    }
    flush(); endList();
    if (fenced) output.push("<pre><code>" + escape(code.join("\n")) + "</code></pre>");
    return output.join("");
  }
  return { render };
})();
if (typeof module !== "undefined") module.exports = WorkbenchMarkdown;
