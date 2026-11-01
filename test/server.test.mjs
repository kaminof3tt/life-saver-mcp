import assert from "node:assert/strict";
import test from "node:test";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

import { loadConfig } from "../lib/config.js";
import { createServer } from "../lib/server.js";
import { createService } from "../lib/service.js";

/** 起一对内存 transport，拿一个已经握手完的客户端。 */
async function connect(env = {}) {
  const loaded = loadConfig({ env });
  const service = createService(loaded.config, loaded.secrets);
  const server = createServer(service, { name: "life-saver-mcp", version: "0.0.1" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  const client = new Client({ name: "test-client", version: "0.0.1" }, { capabilities: {} });
  await client.connect(clientTransport);
  return { client, server, service };
}

/** 取出文本内容。 */
function textOf(result) {
  return result.content.filter((block) => block.type === "text").map((block) => block.text).join("\n");
}

test("tools/list 报出六个工具，每个都有 JSON Schema 与必填项", async () => {
  const { client, server, service } = await connect();
  const listed = await client.listTools();
  assert.equal(listed.tools.length, 6);
  assert.deepEqual(
    listed.tools.map((tool) => tool.name).sort(),
    ["zentao_bug_op", "zentao_read", "zentao_search", "zentao_status", "zentao_task_op", "zentao_workhours"],
  );
  for (const tool of listed.tools) {
    assert.equal(typeof tool.description, "string");
    assert.ok(tool.description.length > 10, `${tool.name} 的描述太短`);
    assert.equal(tool.inputSchema.type, "object");
    assert.equal(tool.inputSchema.additionalProperties, false);
  }
  const read = listed.tools.find((tool) => tool.name === "zentao_read");
  assert.deepEqual(read.inputSchema.required, ["kind", "id"]);
  assert.equal(read.inputSchema.properties.kind.type, "string");
  assert.ok(Array.isArray(read.inputSchema.properties.kind.enum));
  const status = listed.tools.find((tool) => tool.name === "zentao_status");
  assert.deepEqual(status.inputSchema.required, []);
  await service.dispose();
  await server.close();
});

test("未知工具回 isError，并列出可用名字", async () => {
  const { client, service, server } = await connect();
  const result = await client.callTool({ name: "zentao_not_a_tool", arguments: {} });
  assert.equal(result.isError, true);
  assert.match(textOf(result), /没有名为 zentao_not_a_tool 的工具/);
  assert.match(textOf(result), /zentao_read/);
  await service.dispose();
  await server.close();
});

test("参数不合法时带回错误码，而不是崩掉连接", async () => {
  const { client, service, server } = await connect();
  const result = await client.callTool({ name: "zentao_read", arguments: { kind: "task" } });
  assert.equal(result.isError, true);
  assert.match(textOf(result), /\[bad-args\]/);
  await service.dispose();
  await server.close();
});

test("id 认不出编号时给出格式提示", async () => {
  const { client, service, server } = await connect();
  const result = await client.callTool({ name: "zentao_read", arguments: { kind: "task", id: "看这个任务" } });
  assert.equal(result.isError, true);
  assert.match(textOf(result), /没从 id 里认出编号/);
  await service.dispose();
  await server.close();
});

test("直接粘禅道链接也能读（链接里的类型优先）", async () => {
  const { client, service, server } = await connect();
  const result = await client.callTool({
    name: "zentao_read",
    arguments: { id: "http://zentao.example.com/index.php?m=task&f=view&taskID=1875" },
  });
  // 没配通道，所以这里只验证「链接被解析成 task#1875 后才去取数」。
  assert.equal(result.isError, true);
  assert.match(textOf(result), /task#1875/);
  await service.dispose();
  await server.close();
});

test("没配任何通道时，读正文给出可执行的排查提示", async () => {
  const { client, service, server } = await connect();
  const result = await client.callTool({ name: "zentao_read", arguments: { kind: "task", id: 1875 } });
  assert.equal(result.isError, true);
  const text = textOf(result);
  assert.match(text, /\[[a-z-]+\]/);
  assert.ok(text.length > 20);
  await service.dispose();
  await server.close();
});

test("zentao_status 在没有配置的机器上也能出报告", async () => {
  const { client, service, server } = await connect();
  const result = await client.callTool({ name: "zentao_status", arguments: {} });
  assert.equal(result.isError, undefined);
  const text = textOf(result);
  assert.match(text, /禅道|通道/);
  await service.dispose();
  await server.close();
});

test("写工具在写关闭时拒绝执行", async () => {
  const { client, service, server } = await connect({ ZENTAO_WRITE_ENABLED: "0" });
  const result = await client.callTool({
    name: "zentao_task_op",
    arguments: { id: 1875, action: "start", left: 4 },
  });
  assert.equal(result.isError, true);
  assert.match(textOf(result), /write-disabled|写/);
  await service.dispose();
  await server.close();
});
