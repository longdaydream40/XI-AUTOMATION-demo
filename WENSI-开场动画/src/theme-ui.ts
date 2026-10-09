// 上游 theme-ui.ts 是「亮色 ↔ 暗色」整套调色板插值 + 每帧写 CSS 变量。
// 这个独立版只有一套配色（黑场），不换主题，所以只留下 boot.ts 唯一用到的那个数：
//   boot.ts:178  this.el(".welcome-heading").style.color = themeAmount > .0001 ? ...
// 恒为 0 时它走另一支，标题墨色交给 黑场开场.css 里的 filter 处理。
export const themeAmount = 0;
