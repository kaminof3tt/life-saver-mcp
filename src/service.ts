/**
 * 把读到的配置包成 core 的 service。
 *
 * `ServiceDeps` 只要求两个回调：怎么取配置、怎么取密码。MCP 这边两者都是常量
 * （进程启动时读一次，之后不变），所以直接闭包捕获——不需要宿主那套 ref/设置页。
 */

import { LifeSaverService, type LifeSaverConfig, type Secrets } from "life-saver-core";

/** 用一份固定的配置与密码建 service。 */
export function createService(config: LifeSaverConfig, secrets: Secrets): LifeSaverService {
  return new LifeSaverService({
    config: () => config,
    secrets: async () => secrets,
  });
}
