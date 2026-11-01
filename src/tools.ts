/**
 * 六个工具的登记表。
 *
 * 每个工具的三件事都在 core 里：`spec`（名字/描述/参数）、`run`（执行）、`render`（排版）。
 * 这里只把三件套绑成一行。加工具 = 在 core 加一个 spec+runner+renderer，再在这里加一行。
 *
 * 用低层 `Server` 而不是 `McpServer`：参数 schema 直接给 JSON Schema
 * （`jsonSchemaOf`），不必为了走 zod 再把规格翻译一遍。
 */

import {
  BUGOP_SPEC,
  READ_SPEC,
  SEARCH_SPEC,
  STATUS_SPEC,
  TASKOP_SPEC,
  WORKHOURS_SPEC,
  renderBugOpOutput,
  renderReadOutput,
  renderSearchOutput,
  renderStatusOutput,
  renderTaskOpOutput,
  renderWorkhoursOutput,
  runBugOpTool,
  runReadTool,
  runSearchTool,
  runStatusTool,
  runTaskOpTool,
  runWorkhoursTool,
  type LifeSaverService,
  type ToolRunContext,
  type ToolSpec,
} from "life-saver-core";

/** 一个工具在 MCP 侧的完整形态。 */
export interface McpTool {
  readonly spec: ToolSpec;
  readonly run: (service: LifeSaverService, args: unknown, context: ToolRunContext) => Promise<unknown>;
  readonly render: (value: unknown) => string;
}

/**
 * 绑定一个工具。
 *
 * `run` 的返回类型和 `render` 的入参类型在 core 里是同一条链（runner 的返回即 renderer 的入参），
 * 但登记表要抹平成 `unknown` 才能放进同一个数组。这个 `as T` 只在函数边界发生一次，
 * 一旦 core 改了返回形状，`run` 那一侧的类型推导会立刻报错。
 */
function bind<T>(
  spec: ToolSpec,
  run: (service: LifeSaverService, args: unknown, context: ToolRunContext) => Promise<T>,
  render: (value: T) => string,
): McpTool {
  return { spec, run: (service, args, context) => run(service, args, context), render: (value) => render(value as T) };
}

export const TOOLS: readonly McpTool[] = [
  bind(READ_SPEC, runReadTool, renderReadOutput),
  bind(SEARCH_SPEC, runSearchTool, renderSearchOutput),
  bind(STATUS_SPEC, (service, _args, context) => runStatusTool(service, context), renderStatusOutput),
  bind(WORKHOURS_SPEC, runWorkhoursTool, renderWorkhoursOutput),
  bind(TASKOP_SPEC, runTaskOpTool, renderTaskOpOutput),
  bind(BUGOP_SPEC, runBugOpTool, renderBugOpOutput),
];

/** 按名字找工具。 */
export function toolNamed(name: string): McpTool | undefined {
  return TOOLS.find((tool) => tool.spec.name === name);
}

/** 工具名清单，报错时用。 */
export function toolNames(): string[] {
  return TOOLS.map((tool) => tool.spec.name);
}
