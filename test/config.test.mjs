import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";

const fixture = (name) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

import { configFromEnv, configFromFile, describeConfig, loadConfig } from "../lib/config.js";

const FULL_ENV = {
  ZENTAO_BASE_URL: "http://zentao.example.com/zentao",
  ZENTAO_ACCOUNT: "tester",
  ZENTAO_MODE: "http",
  ZENTAO_SKIN: "detail",
  ZENTAO_HTTP_TIMEOUT_MS: "12000",
  ZENTAO_DB_HOST: "10.0.0.9",
  ZENTAO_DB_PORT: "3306",
  ZENTAO_DB_NAME: "zentao4",
  ZENTAO_DB_USER: "reader",
  ZENTAO_DB_PREFIX: "zt_",
  ZENTAO_SFTP_HOST: "10.0.0.9",
  ZENTAO_SFTP_UPLOAD_BASE: "/opt/zentao/www/data/upload",
  ZENTAO_WRITE_ENABLED: "0",
  ZENTAO_OUTPUT_DIR: "D:/tmp/zentao",
  ZENTAO_PASSWORD: "p1",
  ZENTAO_DB_PASSWORD: "p2",
};

test("环境变量全部映射到配置的对应字段", () => {
  const raw = configFromEnv(FULL_ENV);
  assert.equal(raw.mode, "http");
  assert.equal(raw.http.baseUrl, "http://zentao.example.com/zentao");
  assert.equal(raw.http.account, "tester");
  assert.equal(raw.http.skin, "detail");
  assert.equal(raw.http.timeoutMs, 12000);
  assert.equal(raw.db.host, "10.0.0.9");
  assert.equal(raw.db.port, 3306);
  assert.equal(raw.db.database, "zentao4");
  assert.equal(raw.db.user, "reader");
  assert.equal(raw.sftp.uploadBase, "/opt/zentao/www/data/upload");
  assert.equal(raw.write.enabled, false);
  assert.equal(raw.output.dir, "D:/tmp/zentao");
});

test("留空的环境变量当作没填，不覆盖默认值", () => {
  const loaded = loadConfig({ env: { ZENTAO_BASE_URL: "   ", ZENTAO_DB_PORT: "" } });
  assert.equal(loaded.config.http.baseUrl, "");
  assert.equal(loaded.config.db.port, 3306);
  assert.equal(loaded.config.mode, "auto");
});

test("布尔只认常见的真假写法，其它一律报错", () => {
  assert.equal(configFromEnv({ ZENTAO_WRITE_ENABLED: "ON" }).write.enabled, true);
  assert.equal(configFromEnv({ ZENTAO_WRITE_ALLOW_OTHERS: "yes" }).write.allowOthers, true);
  assert.equal(configFromEnv({ ZENTAO_DISCOVERY: "off" }).discovery.enabled, false);
  assert.throws(() => configFromEnv({ ZENTAO_WRITE_ENABLED: "可能" }), /不是布尔/);
});

test("数字字段给非数字直接报错，不会变成 NaN", () => {
  assert.throws(() => configFromEnv({ ZENTAO_DB_PORT: "三千" }), /不是数字/);
});

test("密码只从环境变量来，readSecretsFromEnv 认得三个键", () => {
  const loaded = loadConfig({ env: FULL_ENV });
  assert.equal(loaded.secrets.httpPassword, "p1");
  assert.equal(loaded.secrets.dbPassword, "p2");
  assert.equal(loaded.secrets.sftpPassword, "");
  assert.ok(loaded.sources.includes("密码来自环境变量"));
});

test("环境变量盖过配置文件，文件里的其它字段留着", () => {
  const loaded = loadConfig({ configPath: fixture("site.json"), env: { ZENTAO_BASE_URL: "http://override.local" } });
  assert.equal(loaded.config.http.baseUrl, "http://override.local");
  assert.equal(loaded.config.db.host, "10.0.0.9");
  assert.ok(loaded.sources.some((item) => item.includes("配置文件")));
});

test("配置文件兼容旧 life-saver-mcp 的 handlers.zentao.url", () => {
  const raw = configFromFile(fixture("legacy.json"));
  assert.equal(raw.http.baseUrl, "http://legacy.example.com");
  assert.equal(raw.handlers, undefined);
  assert.equal(raw.providers, undefined);
});

test("--check 的摘要不出现密码明文", () => {
  const text = describeConfig(loadConfig({ env: FULL_ENV }));
  assert.match(text, /HTTP 账号/);
  assert.match(text, /密码 已配置/);
  assert.equal(text.includes("p1"), false);
  assert.equal(text.includes("p2"), false);
});

test("配置文件不是 JSON 对象时报配置错误", () => {
  assert.throws(() => configFromFile(fixture("array.json")), /不是 JSON 对象/);
});
