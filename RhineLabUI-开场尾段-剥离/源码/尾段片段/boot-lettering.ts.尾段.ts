// 尾段片段：src/boot-lettering.ts
// 起止 = 上游原文件行号；上游 /home/xuan/设计/RhineLabUI（HEAD 12cc5e4）
// 尾段窗口 f457–f673（原片 18.28–26.92 s）

──── src/boot-lettering.ts:9-32  · 依赖（尾段之前就跑完 / 尾段每帧都在用） loadBootWebfonts：字体加载门（字体缺失就退回作者画的字形）
export async function loadBootWebfonts() {
  if (!__RHINE_NOVECENTO__) return false;
  const faces = ["Normal", "DemiBold", "Bold"].map(weight => new FontFace(
    `Rhine Novecento ${weight}`,
    `url("${assetUrl(`fonts/novecento/webFonts/NovecentoSansWide${weight}/font.woff2`)}") format("woff2")`,
    { weight: "400", style: "normal", display: "swap" },
  ));
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      Promise.all(faces.map(face => face.load())),
      new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error("Novecento load timeout")), 8000); }),
    ]);
    faces.forEach(face => document.fonts.add(face));
    letterings.forEach(lettering => lettering.useWebfonts());
    return true;
  } catch (error) {
    console.warn("Novecento kit unavailable; retaining authored phrase graphics.", error);
    return false;
  } finally { clearTimeout(timeout); }
}

type PhraseKey = keyof typeof artwork;
const ns = "http://www.w3.org/2000/svg";

──── src/boot-lettering.ts:35-78  · 依赖（尾段之前就跑完 / 尾段每帧都在用） 构造函数：把 art.json 里的字形格子先建好，setText 才有东西可显隐
export class BootLettering {
  private label = document.createElement("span");
  private phrases: {
    text: string;
    node: HTMLSpanElement;
    letters: HTMLSpanElement[];
    weight: string;
  }[];
  private value: string | undefined;

  constructor(private host: HTMLElement, keys: PhraseKey[]) {
    this.label.className = "boot-phrase-label";
    this.phrases = keys.map((key) => {
      const art = artwork[key];
      const node = document.createElement("span");
      node.className = "boot-phrase";
      node.dataset.phrase = key;
      node.dataset.weight = art.weight;
      node.setAttribute("aria-hidden", "true");
      node.hidden = true;
      const letters = art.letters.map((letter) => {
        const cell = document.createElement("span");
        cell.className = "boot-phrase-letter";
        cell.style.width = `${letter.width}em`;
        if (letter.path) {
          const svg = document.createElementNS(ns, "svg");
          svg.classList.add("boot-letter-art");
          svg.setAttribute("viewBox", `0 0 ${letter.width * art.units} ${art.units}`);
          svg.setAttribute("focusable", "false");
          const path = document.createElementNS(ns, "path");
          path.setAttribute("d", letter.path);
          svg.append(path);
          cell.append(svg);
        }
        node.append(cell);
        return cell;
      });
      return { text: art.text, node, letters, weight: art.weight };
    });
    host.classList.add("has-boot-lettering");
    host.replaceChildren(this.label, ...this.phrases.map((p) => p.node));
    host.dataset.letteringRenderer = "artwork";
    letterings.add(this);
  }

──── src/boot-lettering.ts:80-92  · 依赖（尾段之前就跑完 / 尾段每帧都在用） useWebfonts：字体就绪后换掉字形来源，格子与时间轴不变
  useWebfonts() {
    // Retain the measured cells and the reveal timeline. Only the glyph source
    // changes: actual WOFF2 text replaces each pre-authored SVG drawing.
    for (const phrase of this.phrases) {
      phrase.node.style.setProperty("--boot-webfont-family", `"Rhine Novecento ${phrase.weight}"`);
      phrase.letters.forEach((letter, i) => {
        letter.replaceChildren();
        letter.dataset.letter = phrase.text[i];
        letter.classList.add("boot-font-letter");
      });
    }
    this.host.dataset.letteringRenderer = "webfont";
  }

──── src/boot-lettering.ts:94-110  ★ 尾段生效 ★setText：尾段唯一入口。逐帧比对同值直接 return，值一变压 phrase 与字母格子
  setText(value: string) {
    if (this.value === value) return;
    this.value = value;
    this.label.textContent = value;
    const active = value ? this.phrases.find((p) => p.text.startsWith(value)) : undefined;
    // A new, unauthored phrase remains readable until its artwork is exported.
    this.host.classList.toggle("boot-lettering-fallback", Boolean(value && !active));
    for (const phrase of this.phrases) {
      const visible = phrase === active;
      if (phrase.node.hidden === visible) phrase.node.hidden = !visible;
      if (!visible) continue;
      phrase.letters.forEach((letter, i) => {
        const hidden = i >= value.length;
        if (letter.hidden !== hidden) letter.hidden = hidden;
      });
    }
  }
