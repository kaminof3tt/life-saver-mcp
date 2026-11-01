#!/usr/bin/env node
/**
 * life-saver-mcp 入口：stdio 上的 MCP 服务器。
 *
 * stdout 是协议通道，任何日志都只能走 stderr——所以这里唯一会写到 stdout 的情况
 * 是用户显式要 `--help` / `--version` / `--check`，写完就退出，不连 transport。
 */

import { readFileSync } from "node:fs";

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { describeConfig, loadConfig } from "./config.js";
import { createServer } from "./server.js";
import { createService } from "./service.js";

interface Args {
  readonly help: boolean;
  readonly version: boolean;
  readonly check: boolean;
  readonly configPath?: string;
}

const USAGE = `life-saver-mcp —— 禅道（ZenTao）MCP 服务器

用法
  life-saver-mcp                     # 在 stdio 上开服务器（给 MCP 客户端用）
  life-saver-mcp --check             # 只打印解析出来的配置摘要，不连禅道
  life-saver-mcp --config <file>     # 从 JSON 文件补充配置（环境变量优先）
  life-saver-mcp --version
  life-saver-mcp --help

配置
  站点：ZENTAO_BASE_URL、ZENTAO_ACCOUNT
  只读库：ZENTAO_DB_HOST、ZENTAO_DB_PORT、ZENTAO_DB_NAME、ZENTAO_DB_USER、ZENTAO_DB_PREFIX
  附件 SFTP：ZENTAO_SFTP_HOST、ZENTAO_SFTP_PORT、ZENTAO_SFTP_USER、ZENTAO_SFTP_UPLOAD_BASE
  密码：ZENTAO_PASSWORD、ZENTAO_DB_PASSWORD、ZENTAO_SFTP_PASSWORD（只从环境变量读）
  其它：ZENTAO_MODE=auto|db|http、ZENTAO_WRITE_ENABLED、ZENTAO_WRITE_MODE、ZENTAO_OUTPUT_DIR

  完整清单见 README。密码不会回显，--check 只说「已配置 / 缺」。
`;

function parseArgs(argv: readonly string[]): Args {
  const rest = argv.slice(2);
  let configPath: string | undefined;
  for (let index = 0; index < rest.length; index += 1) {
    const current = rest[index] as string;
    if (current === "--config" || current === "-c") {
      const next = rest[index + 1];
      if (next === undefined) throw new Error("--config 后面要跟一个文件路径");
      configPath = next;
      index += 1;
      continue;
    }
    if (current.startsWith("--config=")) {
      configPath = current.slice("--config=".length);
    }
  }
  return {
    help: rest.includes("--help") || rest.includes("-h"),
    version: rest.includes("--version") || rest.includes("-v"),
    check: rest.includes("--check"),
    configPath,
  };
}

/** 版本从包自带的 package.json 读，避免两处手写。 */
function versionOf(): string {
  const url = new URL("../package.json", import.meta.url);
  const parsed = JSON.parse(readFileSync(url, "utf8")) as { version?: unknown };
  return typeof parsed.version === "string" ? parsed.version : "0.0.0";
}

async function main(): Promise<void> {
  let args: Args;
  try {
    args = parseArgs(process.argv);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n\n${USAGE}`);
    process.exitCode = 2;
    return;
  }

  if (args.help) {
    process.stdout.write(USAGE);
    return;
  }
  if (args.version) {
    process.stdout.write(`${versionOf()}\n`);
    return;
  }

  let loaded;
  try {
    loaded = loadConfig({ configPath: args.configPath });
  } catch (error) {
    process.stderr.write(`配置有误：${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
    return;
  }

  if (args.check) {
    process.stdout.write(`${describeConfig(loaded)}\n`);
    return;
  }

  const service = createService(loaded.config, loaded.secrets);
  const server = createServer(service, { name: "life-saver-mcp", version: versionOf() });

  const shutdown = (): void => {
    void service.dispose().finally(() => process.exit(0));
  };
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);

  await server.connect(new StdioServerTransport());
  process.stderr.write(`life-saver-mcp ${versionOf()} 已就绪（${loaded.config.mode}）\n`);
}

await main();
