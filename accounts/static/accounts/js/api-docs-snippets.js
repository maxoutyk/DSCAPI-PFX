/**
 * API docs code snippet generators and Postman collection builders.
 */
(function (global) {
  'use strict';

  const LANGS = [
    { id: 'curl', label: 'cURL' },
    { id: 'javascript', label: 'JavaScript' },
    { id: 'python', label: 'Python' },
    { id: 'nodejs', label: 'Node.js' },
    { id: 'php', label: 'PHP' },
    { id: 'go', label: 'Go' },
    { id: 'java', label: 'Java' },
    { id: 'ruby', label: 'Ruby' },
  ];

  const PATH_PARAM_SAMPLES = {
    job_id: 'a93e5d39-7f3e-44ba-a901-90f0cf1a4ea7',
  };

  const QUERY_PARAM_SAMPLES = {
    fy: '2024-25',
    type: 'R1',
    gstin: '33AAUPP8709M3ZS',
    include_pdf: '1',
    format: 'json',
  };

  function exampleQueryValue(name, type) {
    if (QUERY_PARAM_SAMPLES[name] !== undefined) {
      return QUERY_PARAM_SAMPLES[name];
    }
    if (type === 'integer') return '1';
    return 'value';
  }

  function parseJsonBody(raw) {
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (_err) {
      return raw;
    }
  }

  function isPathParam(path, name) {
    return path.includes(`{${name}}`);
  }

  function buildRequestSpec(item, baseUrl) {
    if (item.kind === 'guide') {
      if (item.curl) {
        return { guide: true, curl: item.curl };
      }
      return { guide: true, hidden: true };
    }

    const method = (item.method || 'GET').toUpperCase();
    const rawPath = item.path || '';
    const external = rawPath.startsWith('http');
    let path = rawPath;

    if (!external) {
      path = path.replace(/\{(\w+)\}/g, (_, name) => PATH_PARAM_SAMPLES[name] || `{${name}}`);
    }

    const url = external ? path : `${baseUrl}${path}`;
    const query = {};
    const headers = {};

    if (!external || !url.includes('127.0.0.1:9765')) {
      if (external) {
        headers['Content-Type'] = 'application/json';
      } else {
        headers.Authorization = 'Bearer dsc_live_YOUR_KEY';
        if (method !== 'GET') {
          headers['Content-Type'] = 'application/json';
        }
      }
    } else {
      headers['Content-Type'] = 'application/json';
    }

    (item.parameters || []).forEach((param) => {
      if (isPathParam(rawPath, param.name)) return;
      if (method === 'GET' && param.required) {
        query[param.name] = exampleQueryValue(param.name, param.type);
      }
    });

    const body = method === 'GET' ? null : parseJsonBody(item.request_json);

    return { method, url, headers, query, body, external };
  }

  function appendQuery(url, query) {
    const keys = Object.keys(query || {});
    if (!keys.length) return url;
    const qs = keys
      .map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(query[key])}`)
      .join('&');
    return `${url}${url.includes('?') ? '&' : '?'}${qs}`;
  }

  function jsonPretty(value) {
    if (typeof value === 'string') return value;
    return JSON.stringify(value, null, 2);
  }

  function shellEscape(value) {
    return String(value).replace(/'/g, "'\\''");
  }

  function generateSnippet(lang, spec) {
    if (spec.guide && spec.hidden) {
      return '';
    }
    if (spec.guide && spec.curl) {
      return lang === 'curl' ? spec.curl : '# See cURL tab for this guide example.';
    }

    const url = appendQuery(spec.url, spec.query);
    const hasBody = spec.body !== null && spec.body !== undefined && spec.method !== 'GET';
    const bodyText = hasBody ? jsonPretty(spec.body) : '';

    switch (lang) {
      case 'curl':
        return generateCurl(spec, url, hasBody, bodyText);
      case 'javascript':
        return generateJavaScript(spec, url, hasBody, bodyText);
      case 'python':
        return generatePython(spec, url, hasBody, bodyText);
      case 'nodejs':
        return generateNode(spec, url, hasBody, bodyText);
      case 'php':
        return generatePhp(spec, url, hasBody, bodyText);
      case 'go':
        return generateGo(spec, url, hasBody, bodyText);
      case 'java':
        return generateJava(spec, url, hasBody, bodyText);
      case 'ruby':
        return generateRuby(spec, url, hasBody, bodyText);
      default:
        return generateCurl(spec, url, hasBody, bodyText);
    }
  }

  function generateCurl(spec, url, hasBody, bodyText) {
    const lines = [`curl -X ${spec.method} "${url}" \\`];
    Object.entries(spec.headers).forEach(([key, value]) => {
      lines.push(`  -H "${key}: ${value}" \\`);
    });
    if (hasBody) {
      const compact = typeof spec.body === 'string' ? spec.body : JSON.stringify(spec.body);
      lines.push(`  -d '${shellEscape(compact)}'`);
    } else {
      lines[lines.length - 1] = lines[lines.length - 1].replace(/ \\$/, '');
    }
    return lines.join('\n');
  }

  function generateJavaScript(spec, url, hasBody, bodyText) {
    const headerLines = Object.entries(spec.headers)
      .map(([key, value]) => `    '${key}': '${value}',`)
      .join('\n');
    let bodyBlock = '';
    if (hasBody) {
      if (typeof spec.body === 'string') {
        bodyBlock = `  body: ${JSON.stringify(spec.body)},\n`;
      } else {
        bodyBlock = `  body: JSON.stringify(${JSON.stringify(spec.body)}),\n`;
      }
    }
    return `const response = await fetch('${url}', {
  method: '${spec.method}',
  headers: {
${headerLines}
  },
${bodyBlock}});

const data = await response.json();
console.log(data);`;
  }

  function generatePython(spec, url, hasBody, bodyText) {
    const headerLines = Object.entries(spec.headers)
      .map(([key, value]) => `    '${key}': '${value}',`)
      .join('\n');
    let bodyPart = '';
    if (hasBody) {
      if (typeof spec.body === 'string') {
        bodyPart = `\npayload = '''${bodyText}'''\nresponse = requests.${spec.method.toLowerCase()}(url, headers=headers, data=payload)`;
      } else {
        bodyPart = `\npayload = ${bodyText}\nresponse = requests.${spec.method.toLowerCase()}(url, headers=headers, json=payload)`;
      }
    } else {
      bodyPart = `\nresponse = requests.${spec.method.toLowerCase()}(url, headers=headers)`;
    }
    return `import requests

url = '${url}'
headers = {
${headerLines}
}
${bodyPart}
print(response.json())`;
  }

  function generateNode(spec, url, hasBody, bodyText) {
    const headerLines = Object.entries(spec.headers)
      .map(([key, value]) => `      '${key}': '${value}',`)
      .join('\n');
    const dataBlock = hasBody
      ? typeof spec.body === 'string'
        ? `    data: '${shellEscape(bodyText)}',\n`
        : `    data: ${JSON.stringify(spec.body)},\n`
      : '';
    return `const axios = require('axios');

async function run() {
  const response = await axios({
    method: '${spec.method.toLowerCase()}',
    url: '${url}',
    headers: {
${headerLines}
    },
${dataBlock}  });
  console.log(response.data);
}

run().catch(console.error);`;
  }

  function generatePhp(spec, url, hasBody, bodyText) {
    const headerLines = Object.entries(spec.headers)
      .map(([key, value]) => `    '${key}: ${value}'`)
      .join(',\n');
    const bodyPart = hasBody
      ? typeof spec.body === 'string'
        ? `\n$body = '${shellEscape(bodyText)}';\ncurl_setopt($ch, CURLOPT_POSTFIELDS, $body);`
        : `\n$body = json_encode(${bodyText.replace(/\n/g, '')});\ncurl_setopt($ch, CURLOPT_POSTFIELDS, $body);`
      : '';
    return `<?php
$ch = curl_init('${url}');
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, '${spec.method}');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
${headerLines}
]);${bodyPart}
$response = curl_exec($ch);
curl_close($ch);
echo $response;`;
  }

  function generateGo(spec, url, hasBody, bodyText) {
    const bodyVar = hasBody
      ? typeof spec.body === 'string'
        ? `body := strings.NewReader(\`${bodyText}\`)`
        : `body := strings.NewReader(\`${JSON.stringify(spec.body)}\`)`
      : 'var body io.Reader';
    const bodyArg = hasBody ? 'body' : 'nil';
    const headerBlock = Object.entries(spec.headers)
      .map(([key, value]) => `\treq.Header.Set("${key}", "${value}")`)
      .join('\n');
    return `package main

import (
\t"fmt"
\t"io"
\t"net/http"
\t"strings"
)

func main() {
\t${bodyVar}
\treq, err := http.NewRequest("${spec.method}", "${url}", ${bodyArg})
\tif err != nil {
\t\tpanic(err)
\t}
${headerBlock}
\tresp, err := http.DefaultClient.Do(req)
\tif err != nil {
\t\tpanic(err)
\t}
\tdefer resp.Body.Close()
\tb, _ := io.ReadAll(resp.Body)
\tfmt.Println(string(b))
}`;
  }

  function generateJava(spec, url, hasBody, bodyText) {
    const bodySend = hasBody
      ? `String json = ${JSON.stringify(bodyText)};\nconn.getOutputStream().write(json.getBytes(StandardCharsets.UTF_8));`
      : '';
    return `import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

URL url = new URL("${url}");
HttpURLConnection conn = (HttpURLConnection) url.openConnection();
conn.setRequestMethod("${spec.method}");
${Object.entries(spec.headers)
  .map(([key, value]) => `conn.setRequestProperty("${key}", "${value}");`)
  .join('\n')}
conn.setDoOutput(${hasBody ? 'true' : 'false'});
${bodySend}
int code = conn.getResponseCode();
System.out.println("Status: " + code);`;
  }

  function generateRuby(spec, url, hasBody, bodyText) {
    const headers = Object.entries(spec.headers)
      .map(([key, value]) => `  '${key}' => '${value}'`)
      .join(',\n');
    const httpClass = spec.method.charAt(0) + spec.method.slice(1).toLowerCase();
    const bodyPart = hasBody
      ? typeof spec.body === 'string'
        ? `\nrequest.body = '${shellEscape(bodyText)}'`
        : `\nrequest.body = ${bodyText}.to_json`
      : '';
    return `require 'net/http'
require 'json'
require 'uri'

uri = URI('${url}')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = (uri.scheme == 'https')

request = Net::HTTP::${httpClass}.new(uri)
request.initialize_http_header({
${headers}
})${bodyPart}

response = http.request(request)
puts response.body`;
  }

  function postmanUrlObject(spec, baseUrl) {
    const raw = appendQuery(spec.url, spec.query);
    const variableRaw = raw.replace(baseUrl, '{{base_url}}');
    return {
      raw: variableRaw,
    };
  }

  function buildPostmanRequest(item, spec, baseUrl) {
    const usesPlatformAuth = !spec.external || !(spec.url || '').includes('127.0.0.1:9765');
    const request = {
      method: spec.method,
      header: Object.entries(spec.headers).map(([key, value]) => ({
        key,
        value: key === 'Authorization' ? 'Bearer {{api_key}}' : value,
        type: 'text',
      })),
      url: postmanUrlObject(spec, baseUrl),
      description: item.description || '',
    };

    if (spec.body && spec.method !== 'GET') {
      const raw = typeof spec.body === 'string' ? spec.body : JSON.stringify(spec.body, null, 2);
      request.body = {
        mode: 'raw',
        raw,
        options: { raw: { language: 'json' } },
      };
    }

    if (usesPlatformAuth && !spec.external) {
      request.auth = {
        type: 'bearer',
        bearer: [{ key: 'token', value: '{{api_key}}', type: 'string' }],
      };
    }

    return request;
  }

  function buildPostmanCollection(items, catalog, selectedItem) {
    const endpoints = items.filter((item) => item.kind === 'endpoint' || (item.kind === 'guide' && item.curl));
    const collectionItems = selectedItem
      ? [
          {
            name: selectedItem.title,
            request: buildPostmanRequest(selectedItem, buildRequestSpec(selectedItem, catalog.base_url), catalog.base_url),
            response: [],
          },
        ]
      : catalog.services.map((service) => ({
          name: service.title,
          item: service.items
            .filter((item) => item.kind === 'endpoint')
            .map((item) => ({
              name: item.title,
              request: buildPostmanRequest(item, buildRequestSpec(item, catalog.base_url), catalog.base_url),
              response: [],
            })),
        }));

    return {
      info: {
        name: selectedItem ? `IG E-Sign — ${selectedItem.title}` : 'IG E-Sign API',
        description: 'IG E-Sign REST API collection. Set `api_key` and `base_url` collection variables.',
        schema: 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
      },
      variable: [
        { key: 'base_url', value: catalog.base_url },
        { key: 'api_key', value: 'dsc_live_YOUR_KEY' },
      ],
      auth: {
        type: 'bearer',
        bearer: [{ key: 'token', value: '{{api_key}}', type: 'string' }],
      },
      item: collectionItems,
    };
  }

  function downloadJson(filename, data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  global.ApiDocsSnippets = {
    LANGS,
    buildRequestSpec,
    generateSnippet,
    buildPostmanCollection,
    downloadJson,
  };
})(window);
