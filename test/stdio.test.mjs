import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const entry = fileURLToPath(new URL("../lib/index.js", import.meta.url));

/** 像真实客户端那样把进程拉起来，走一遍 stdio 握手。 */
async function spawnClient(env = {}) {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [entry],
    env: { PATH: process.env.PATH ?? "", ...env },
    stderr: "pipe",
  });
  const client = new Client({ name: "stdio-test", version: "0.0.1" }, { capabilities: {} });
  await client.connect(transport);
  return client;
}

test("stdio 上能握手、能列工具、能调用", async () => {
  const client = await spawnClient();
  try {
    const info = client.getServerVersion();
    assert.equal(info?.name, "life-saver-mcp");
    assert.equal(info?.version, "0.0.1");

    const listed = await client.listTools();
    assert.equal(listed.tools.length, 6);

    const status = await client.callTool({ name: "zentao_status", arguments: {} });
    assert.equal(status.isError, undefined);
    const text = status.content.find((block) => block.type === "text")?.text ?? "";
    assert.match(text, /通道|禅道/);
  } finally {
    await client.close();
  }
});

test("stdlib 出错也走 isError，进程不退出", async () => {
  const client = await spawnClient();
  try {
    const bad = await client.callTool({ name: "zentao_search", arguments: {} });
    assert.equal(bad.isError, true);
    const again = await client.listTools();
    assert.equal(again.tools.length, 6);
  } finally {
    await client.close();
  }
});
