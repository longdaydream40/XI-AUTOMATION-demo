// 尾段片段：src/boot.ts
// 起止 = 上游原文件行号；上游 /home/xuan/设计/RhineLabUI（HEAD 12cc5e4）
// 尾段窗口 f457–f673（原片 18.28–26.92 s）

──── src/boot.ts:129-132  · 依赖（尾段之前就跑完 / 尾段每帧都在用） update 入口：同帧只算一次快照，写进 dataset.bootFrame
  update(time: number) {
    const s = bootMotion(time),
      t = s.t;
    this.stage.dataset.bootFrame = String(s.f);

──── src/boot.ts:133-137  · 前置（尾段窗口内已定型，不再变化） access-text / boot-logo 层（尾段里 logoOpacity 恒定，只有位移在写）
    this.accessLettering.setText(s.access);
    this.opacity(".access-text", s.accessOpacity);
    this.opacity(".boot-logo", s.logoOpacity);
    this.el(".boot-logo").style.transform =
      `translate(${s.logo.offsetX}px, 1px)`;

──── src/boot.ts:138-140  ★ 尾段生效 ★标志轮廓缺口。f457 时只剩 97.25% 实线，缺口绕行到 f486 才停
    this.contour.style.strokeDasharray = `${s.logo.length} ${1 - s.logo.length}`;
    this.contour.style.strokeDashoffset = String(-s.logo.start);
    this.contour.setAttribute("stroke-width", String(s.logo.strokeWidth));

──── src/boot.ts:141-158  · 前置（尾段窗口内已定型，不再变化） 字形文本节点 + 加减号（尾段恒定）
    // Preserve the SVG text node once each revealed letter is in place. Replacing
    // it every frame invalidates glyph rasterization under the moving HUD.
    if (this.letters.textContent !== s.logoLetters)
      this.letters.textContent = s.logoLetters;
    this.plus.style.opacity = this.minus.style.opacity =
      s.logo.symbolScale > 0 ? "1" : "0";
    this.plus.setAttribute(
      "transform",
      `translate(${s.logo.plusX} 70) rotate(${s.logo.plusAngle}) scale(${s.logo.symbolScale}) translate(-69 -70)`,
    );
    this.minus.setAttribute(
      "d",
      `M${-s.logo.minusWidth / 2} 0h${s.logo.minusWidth}`,
    );
    this.minus.setAttribute(
      "transform",
      `translate(${s.logo.minusX} 70) scale(${s.logo.symbolScale})`,
    );

──── src/boot.ts:159-160  ★ 尾段生效 ★auth-status 开关 + setText(s.auth)：f479/485/486 的缺字就从这一行进 DOM
    this.opacity(".auth-status", s.authOpacity);
    this.authLettering.setText(s.auth);

──── src/boot.ts:161-169  · 前置（尾段窗口内已定型，不再变化） brand 三行 / powered（尾段恒定）
    this.opacity(".brand", 1);
    this.el(".brand").style.transform = "none";
    this.brandLines.forEach((node, i) => {
      node.style.opacity = String(s.brand[i].opacity);
      node.style.transform = `translateX(${s.brand[i].x}px)`;
    });
    this.opacity(".powered", s.poweredLetters > 0);
    this.el(".powered").style.clipPath =
      `inset(0 ${100 * (1 - s.poweredLetters / 19)}% 0 0)`;

──── src/boot.ts:170-171  ★ 尾段生效 ★scan 层开关 + renderScan 调用。f487 之后这一行是整段扫描环的唯一入口
    this.opacity(".scan", s.scanVisible);
    if (s.scanVisible) this.renderScan(s);

──── src/boot.ts:172-196  ★ 尾段生效 ★welcome 组 + 白场 + 底纹 + return。f569–f673 全部动画都在这一段里
    this.opacity(".welcome", s.welcomeVisible ? s.welcomeOpacity : 0);
    this.el(".welcome").style.transform = `scale(${s.welcomeScale})`;
    this.el(".welcome").style.filter =
      `blur(${s.exitBlur}px) invert(${s.exit * 0.22}) sepia(${s.exit}) saturate(${1 + s.exit * 5}) hue-rotate(${s.exit * 115}deg)`;
    this.opacity(".welcome-panel", s.welcomePanel);
    this.opacity(".welcome-heading", 1);
    this.el(".welcome-heading").style.color =
      themeAmount > .0001 ? "var(--theme-ink)" : `rgb(${255 * (1 - s.welcomeInk)} ${255 * (1 - s.welcomeInk)} ${255 * (1 - s.welcomeInk)})`;
    this.opacity(".welcome-company", s.companyVisible);
    this.el(".welcome-company").style.opacity = String(
      s.companyVisible ? (s.companyMask ? 0.65 : 1) : 0,
    );
    this.companyInk[1].querySelector("span")!.style.opacity = s.companyMask
      ? ".06"
      : "1";
    this.el(".welcome-highlight").style.clipPath =
      `inset(0 ${100 * (1 - s.highlight)}% 0 0)`;
    this.opacity(".welcome-database", s.databaseOpacity);
    this.opacity(".welcome-logo", s.welcomeLogo);
    this.opacity("#boot-background", s.backgroundOpacity);
    this.opacity(".boot-white", s.white);
    this.el(".boot-background svg").style.transform =
      `translate(${Math.sin(t * 0.16) * 18}px, ${-(t - 6) * 5}px) scale(1.08)`;
    return s;
  }

