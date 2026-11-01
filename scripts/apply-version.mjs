#!/usr/bin/env node
// 把版本号写进 package.json 的 version 与 dependencies["life-saver-core"]。
// 发布流水线里用的是「发的时候现改、不提交」的方式，所以这个脚本只动文件、不碰 git。
//
//   node scripts/apply-version.mjs 0.1.0
import { readFileSync, writeFileSync } from "node:fs";

const version = (process.argv[2] || "").trim();
if (!/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(version)) {
  console.error(`版本号不合法：${version || "(空)"}；应形如 0.1.0`);
  process.exit(1);
}

const path = new URL("../package.json", import.meta.url);
const manifest = JSON.parse(readFileSync(path, "utf8"));

manifest.version = version;
manifest.dependencies = { ...manifest.dependencies, "life-saver-core": version };

writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`package.json → version ${version}，依赖 life-saver-core ${version}`);
