/**
 * MCP 侧的配置来源：环境变量 + 可选 JSON 文件。
 *
 * 插件那边配置存在 profile 的 cordis.patch.yml 里、密码存在凭据中心；
 * MCP 服务器没有宿主，所以一切从环境变量来，密码同样只走环境变量
 * （`ZENTAO_PASSWORD` / `ZENTAO_DB_PASSWORD` / `ZENTAO_SFTP_PASSWORD`）。
 *
 * 优先级：命令行 `--config <file>` 里的值 < 环境变量。密码只认环境变量。
 * 这样「把站点写进 client 配置、把密码写进 shell 环境」是最自然的用法。
 */

import { readFileSync } from "node:fs";

import {
  Config,
  LifeSaverError,
  readSecretsFromEnv,
  unwrapConfig,
  type LifeSaverConfig,
  type Secrets,
} from "life-saver-core";

/** 读一次配置的结果，附带「这些值是从哪来的」用于排查。 */
export interface LoadedConfig {
  readonly config: LifeSaverConfig;
  readonly secrets: Secrets;
  readonly sources: readonly string[];
}

/** 环境变量名。SCREAMING_SNAKE，和 README 表格一一对应。 */
export const ENV = {
  mode: "ZENTAO_MODE",
  baseUrl: "ZENTAO_BASE_URL",
  account: "ZENTAO_ACCOUNT",
  skin: "ZENTAO_SKIN",
  httpTimeoutMs: "ZENTAO_HTTP_TIMEOUT_MS",
  discoveryEnabled: "ZENTAO_DISCOVERY",
  discoveryTtlMs: "ZENTAO_DISCOVERY_TTL_MS",
  dbHost: "ZENTAO_DB_HOST",
  dbPort: "ZENTAO_DB_PORT",
  dbName: "ZENTAO_DB_NAME",
  dbUser: "ZENTAO_DB_USER",
  dbPrefix: "ZENTAO_DB_PREFIX",
  dbLimit: "ZENTAO_DB_CONNECTION_LIMIT",
  sftpHost: "ZENTAO_SFTP_HOST",
  sftpPort: "ZENTAO_SFTP_PORT",
  sftpUser: "ZENTAO_SFTP_USER",
  sftpUploadBase: "ZENTAO_SFTP_UPLOAD_BASE",
  sftpPrivateKeyPath: "ZENTAO_SFTP_PRIVATE_KEY",
  writeEnabled: "ZENTAO_WRITE_ENABLED",
  writeMode: "ZENTAO_WRITE_MODE",
  writeAllowOthers: "ZENTAO_WRITE_ALLOW_OTHERS",
  outputDir: "ZENTAO_OUTPUT_DIR",
  targets: "ZENTAO_TARGETS",
  maxAttachments: "ZENTAO_MAX_ATTACHMENTS",
  maxAttachmentBytes: "ZENTAO_MAX_ATTACHMENT_BYTES",
  maxRelated: "ZENTAO_MAX_RELATED",
} as const;

type Raw = Record<string, unknown>;

/** 环境变量里的布尔：1/true/yes/on 为真，0/false/no/off 为假，其余按无效处理。 */
function boolOf(value: string | undefined): boolean | undefined {
  if (value === undefined) return undefined;
  const text = value.trim().toLowerCase();
  if (text === "") return undefined;
  if (["1", "true", "yes", "y", "on"].includes(text)) return true;
  if (["0", "false", "no", "n", "off"].includes(text)) return false;
  throw new LifeSaverError("bad-config", `环境变量取值不是布尔：${value}`);
}

/** 环境变量里的数字：非数字直接报错，别让它悄悄变成 NaN 传到查询里。 */
function numOf(name: string, value: string | undefined): number | undefined {
  if (value === undefined) return undefined;
  const text = value.trim();
  if (text === "") return undefined;
  const parsed = Number(text);
  if (!Number.isFinite(parsed)) throw new LifeSaverError("bad-config", `环境变量 ${name} 不是数字：${value}`);
  return parsed;
}