──── src/boot.ts:197-264  ★ 尾段生效 ★renderScan：尾段专有。扫描环全部几何（弧、端点圆、小点、字距）都由这里落进 SVG
  private renderScan(s: ReturnType<typeof bootMotion>) {
    const { scan } = s,
      r = scan.radius;
    const group = this.scanPaths[0].parentElement!;
    group.setAttribute(
      "transform",
      `translate(960 540) scale(${s.ringScale}) translate(-960 -540)`,
    );
    group.style.opacity = String(s.ringOpacity);
    group.style.filter = `blur(${s.ringBlur}px)`;
    this.scanPaths[0].setAttribute(
      "d",
      arc(r, scan.outerStart, scan.outerSweep),
    );
    this.scanPaths[0].setAttribute("stroke-width", "2.4");
    this.scanPaths[1].setAttribute(
      "d",
      arc(scan.whiteRadius, scan.whiteStart, scan.whiteSweep),
    );
    this.scanPaths[1].setAttribute("stroke-width", "4");
    const inner = scan.innerStart;
    this.scanPaths[2].setAttribute(
      "d",
      arc(scan.innerRadius, inner, scan.innerSweep),
    );
    this.scanPaths[3].setAttribute(
      "d",
      arc(scan.innerRadius, inner + Math.PI, scan.innerSweep),
    );
    s.scanOrbit.sides.forEach((side, i) => {
      this.scanPaths[i + 4].setAttribute(
        "d",
        arc(side.radius, side.start, side.sweep, side.x, side.y),
      );
      this.scanPaths[i + 4].style.opacity = s.scanOrbit.sideVisible ? "1" : "0";
    });
    s.scanOrbit.satellites.forEach((point, i) => {
      const dot = this.satellites[i];
      dot.setAttribute("cx", String(point.x));
      dot.setAttribute("cy", String(point.y));
      dot.setAttribute("r", String(point.radius));
    });
    this.core.style.opacity = s.ornament ? "1" : "0";
    this.core.setAttribute("r", String(s.coreRadius));
    const orbit = scan.orbit;
    this.orbitDots.forEach((dot, i) => {
      dot.setAttribute(
        "cx",
        String(960 + Math.cos(orbit + i * Math.PI) * scan.orbitRadius),
      );
      dot.setAttribute(
        "cy",
        String(540 + Math.sin(orbit + i * Math.PI) * scan.orbitRadius),
      );
      dot.setAttribute("r", String(scan.dotRadius));
    });
    this.caps.forEach((cap, i) => {
      const angle = i ? scan.whiteStart : scan.outerStart + scan.outerSweep;
      const radius = i ? scan.whiteRadius : r;
      cap.setAttribute("cx", String(960 + Math.cos(angle) * radius));
      cap.setAttribute("cy", String(540 + Math.sin(angle) * radius));
      cap.setAttribute("r", String(i ? scan.whiteCap : scan.blackCap));
    });
    this.opacity(".scan > span", s.permissionOpacity);
    this.el(".scan > span").style.letterSpacing = `${s.scanTracking}px`;
    this.el(".scan > span").style.setProperty("--boot-phrase-tracking", `${s.scanTracking}px`);
    this.el(".scan > span").style.fontSize = `${s.scanFont}px`;
  }

──── src/boot.ts:265-273  ★ 尾段生效 reset：跳过或重播时的收尾，尾段里被 setMode 调用
  reset() {
    // Restore shared corner branding when skipping at any intermediate frame.
    [".brand", ".powered"].forEach((key) =>
      this.el(key).removeAttribute("style"),
    );
    this.brandLines.forEach((node) => node.removeAttribute("style"));
    this.el(".powered").innerHTML = this.poweredHTML;
    this.opacity("#boot-background", 0);
  }
