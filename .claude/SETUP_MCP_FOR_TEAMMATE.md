# Setup MCP Server for Teammate

Share this guide with your teammate to enable the `prompt-validator` MCP server in their Claude Code environment.

---

## Prerequisites

- Claude Code installed (Desktop app)
- Access to the prompt validator repository (or just this guide)
- ~5 minutes setup time

---

## Step 1: Create `.claude` Directory (if not exists)

On your machine, locate your `.claude` directory:

**Windows:**
```
C:\Users\{YourUsername}\.claude\
```

**macOS/Linux:**
```
~/.claude/
```

If it doesn't exist, create it.

---

## Step 2: Add the MCP Proxy File

**Create a new file:** `mcp-proxy.js` in your `.claude/` directory

**Copy this content exactly:**

```javascript
// mcp-proxy.js — MCP stdio-to-HTTP proxy (no dependencies)
// Bridges Claude Desktop (stdio) to Prompt Validator MCP HTTP endpoint.
const https = require('https');
const readline = require('readline');

const MCP_URL = 'https://promptvalidatorcompleterepo.vercel.app/mcp';
const url = new URL(MCP_URL);

const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on('line', (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;

  let msg;
  try { msg = JSON.parse(trimmed); } catch { return; }

  const body = JSON.stringify(msg);
  const options = {
    hostname: url.hostname,
    path: url.pathname,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(body),
    },
    timeout: 30000,
  };

  const req = https.request(options, (res) => {
    let data = '';
    res.on('data', (chunk) => { data += chunk; });
    res.on('end', () => {
      if (res.statusCode === 202 || !data.trim()) return; // notification ACK
      process.stdout.write(data.trim() + '\n');
    });
  });

  req.on('timeout', () => {
    req.destroy();
    if (msg.id !== undefined) {
      process.stdout.write(JSON.stringify({
        jsonrpc: '2.0', id: msg.id,
        error: { code: -32001, message: 'Request timeout after 30s' }
      }) + '\n');
    }
  });

  req.on('error', (err) => {
    if (msg.id !== undefined) {
      process.stdout.write(JSON.stringify({
        jsonrpc: '2.0', id: msg.id,
        error: { code: -32603, message: err.message }
      }) + '\n');
    }
  });

  req.write(body);
  req.end();
});
```

**Save file:** `C:\Users\{YourUsername}\.claude\mcp-proxy.js`

---

## Step 3: Register MCP Server in Claude Code

### Open Claude Code Settings:

1. Click **Settings** (gear icon, bottom-left)
2. Click **Claude Code** in left sidebar
3. Scroll to **Local MCP servers**
4. Click **Edit Config**

### Add the MCP Server Entry:

In the config editor, add this entry:

```json
{
  "name": "prompt-validator",
  "command": "node",
  "args": ["C:/Users/{YourUsername}/.claude/mcp-proxy.js"]
}
```

**Replace `{YourUsername}` with your actual Windows username** (e.g., `john.smith`)

### Save and Restart

1. Click **Save**
2. Close and reopen Claude Code
3. Go back to **Settings → Claude Code → Local MCP servers**

You should see **`prompt-validator` with a blue "running" badge** ✅

---

## Step 4: Verify Tools Are Available

### Check the Connector:

1. Settings → **Connectors**
2. Find **prompt-validator** in the list
3. Confirm you see these 7 tools:
   - ✅ `validate_prompt`
   - ✅ `improve_prompt`
   - ✅ `list_personas`
   - ✅ `get_persona_details`
   - ✅ `query_history`
   - ✅ `get_analytics`
   - ✅ `save_validation`

All permissions should be set to **"Always allow"**

---

## Step 5: Test the Tools

### In any Claude conversation, try:

**Test 1 — List personas:**
```
Use the prompt-validator MCP server to list all available personas
```

**Test 2 — Validate a prompt:**
```
Validate this prompt using the prompt-validator: "Write a tutorial on Python async programming"
Using persona: product_manager
```

**Test 3 — Get analytics:**
```
Use the prompt-validator to fetch current analytics and tell me the total token usage
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **MCP server shows red X or "error"** | Check that `mcp-proxy.js` path is correct in config. Path must use forward slashes: `C:/Users/...` not `C:\Users\...` |
| **Timeout errors** | Vercel endpoint may be slow. Wait 10-15s and retry. If persistent, check internet connection. |
| **Tools not visible** | Restart Claude Code. Settings → Local MCP servers should show blue "running" badge. |
| **"Unknown tool" error** | Confirm all 7 tool names are visible in Connectors page. If missing, MCP server didn't start. |

---

## What the MCP Server Does

The `prompt-validator` MCP server exposes the full validator engine to Claude Code:

- **Backend:** Vercel serverless (Python FastAPI)
- **Protocol:** JSON-RPC 2.0 (Model Context Protocol)
- **Database:** MongoDB Atlas (or SQLite fallback)
- **LLM:** Anthropic Claude Sonnet 4.6

Your teammate can now:
- ✅ Validate prompts from Claude Code directly
- ✅ Query validation history
- ✅ Get token/cost analytics
- ✅ Improve prompts using AI
- ✅ Test all features without leaving Claude

---

## Share This With Your Teammate

**Provide them:**
1. This file (`SETUP_MCP_FOR_TEAMMATE.md`)
2. OR copy the steps above into a Slack/Teams message
3. Their Windows username (so they can customize the path)

**They should:**
1. Create `mcp-proxy.js` in their `.claude/` directory
2. Register it in Claude Code settings
3. Restart Claude Code
4. Test with one of the validation commands above

---

## Questions?

If setup fails:
1. Check that Node.js is installed: `node --version`
2. Verify path uses forward slashes: `C:/Users/...`
3. Restart Claude Code completely (close all windows)
4. Check Claude Code console for error messages (Settings → Developer → Show logs)

---

**Version:** 1.0 | **Date:** April 2026 | **MCP Endpoint:** `https://promptvalidatorcompleterepo.vercel.app/mcp`
