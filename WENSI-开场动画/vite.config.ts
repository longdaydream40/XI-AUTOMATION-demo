import { defineConfig } from "vite";

export default defineConfig({
  // 上游用 __RHINE_NOVECENTO__ 决定逐字排版走授权字体还是作者画的字形。
  // 这个独立版没有 Novecento 授权 kit，恒为 false —— 也就是走上游的默认分支。
  define: { __RHINE_NOVECENTO__: "false" },
});
