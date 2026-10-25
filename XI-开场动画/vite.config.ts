import { defineConfig } from "vite";

export default defineConfig({
  // 产物由 /home/xuan/设计/拼接.html 嵌入，支持任意 HTTP 子路径。
  // 所以资源一律走相对路径。默认的 "/assets/..." 在 http://host:9174/拼接.html 里
  // 会被解析成站点根，直接 404。
  base: "./",
  // 上游用 __RHINE_NOVECENTO__ 决定逐字排版走授权字体还是作者画的字形。
  // 这个独立版没有 Novecento 授权 kit，恒为 false —— 也就是走上游的默认分支。
  define: { __RHINE_NOVECENTO__: "false" },
});
