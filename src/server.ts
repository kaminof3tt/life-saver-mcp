/**
 * MCP 服务器装配：把六个工具挂到 `tools/list` / `tools/call` 上。
 *
 * 刻意用低层 `Server` 而不是 `McpServer`：`McpServer` 的 `registerTool` 需要 zod schema，
 * 而我们的参数规格在 core 里本来就是 JSON Schema（`jsonSchemaOf`），再翻一遍 zod
 * 只会多一处必须同步维护的副本。
 *
 * 错误处理：业务错误（`LifeSaverError`）回 `isError: true` 并把 code/hint 带进正文，
 * 让模型能自己纠（比如参数错了、通道没配）。协议层错误才交给 SDK 抛。
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { LifeSaverError, jsonSchemaOf, messageOf, type LifeSaverService } from "life-saver-core";

import { TOOLS, toolNames, toolNamed } from "./tools.js";

/** 服务器自报的名字与版本（版本从 package.json 来，见 index.ts）。 */
export interface ServerIdentity {
  readonly name: string;
  readonly version: string;
}

/** 把业务错误排版成模型能直接读懂的一段话。 */
export function formatError(error: unknown): string {
  if (error instanceof LifeSaverError) {
    const head = `[${error.code}] ${error.message}`;
    return error.hint === undefined || error.hint === "" ? head : `${head}\n\n${error.hint}`;
  }
  return `[internal] ${messageOf(error)}`;
}

/** 装配一个服务器实例（不连 transport，测试可以直接塞内存 transport）。 */
export function createServer(service: LifeSaverService, identity: ServerIdentity): Server {
  const server = new Server(identity, { capabilities: { tools: {} } });

  server.setRequestHandler(ListToolsRequestSchema, () => ({
    tools: TOOLS.map((tool) => ({
      name: tool.spec.name,
      description: tool.spec.description,
      inputSchema: jsonSchemaOf(tool.spec),
    })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    const tool = toolNamed(name);
    if (tool === undefined) {
      return {
        content: [{ type: "text" as const, text: `没有名为 ${name} 的工具。可用：${toolNames().join("、")}` }],
        isError: true,
      };
    }
    try {
      const value = await tool.run(service, args ?? {}, { cwd: process.cwd() });
      return { content: [{ type: "text" as const, text: tool.render(value) }] };
    } catch (error) {
      return { content: [{ type: "text" as const, text: formatError(error) }], isError: true };
    }
  });

  return server;
}
