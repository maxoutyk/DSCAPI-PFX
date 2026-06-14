/**
 * Lightweight syntax highlighting for API docs code blocks.
 */
(function (global) {
  'use strict';

  function placeholderToken(index) {
    return `@@HLPH${String(index).padStart(4, '0')}@@`;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function span(cls, text) {
    return `<span class="hl-${cls}">${escapeHtml(text)}</span>`;
  }

  function protectSegments(text, pattern, store) {
    return text.replace(pattern, (match) => {
      const token = placeholderToken(store.length);
      store.push(match);
      return token;
    });
  }

  function restoreSegments(text, store, wrap) {
    let output = text;
    for (let index = store.length - 1; index >= 0; index -= 1) {
      const token = placeholderToken(index);
      output = output.split(token).join(wrap(store[index]));
    }
    return output;
  }

  function highlightJson(code) {
    const escaped = escapeHtml(code);
    const protectedChunks = [];

    let result = escaped.replace(/"(?:\\.|[^"\\])*"(\s*:)/g, (match, colon) => {
      const key = match.slice(0, match.length - colon.length);
      const html = `<span class="hl-json-key">${key}</span><span class="hl-punct">:</span>`;
      const token = placeholderToken(protectedChunks.length);
      protectedChunks.push(html);
      return token;
    });

    result = result.replace(/"(?:\\.|[^"\\])*"/g, (match) => span('string', match));

    return restoreSegments(result, protectedChunks, (chunk) => chunk);
  }

  function highlightGeneric(code, lang) {
    let result = escapeHtml(code);
    const protectedSegments = [];

    result = protectSegments(result, /'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"/g, protectedSegments);

    if (lang === 'python' || lang === 'ruby' || lang === 'php') {
      result = protectSegments(result, /#.*$/gm, protectedSegments);
    } else if (lang === 'javascript' || lang === 'nodejs' || lang === 'go' || lang === 'java') {
      result = protectSegments(result, /\/\/.*$/gm, protectedSegments);
    }

    if (lang === 'curl') {
      result = result.replace(/\bcurl\b/g, (m) => span('command', m));
      result = result.replace(/(-X|-H|-d|-s|-o)\b/g, (m) => span('flag', m));
      return restoreSegments(result, protectedSegments, (segment) => {
        if (segment.startsWith('#') || segment.startsWith('//')) {
          return span('comment', segment);
        }
        return span('string', segment);
      });
    }

    const keywordPatterns = {
      javascript: /\b(const|let|var|async|await|fetch|JSON|console|log)\b/g,
      nodejs: /\b(const|require|async|await|axios|console|log)\b/g,
      python: /\b(import|from|print|def|return|True|False|None)\b/g,
      php: /\b(\$\w+|curl_setopt|curl_init|curl_exec|curl_close|echo)\b/g,
      go: /\b(package|import|func|main|fmt|Println|panic|defer|nil)\b/g,
      java: /\b(import|public|class|void|int|String|System|out|println)\b/g,
      ruby: /\b(require|def|end|puts|true|false|nil)\b/g,
    };

    const pattern =
      keywordPatterns[lang] ||
      /\b(const|let|var|import|from|require|def|class|func|package|public|private|return|if|else|async|await|new|nil)\b/g;

    result = result.replace(pattern, (m) => span('keyword', m));
    result = result.replace(/\b([a-zA-Z_][\w]*)\s*(?=\()/g, (m) => span('function', m));

    return restoreSegments(result, protectedSegments, (segment) => {
      if (segment.startsWith('#') || segment.startsWith('//')) {
        return span('comment', segment);
      }
      return span('string', segment);
    });
  }

  function highlight(code, lang) {
    if (!code) return '';
    if (lang === 'json' || lang === 'json-error') {
      return highlightJson(code);
    }
    return highlightGeneric(code, lang);
  }

  global.ApiDocsHighlight = { highlight, highlightJson, escapeHtml };
})(window);