/** 环境变量里的字符串：空串视为没填（和设置页留空的语义一致）。 */
function textOf(value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  const text = value.trim();
  return text === "" ? undefined : text;
}

/** 按需塞值，避免把 undefined 写进 schema 触发「类型不符」。 */
function put(target: Raw, key: string, value: unknown): void {
  if (value !== undefined) target[key] = value;
}

function group(target: Raw, key: string): Raw {
  const existing = target[key];
  if (existing !== undefined && typeof existing === "object" && existing !== null) return existing as Raw;
  const created: Raw = {};
  target[key] = created;
  return created;
}

/** 环境变量 → schema 的嵌套形状。 */
export function configFromEnv(env: NodeJS.ProcessEnv): Raw {
  const raw: Raw = {};
  put(raw, "mode", textOf(env[ENV.mode]));
  put(raw, "targets", textOf(env[ENV.targets]));

  const http = group(raw, "http");
  put(http, "baseUrl", textOf(env[ENV.baseUrl]));
  put(http, "account", textOf(env[ENV.account]));
  put(http, "skin", textOf(env[ENV.skin]));
  put(http, "timeoutMs", numOf(ENV.httpTimeoutMs, env[ENV.httpTimeoutMs]));

  const db = group(raw, "db");
  put(db, "host", textOf(env[ENV.dbHost]));
  put(db, "port", numOf(ENV.dbPort, env[ENV.dbPort]));
  put(db, "database", textOf(env[ENV.dbName]));
  put(db, "user", textOf(env[ENV.dbUser]));
  put(db, "prefix", textOf(env[ENV.dbPrefix]));
  put(db, "connectionLimit", numOf(ENV.dbLimit, env[ENV.dbLimit]));

  const sftp = group(raw, "sftp");
  put(sftp, "host", textOf(env[ENV.sftpHost]));
  put(sftp, "port", numOf(ENV.sftpPort, env[ENV.sftpPort]));
  put(sftp, "user", textOf(env[ENV.sftpUser]));
  put(sftp, "uploadBase", textOf(env[ENV.sftpUploadBase]));
  put(sftp, "privateKeyPath", textOf(env[ENV.sftpPrivateKeyPath]));

  const write = group(raw, "write");
  put(write, "enabled", boolOf(env[ENV.writeEnabled]));
  put(write, "mode", textOf(env[ENV.writeMode]));
  put(write, "allowOthers", boolOf(env[ENV.writeAllowOthers]));

  const discovery = group(raw, "discovery");
  put(discovery, "enabled", boolOf(env[ENV.discoveryEnabled]));
  put(discovery, "ttlMs", numOf(ENV.discoveryTtlMs, env[ENV.discoveryTtlMs]));

  const limits = group(raw, "limits");
  put(limits, "maxAttachments", numOf(ENV.maxAttachments, env[ENV.maxAttachments]));
  put(limits, "maxAttachmentBytes", numOf(ENV.maxAttachmentBytes, env[ENV.maxAttachmentBytes]));
  put(limits, "maxRelated", numOf(ENV.maxRelated, env[ENV.maxRelated]));

  const output = group(raw, "output");
  put(output, "dir", textOf(env[ENV.outputDir]));

  return raw;
}

/**
 * 把配置文件摊平成 core 认识的嵌套形状。
 *
 * 兼容两种写法：
 *   1. 本项目的形状：`{ baseUrl, account, db: { host, ... }, write: { enabled } }`；
 *   2. 旧 life-saver-mcp 的 `handlers.zentao.url`（只取地址，其余历史字段忽略）。
 */
export function configFromFile(path: string): Raw {
  const text = readFileSync(path, "utf8");
  const parsed: unknown = JSON.parse(text);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new LifeSaverError("bad-config", `配置文件不是 JSON 对象：${path}`);
  }
  const input = parsed as Raw;
  const legacy = (input.handlers as Raw | undefined)?.zentao as Raw | undefined;
  const raw: Raw = { ...input };
  delete raw.handlers;
  delete raw.providers;
  if (textOf(typeof legacy?.url === "string" ? legacy.url : undefined) !== undefined) {
    const http = group(raw, "http");
    put(http, "baseUrl", legacy?.url);
  }
  return raw;
}

/** 递归合并：file 打底，env 覆盖。数组/标量直接替换，不做拼接。 */
function merge(base: Raw, override: Raw): Raw {
  const result: Raw = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const previous = result[key];
    if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      previous !== null &&
      typeof previous === "object" &&
      !Array.isArray(previous)
    ) {
      result[key] = merge(previous as Raw, value as Raw);
    } else {
      result[key] = value;
    }
  }
  return result;
}

/** 去掉合并后留下的空对象，免得 schemastery 把它们当成「显式给了一堆空值」。 */
function prune(raw: Raw): Raw {
  const result: Raw = {};
  for (const [key, value] of Object.entries(raw)) {
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      const nested = prune(value as Raw);
      if (Object.keys(nested).length > 0) result[key] = nested;
      continue;
    }
    if (value !== undefined) result[key] = value;
  }
  return result;
}

/** 读一次完整配置。 */
export function loadConfig(options: { configPath?: string; env?: NodeJS.ProcessEnv } = {}): LoadedConfig {
  const env = options.env ?? process.env;
  const sources: string[] = [];
  let raw: Raw = {};
  if (options.configPath !== undefined) {
    raw = configFromFile(options.configPath);
    sources.push(`配置文件 ${options.configPath}`);
  }
  const fromEnv = prune(configFromEnv(env));
  if (Object.keys(fromEnv).length > 0) {
    sources.push("环境变量");
    raw = merge(raw, fromEnv);
  }

  let config: LifeSaverConfig;
  try {
    config = unwrapConfig(new Config(raw)) as LifeSaverConfig;
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new LifeSaverError("bad-config", `配置不合法：${detail}`);
  }

  const secrets = readSecretsFromEnv(env);
  if (secrets.httpPassword !== "" || secrets.dbPassword !== "" || secrets.sftpPassword !== "") {
    sources.push("密码来自环境变量");
  }
  return { config, secrets, sources };
}

/** `--check` 打印的摘要：只说是/否，绝不回显密码本身。 */
export function describeConfig(loaded: LoadedConfig): string {
  const { config, secrets } = loaded;
  const yesNo = (value: boolean): string => (value ? "已配置" : "缺");
  const http = config.http;
  const db = config.db;
  const sftp = config.sftp;
  return [
    `取数通道      ${config.mode}`,
    `禅道地址      ${http.baseUrl === "" ? "（未配置）" : http.baseUrl}`,
    `HTTP 账号     ${http.account === "" ? "（未配置）" : http.account} · 密码 ${yesNo(secrets.httpPassword !== "")}`,
    `只读库        ${db.host === "" ? "（未配置）" : `${db.host}:${db.port}/${db.database}（前缀 ${db.prefix}）`} · 密码 ${yesNo(secrets.dbPassword !== "")}`,
    `附件 SFTP     ${sftp.host === "" ? "（未配置）" : `${sftp.host}:${sftp.port}`} · 上传目录 ${sftp.uploadBase === "" ? "（未配置）" : sftp.uploadBase} · 密码 ${yesNo(secrets.sftpPassword !== "")}`,
    `写操作        ${config.write.enabled ? `开启 · 走 ${config.write.mode}` : "关闭（只读）"}${config.write.allowOthers ? " · 允许改别人名下的" : ""}`,
    `落盘目录      ${config.output.dir === "" ? "（默认：当前工作目录/zentao-extract）" : config.output.dir}`,
    `配置来源      ${loaded.sources.length === 0 ? "（全默认值）" : loaded.sources.join(" + ")}`,
  ].join("\n");
}
